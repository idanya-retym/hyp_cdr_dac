"""
Thermometric DAC: Required current source sigma (mismatch) vs. target DNL.

DAC:  7-bit, fully thermometric, differential
      N = 2^7 - 1 = 127 unit current sources

For a fully thermometric DAC the DNL at each code transition is set by the
deviation of a single unit current source from the average.  Given a relative
mismatch  sigma_rel = sigma(Iu)/Iu  the probability that *all* 127 codes meet
|DNL| < DNL_target is:

    Yield ≈ [ 2·Phi(DNL_target / sigma_rel) - 1 ]^N

where Phi is the standard-normal CDF.

This script:
  1. Plots sigma_rel vs. DNL_target for several yield levels  (analytical)
  2. Plots yield   vs. sigma_rel for DNL < 0.5 LSB           (analytical)
  3. Runs Monte Carlo to overlay simulated yield on (2)
  4. Runs Monte Carlo to overlay simulated max|DNL| percentiles on (1)

Usage:
    python dac_sigma_vs_dnl.py                 # default params
    python dac_sigma_vs_dnl.py --mc 10000      # set Monte Carlo iterations
    python dac_sigma_vs_dnl.py --bits 7        # change resolution
"""

import argparse
import numpy as np
from scipy.stats import norm
from scipy.special import erfinv
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# ---------------------------------------------------------------------------
# Analytical helpers
# ---------------------------------------------------------------------------

def sigma_for_dnl_yield(dnl_target: float, yield_target: float, n_elements: int) -> float:
    """Return the max allowable sigma_rel so that P(all |DNL|<dnl_target) >= yield_target."""
    # Y = [2*Phi(dnl_target/sigma) - 1]^N
    # => Phi(dnl_target/sigma) = (1 + Y^(1/N)) / 2
    # => dnl_target/sigma = Phi_inv(...)
    per_element_prob = yield_target ** (1.0 / n_elements)
    phi_arg = (1.0 + per_element_prob) / 2.0
    if phi_arg >= 1.0:
        return 0.0
    z = norm.ppf(phi_arg)
    if z == 0:
        return np.inf
    return dnl_target / z


def yield_analytical(sigma_rel: np.ndarray, dnl_target: float, n_elements: int) -> np.ndarray:
    """Return yield = P(all |DNL| < dnl_target) for an array of sigma_rel values."""
    z = dnl_target / sigma_rel
    per_element = 2.0 * norm.cdf(z) - 1.0
    return per_element ** n_elements


# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------

def monte_carlo(sigma_rel_values: np.ndarray, n_elements: int,
                n_mc: int, dnl_target: float = 0.5):
    """Run Monte Carlo for each sigma_rel value.

    Returns
    -------
    mc_yield       : array – fraction of trials where max|DNL| < dnl_target
    mc_max_dnl_med : array – median of max|DNL| across trials
    mc_max_dnl_95  : array – 95th-percentile of max|DNL|
    mc_max_dnl_99  : array – 99th-percentile of max|DNL|
    """
    mc_yield = np.zeros_like(sigma_rel_values)
    mc_max_dnl_med = np.zeros_like(sigma_rel_values)
    mc_max_dnl_95 = np.zeros_like(sigma_rel_values)
    mc_max_dnl_99 = np.zeros_like(sigma_rel_values)

    for i, sr in enumerate(sigma_rel_values):
        # Each row: one trial of N unit currents with relative mismatch sr
        # I_unit = 1 + sr * randn  (normalised to unit nominal current)
        currents = 1.0 + sr * np.random.randn(n_mc, n_elements)

        # I_lsb = mean of all unit elements (per trial)
        i_lsb = currents.mean(axis=1, keepdims=True)

        # DNL(k) = (I_k - I_lsb) / I_lsb   for each unit element
        dnl = (currents - i_lsb) / i_lsb

        max_abs_dnl = np.max(np.abs(dnl), axis=1)      # shape (n_mc,)

        mc_yield[i] = np.mean(max_abs_dnl < dnl_target)
        mc_max_dnl_med[i] = np.median(max_abs_dnl)
        mc_max_dnl_95[i] = np.percentile(max_abs_dnl, 95)
        mc_max_dnl_99[i] = np.percentile(max_abs_dnl, 99)

    return mc_yield, mc_max_dnl_med, mc_max_dnl_95, mc_max_dnl_99


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_all(n_bits: int, n_mc: int):
    n_elements = 2 ** n_bits - 1
    print(f"\n{'='*60}")
    print(f"  {n_bits}-bit fully thermometric differential DAC")
    print(f"  Unit elements N = {n_elements}")
    print(f"  Monte Carlo iterations = {n_mc}")
    print(f"{'='*60}\n")

    # ---- Sweep ranges ----
    dnl_targets = np.linspace(0.1, 1.0, 300)
    yield_levels = [0.90, 0.95, 0.99, 0.997]
    sigma_sweep = np.linspace(0.001, 0.25, 300)    # 0.1 % to 25 %

    # ---- Figure 1: sigma_rel vs DNL_target for various yield ----
    fig1, ax1 = plt.subplots(figsize=(9, 6))
    for yl in yield_levels:
        sig = np.array([sigma_for_dnl_yield(d, yl, n_elements) for d in dnl_targets])
        ax1.plot(dnl_targets, sig * 100, label=f"Yield = {yl*100:.1f}%")

    ax1.set_xlabel("DNL target  [LSB]", fontsize=12)
    ax1.set_ylabel("Max allowable  σ(Iu)/Iu  [%]", fontsize=12)
    ax1.set_title(f"{n_bits}-bit thermometric DAC – required current-source matching", fontsize=13)
    ax1.legend(fontsize=11)
    ax1.grid(True, which="both", ls="--", alpha=0.5)
    ax1.set_xlim(dnl_targets[0], dnl_targets[-1])
    ax1.set_ylim(bottom=0)

    # Print key numbers
    print("Analytical:  required σ(Iu)/Iu  for |DNL| < 0.5 LSB")
    print("-" * 45)
    for yl in yield_levels:
        s = sigma_for_dnl_yield(0.5, yl, n_elements)
        print(f"  Yield {yl*100:5.1f}%  →  σ_rel ≤ {s*100:.3f}%   ({s:.5f})")
    print()

    # ---- Figure 2: Yield vs sigma_rel for DNL < 0.5 LSB ----
    fig2, ax2 = plt.subplots(figsize=(9, 6))
    y_anal = yield_analytical(sigma_sweep, 0.5, n_elements)
    ax2.plot(sigma_sweep * 100, y_anal * 100, "b-", lw=2, label="Analytical")

    # Monte Carlo overlay
    sigma_mc = np.linspace(0.005, 0.22, 30)
    print(f"Running Monte Carlo ({n_mc} iterations × {len(sigma_mc)} sigma points) ...")
    mc_yield, mc_med, mc_95, mc_99 = monte_carlo(sigma_mc, n_elements, n_mc, 0.5)
    ax2.plot(sigma_mc * 100, mc_yield * 100, "ro", ms=5, label=f"Monte Carlo (N={n_mc})")
    print("Monte Carlo done.\n")

    ax2.set_xlabel("σ(Iu)/Iu  [%]", fontsize=12)
    ax2.set_ylabel("Yield  [%]   (all |DNL| < 0.5 LSB)", fontsize=12)
    ax2.set_title(f"{n_bits}-bit thermometric DAC – yield vs. mismatch", fontsize=13)
    ax2.legend(fontsize=11)
    ax2.grid(True, which="both", ls="--", alpha=0.5)
    ax2.set_xlim(sigma_sweep[0] * 100, sigma_sweep[-1] * 100)
    ax2.set_ylim(0, 105)

    # ---- Figure 3: Expected max|DNL| percentiles vs sigma ----
    fig3, ax3 = plt.subplots(figsize=(9, 6))
    ax3.plot(sigma_mc * 100, mc_med,  "g-o", ms=4, label="Median  max|DNL|")
    ax3.plot(sigma_mc * 100, mc_95,   "r-s", ms=4, label="95th %-ile  max|DNL|")
    ax3.plot(sigma_mc * 100, mc_99,   "k-^", ms=4, label="99th %-ile  max|DNL|")
    ax3.axhline(0.5, color="blue", ls="--", lw=1.5, label="DNL = 0.5 LSB")
    ax3.axhline(1.0, color="red",  ls="--", lw=1.5, label="DNL = 1.0 LSB (non-monotonic)")

    ax3.set_xlabel("σ(Iu)/Iu  [%]", fontsize=12)
    ax3.set_ylabel("max |DNL|  [LSB]", fontsize=12)
    ax3.set_title(f"{n_bits}-bit thermometric DAC – max|DNL| distribution vs. mismatch", fontsize=13)
    ax3.legend(fontsize=10)
    ax3.grid(True, which="both", ls="--", alpha=0.5)
    ax3.set_xlim(sigma_mc[0] * 100, sigma_mc[-1] * 100)
    ax3.set_ylim(bottom=0)

    # ---- Summary table ----
    print("Monte Carlo summary  (DNL target = 0.5 LSB)")
    print(f"{'σ_rel [%]':>10}  {'Yield [%]':>10}  {'med |DNL|':>10}  {'95% |DNL|':>10}  {'99% |DNL|':>10}")
    print("-" * 60)
    for j in range(len(sigma_mc)):
        print(f"{sigma_mc[j]*100:10.2f}  {mc_yield[j]*100:10.1f}  {mc_med[j]:10.4f}  {mc_95[j]:10.4f}  {mc_99[j]:10.4f}")

    plt.tight_layout()
    plt.show()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Thermometric DAC sigma vs DNL analysis")
    parser.add_argument("--bits", type=int, default=7, help="DAC resolution in bits (default 7)")
    parser.add_argument("--mc",   type=int, default=5000, help="Monte Carlo iterations (default 5000)")
    args = parser.parse_args()

    plot_all(args.bits, args.mc)
