"""
Monte Carlo DNL analysis for a thermometric DAC.

Simulates N_sweep instances of a 256-element thermometric DAC with
Gaussian current-source mismatch, and reports statistics on max|DNL|
and sigma(DNL).

Usage:
    python dac_mc_dnl_v1_0.py --sigma_rel 5           # 5% mismatch
    python dac_mc_dnl_v1_0.py --sigma_rel 10 --i_unit 39.06e-6
    python dac_mc_dnl_v1_0.py --sigma_rel 3 --n_sweep 5000
"""

import argparse
import sys
import numpy as np


def run_mc(n_elements: int, i_unit: float, sigma_rel: float, n_sweep: int):
    """Run Monte Carlo and return per-sweep max|DNL| and sigma(DNL) arrays."""
    try:
        # Generate all sweeps at once: (n_sweep x n_elements)
        # I_k = I_unit * (1 + sigma_rel * randn)
        currents = i_unit * (1.0 + sigma_rel * np.random.randn(n_sweep, n_elements))

        # I_LSB = mean current per sweep (what the DAC "thinks" 1 LSB is)
        i_lsb = currents.mean(axis=1, keepdims=True)

        # DNL(k) = (I_k - I_LSB) / I_LSB
        dnl = (currents - i_lsb) / i_lsb

        # Per-sweep statistics
        max_abs_dnl = np.max(np.abs(dnl), axis=1)    # (n_sweep,)
        sigma_dnl = np.std(dnl, axis=1)               # (n_sweep,)

        return max_abs_dnl, sigma_dnl

    except MemoryError:
        print("ERROR: Not enough memory. Reduce n_sweep or n_elements.")
        sys.exit(1)


def print_stats(name: str, data: np.ndarray):
    """Print statistical summary for a data array."""
    print(f"\n  {name}:")
    print(f"    Mean        = {np.mean(data):.6f}")
    print(f"    Median      = {np.median(data):.6f}")
    print(f"    Std Dev     = {np.std(data):.6f}")
    print(f"    Min         = {np.min(data):.6f}")
    print(f"    Max         = {np.max(data):.6f}")
    print(f"    5th  %-ile  = {np.percentile(data, 5):.6f}")
    print(f"    25th %-ile  = {np.percentile(data, 25):.6f}")
    print(f"    75th %-ile  = {np.percentile(data, 75):.6f}")
    print(f"    95th %-ile  = {np.percentile(data, 95):.6f}")
    print(f"    99th %-ile  = {np.percentile(data, 99):.6f}")


def print_yield_table(max_abs_dnl: np.ndarray):
    """Print yield (% of sweeps passing) for various DNL targets."""
    print("\n  Yield vs DNL target:")
    print(f"    {'DNL [LSB]':>10}  {'Pass':>8}  {'Yield':>8}")
    print(f"    {'-'*30}")
    for target in [0.25, 0.3, 0.4, 0.5, 0.75, 1.0]:
        n_pass = np.sum(max_abs_dnl < target)
        yield_pct = n_pass / len(max_abs_dnl) * 100
        print(f"    {target:10.2f}  {n_pass:8d}  {yield_pct:7.1f}%")


def main():
    parser = argparse.ArgumentParser(
        description="Monte Carlo DNL analysis for thermometric DAC")
    parser.add_argument("--n", type=int, default=256,
                        help="Number of thermometer elements (default: 256)")
    parser.add_argument("--i_unit", type=float, default=39.06e-6,
                        help="Unit current in Amps (default: 39.06e-6)")
    parser.add_argument("--sigma_rel", type=float, required=True,
                        help="Relative current source mismatch in %% (e.g. 5 for 5%%)")
    parser.add_argument("--n_sweep", type=int, default=1000,
                        help="Number of Monte Carlo sweeps (default: 1000)")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for reproducibility")
    args = parser.parse_args()

    if args.sigma_rel <= 0:
        print("ERROR: sigma_rel must be positive.")
        sys.exit(1)

    if args.seed is not None:
        np.random.seed(args.seed)

    sigma_frac = args.sigma_rel / 100.0

    print(f"\n{'='*60}")
    print(f"  Thermometric DAC Monte Carlo DNL Analysis")
    print(f"{'='*60}")
    print(f"  Elements (N)     = {args.n}")
    print(f"  I_unit           = {args.i_unit*1e6:.2f} uA")
    print(f"  I_total          = {args.i_unit*args.n*1e3:.3f} mA")
    print(f"  sigma(dI/I)      = {args.sigma_rel:.2f}%")
    print(f"  Monte Carlo runs = {args.n_sweep}")
    if args.seed is not None:
        print(f"  Random seed      = {args.seed}")
    print(f"{'='*60}")

    max_abs_dnl, sigma_dnl = run_mc(args.n, args.i_unit, sigma_frac, args.n_sweep)

    print_stats("max|DNL|  [LSB]", max_abs_dnl)
    print_stats("sigma(DNL) [LSB]", sigma_dnl)
    print_yield_table(max_abs_dnl)

    print(f"\n{'='*60}")
    print(f"  Summary: with {args.sigma_rel:.2f}% current source mismatch,")
    print(f"  median max|DNL| = {np.median(max_abs_dnl):.4f} LSB")
    print(f"  99th %-ile max|DNL| = {np.percentile(max_abs_dnl, 99):.4f} LSB")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
