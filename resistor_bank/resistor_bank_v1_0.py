"""
Resistor bank design: binary-weighted conductance DAC.
Parallel switched resistors covering a programmable range.

Topology:
  R_total = 1 / (G_base + code * G_LSB)

  where G_base = 1/R_max, G_LSB = (1/R_min - 1/R_max) / (2^N - 1)
"""

import numpy as np

# =============================================
# USER PARAMETERS — change these and re-run
# =============================================
R_NOM   = 50       # nominal target [Ohm]
R_MIN   = 21.6     # design min (25/1.16) to guarantee 25Ω at +16% corner
R_MAX   = 119      # design max (100/0.84) to guarantee 100Ω at -16% corner
N_BITS  = 6        # 6 bits to maintain resolution with wider range
# =============================================

G_base = 1.0 / R_MAX
G_max  = 1.0 / R_MIN
G_range = G_max - G_base
G_lsb  = G_range / (2**N_BITS - 1)

print(f"\n{'='*60}")
print(f"  Binary-Weighted Resistor Bank Design")
print(f"{'='*60}")
print(f"  R range       = {R_MIN} – {R_MAX} Ω")
print(f"  R nominal     = {R_NOM} Ω")
print(f"  Bits (N)      = {N_BITS}")
print(f"  Total codes   = {2**N_BITS}")
print(f"{'='*60}")
print(f"\n  G_base (always on) = {G_base*1e3:.4f} mS  (R_base = {R_MAX:.1f} Ω)")
print(f"  G_LSB              = {G_lsb*1e3:.4f} mS")
print(f"  G_range            = {G_range*1e3:.4f} mS")

# Resistor values for each bit (switched in parallel)
print(f"\n  {'Bit':<5} {'Conductance':<15} {'Resistor value':<15} {'Unit resistors'}")
print(f"  {'-'*55}")
R_lsb = 1.0 / G_lsb
for i in range(N_BITS):
    g_bit = G_lsb * (2**i)
    r_bit = 1.0 / g_bit
    n_units = 2**i
    print(f"  b{i:<4} {g_bit*1e3:>10.4f} mS   {r_bit:>10.2f} Ω     {n_units}× {R_lsb:.1f}Ω")

# Resolution at key points
print(f"\n  Resolution (step size in Ω) at key resistances:")
print(f"  {'R [Ω]':<10} {'Code':<8} {'Step ΔR [Ω]':<15} {'Step [%]'}")
print(f"  {'-'*45}")
for r_target in [R_MIN, R_NOM, R_MAX]:
    g_target = 1.0 / r_target
    code = int(round((g_target - G_base) / G_lsb))
    code = max(0, min(2**N_BITS - 1, code))
    r_actual = 1.0 / (G_base + code * G_lsb)
    # step size
    r_plus = 1.0 / (G_base + (code+1) * G_lsb) if code < 2**N_BITS-1 else r_actual
    step = abs(r_actual - r_plus)
    pct = step / r_actual * 100
    print(f"  {r_actual:<10.2f} {code:<8d} {step:<15.4f} {pct:.2f}%")

# Code for nominal
g_nom = 1.0 / R_NOM
code_nom = int(round((g_nom - G_base) / G_lsb))
r_nom_actual = 1.0 / (G_base + code_nom * G_lsb)
print(f"\n  Nominal: code={code_nom}, R={r_nom_actual:.3f} Ω (error={r_nom_actual-R_NOM:.3f} Ω)")

# Sweep: R vs code
print(f"\n  Full code sweep (every 8th code shown):")
print(f"  {'Code':<8} {'R [Ω]':<12} {'ΔR [Ω]'}")
print(f"  {'-'*30}")
codes = np.arange(2**N_BITS)
R_all = 1.0 / (G_base + codes * G_lsb)
step = max(1, 2**N_BITS // 16)
for c in range(0, 2**N_BITS, step):
    dr = R_all[c] - R_all[c+1] if c < 2**N_BITS-1 else 0
    print(f"  {c:<8d} {R_all[c]:<12.3f} {dr:.4f}")
print(f"  {2**N_BITS-1:<8d} {R_all[-1]:<12.3f}")

# Comparison table for different N
print(f"\n{'='*60}")
print(f"  Comparison: bits vs resolution at R={R_NOM}Ω")
print(f"{'='*60}")
print(f"  {'N bits':<8} {'Codes':<8} {'ΔR at 50Ω':<12} {'% step':<10} {'R_LSB unit'}")
print(f"  {'-'*55}")
for n in range(3, 9):
    g_l = G_range / (2**n - 1)
    g_50 = 1.0 / R_NOM
    code_50 = int(round((g_50 - G_base) / g_l))
    r_at = 1.0 / (G_base + code_50 * g_l)
    r_next = 1.0 / (G_base + (code_50+1) * g_l)
    dr = abs(r_at - r_next)
    pct = dr / R_NOM * 100
    r_unit = 1.0 / g_l
    print(f"  {n:<8d} {2**n:<8d} {dr:<12.3f} {pct:<10.2f} {r_unit:.1f} Ω")

print(f"\n{'='*60}\n")
