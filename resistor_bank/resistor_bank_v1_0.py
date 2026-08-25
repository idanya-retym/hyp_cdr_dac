"""
Resistor bank design: binary-weighted conductance DAC.
All resistors are switched (no always-on base resistor).

Topology:
  R_total = 1 / (code * G_LSB)

  code ranges from 1 to 2^N - 1 (code=0 is open circuit, invalid)
  G_LSB = (1/R_min) / (2^N - 1)
  R_max = 1/G_LSB = R_min * (2^N - 1)
"""

import numpy as np

# =============================================
# USER PARAMETERS — change these and re-run
# =============================================
R_NOM   = 50       # nominal target [Ohm]
R_MIN   = 21.6     # design min (25/1.16) to guarantee 25Ω at +16% corner
R_MAX   = 119      # design max (100/0.84) to guarantee 100Ω at -16% corner
N_BITS  = 6        # number of control bits
# =============================================

# G_LSB chosen so that code=2^N-1 gives R_MIN, code=1 gives R_MAX
# R = 1/(code * G_LSB) → G_LSB = 1/(R_MIN * (2^N-1))
# But also need R_MAX = 1/G_LSB → G_LSB = 1/R_MAX
# These conflict, so we use: G_LSB = 1/R_MAX, codes 1..(2^N-1)
# R_min achieved = 1/((2^N-1)*G_LSB) = R_MAX/(2^N-1)
# Adjust N or R_MAX so that R_MAX/(2^N-1) <= R_MIN

G_lsb = (1.0/R_MIN - 1.0/R_MAX) / (2**N_BITS - 2)  # code 1→R_MAX, code max→R_MIN
# code 1 gives R_MAX, code (2^N-1) gives R_MIN
# R(code) = 1 / (code * G_lsb)  where code = 1..63
# Solve: 1/(1*G_lsb) = R_MAX → G_lsb = 1/R_MAX ... no

# Simpler: all switched, conductances from G_min to G_max in 2^N-1 steps
G_min = 1.0 / R_MAX   # smallest conductance = largest R
G_max = 1.0 / R_MIN   # largest conductance = smallest R
G_lsb = (G_max - G_min) / (2**N_BITS - 2)  # code 1→G_min, code 2^N-1→G_max

print(f"\n{'='*60}")
print(f"  Binary-Weighted Resistor Bank (all switched, no base)")
print(f"{'='*60}")
print(f"  R range       = {R_MIN} – {R_MAX} Ω")
print(f"  R nominal     = {R_NOM} Ω")
print(f"  Bits (N)      = {N_BITS}")
print(f"  Valid codes   = 1 to {2**N_BITS - 1} (code 0 = open)")
print(f"{'='*60}")
print(f"\n  G_min (code=1) = {G_min*1e3:.4f} mS  (R = {R_MAX:.1f} Ω)")
print(f"  G_max (code={2**N_BITS-1}) = {G_max*1e3:.4f} mS  (R = {R_MIN:.1f} Ω)")
print(f"  G_LSB          = {G_lsb*1e3:.4f} mS")

# Resistor values for each bit (all switched in parallel)
print(f"\n  {'Bit':<5} {'Conductance':<15} {'Resistor value':<15} {'Unit resistors'}")
print(f"  {'-'*55}")
R_unit = 1.0 / G_lsb
for i in range(N_BITS):
    g_bit = G_lsb * (2**i)
    r_bit = 1.0 / g_bit
    n_units = 2**i
    print(f"  b{i:<4} {g_bit*1e3:>10.4f} mS   {r_bit:>10.2f} Ω     {n_units}× {R_unit:.1f}Ω")

# R vs code (code = number of LSB conductances switched on)
def r_from_code(code):
    if code == 0:
        return np.inf
    return 1.0 / (G_min + (code - 1) * G_lsb)

# Resolution at key points
print(f"\n  Resolution (step size in Ω) at key resistances:")
print(f"  {'R [Ω]':<10} {'Code':<8} {'Step ΔR [Ω]':<15} {'Step [%]'}")
print(f"  {'-'*45}")
for r_target in [R_MIN, R_NOM, R_MAX]:
    g_target = 1.0 / r_target
    code = int(round((g_target - G_min) / G_lsb)) + 1
    code = max(1, min(2**N_BITS - 1, code))
    r_actual = r_from_code(code)
    r_next = r_from_code(code + 1) if code < 2**N_BITS - 1 else r_actual
    step = abs(r_actual - r_next)
    pct = step / r_actual * 100 if r_actual > 0 else 0
    print(f"  {r_actual:<10.2f} {code:<8d} {step:<15.4f} {pct:.2f}%")

# Code for nominal
g_nom = 1.0 / R_NOM
code_nom = int(round((g_nom - G_min) / G_lsb)) + 1
code_nom = max(1, min(2**N_BITS - 1, code_nom))
r_nom_actual = r_from_code(code_nom)
print(f"\n  Nominal: code={code_nom}, R={r_nom_actual:.3f} Ω (error={r_nom_actual-R_NOM:.3f} Ω)")

# Full sweep
print(f"\n  Full code sweep (every 4th code shown):")
print(f"  {'Code':<8} {'R [Ω]':<12} {'ΔR [Ω]'}")
print(f"  {'-'*30}")
step_show = max(1, (2**N_BITS - 1) // 16)
for c in range(1, 2**N_BITS, step_show):
    r_c = r_from_code(c)
    r_next = r_from_code(c + 1) if c < 2**N_BITS - 1 else 0
    dr = r_c - r_next if r_next > 0 else 0
    print(f"  {c:<8d} {r_c:<12.3f} {dr:.4f}")
print(f"  {2**N_BITS-1:<8d} {r_from_code(2**N_BITS-1):<12.3f}")

# Comparison table
print(f"\n{'='*60}")
print(f"  Comparison: bits vs resolution at R={R_NOM}Ω")
print(f"{'='*60}")
print(f"  {'N bits':<8} {'Codes':<8} {'ΔR at 50Ω':<12} {'% step':<10} {'R_unit'}")
print(f"  {'-'*55}")
for n in range(3, 9):
    g_l = (G_max - G_min) / (2**n - 2)
    g_50 = 1.0 / R_NOM
    code_50 = int(round((g_50 - G_min) / g_l)) + 1
    code_50 = max(1, min(2**n - 1, code_50))
    r_at = 1.0 / (G_min + (code_50 - 1) * g_l)
    r_next = 1.0 / (G_min + code_50 * g_l)
    dr = abs(r_at - r_next)
    pct = dr / R_NOM * 100
    r_u = 1.0 / g_l
    print(f"  {n:<8d} {2**n-1:<8d} {dr:<12.3f} {pct:<10.2f} {r_u:.1f} Ω")

print(f"\n{'='*60}\n")
