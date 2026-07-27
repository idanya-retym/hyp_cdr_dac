"""
Monte Carlo DNL analysis for a thermometric DAC.

Simulates N_sweep instances of a thermometric DAC with Gaussian
current-source mismatch, and reports statistics on max|DNL| and sigma(DNL).

Just hit Run — all parameters are set below.
"""

import numpy as np

# =============================================
# USER PARAMETERS — change these and re-run
# =============================================
N_ELEMENTS = 256              # number of thermometer elements
I_UNIT     = 39.06e-6         # unit current [A]
SIGMA_REL  = 5.0              # current source mismatch [%]
N_SWEEP    = 1000             # Monte Carlo iterations
SEED       = 42               # random seed (None for random)
# =============================================

if SEED is not None:
    np.random.seed(SEED)

sigma_frac = SIGMA_REL / 100.0

# --- Monte Carlo ---
currents = I_UNIT * (1.0 + sigma_frac * np.random.randn(N_SWEEP, N_ELEMENTS))
i_lsb = currents.mean(axis=1, keepdims=True)
dnl = (currents - i_lsb) / i_lsb
max_abs_dnl = np.max(np.abs(dnl), axis=1)
sigma_dnl = np.std(dnl, axis=1)

# --- Print results ---
print(f"\n{'='*60}")
print(f"  Thermometric DAC Monte Carlo DNL Analysis")
print(f"{'='*60}")
print(f"  Elements (N)     = {N_ELEMENTS}")
print(f"  I_unit           = {I_UNIT*1e6:.2f} uA")
print(f"  I_total          = {I_UNIT*N_ELEMENTS*1e3:.3f} mA")
print(f"  sigma(dI/I)      = {SIGMA_REL:.2f}%")
print(f"  Monte Carlo runs = {N_SWEEP}")
print(f"{'='*60}")

for name, data in [("max|DNL| [LSB]", max_abs_dnl), ("sigma(DNL) [LSB]", sigma_dnl)]:
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

print("\n  Yield vs DNL target:")
print(f"    {'DNL [LSB]':>10}  {'Pass':>8}  {'Yield':>8}")
print(f"    {'-'*30}")
for target in [0.25, 0.3, 0.4, 0.5, 0.75, 1.0]:
    n_pass = np.sum(max_abs_dnl < target)
    yield_pct = n_pass / len(max_abs_dnl) * 100
    print(f"    {target:10.2f}  {n_pass:8d}  {yield_pct:7.1f}%")

print(f"\n{'='*60}")
print(f"  Summary: with {SIGMA_REL:.2f}% current source mismatch,")
print(f"  median max|DNL| = {np.median(max_abs_dnl):.4f} LSB")
print(f"  99th %-ile max|DNL| = {np.percentile(max_abs_dnl, 99):.4f} LSB")
print(f"{'='*60}\n")
