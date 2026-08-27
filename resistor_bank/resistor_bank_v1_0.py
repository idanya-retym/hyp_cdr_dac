"""
Resistor bank design: binary-weighted conductance DAC with base resistor.

Topology:
  R_base (always on, N_base unit resistors in parallel)
  + 6 switched binary-weighted conductances (1,2,4,8,16,32 units)

  G(code) = G_base + code * G_LSB,  code = 0..2^N-1
  G_LSB = G_base / N_base
  R_unit = 1 / G_LSB
"""

import numpy as np

# =============================================
# USER PARAMETERS -- change these and re-run
# =============================================
R_NOM    = 50       # nominal target [Ohm]
R_MIN    = 21.6     # design min (25/1.16) to guarantee 25 ohm at +16% corner
R_MAX    = 119      # design max (100/0.84) to guarantee 100 ohm at -16% corner
N_BITS   = 6        # number of switched control bits
N_BASE   = 14       # unit resistors in the always-on base
# =============================================

G_base = 1.0 / R_MAX
G_lsb  = G_base / N_BASE
R_unit = 1.0 / G_lsb
N_total = N_BASE + (2**N_BITS - 1)  # total unit resistors
R_min_actual = 1.0 / (G_base + (2**N_BITS - 1) * G_lsb)
R_max_actual = 1.0 / G_base

print(f"\n{'='*60}")
print(f"  Binary-Weighted Resistor Bank (with base)")
print(f"{'='*60}")
print(f"  R range (actual) = {R_min_actual:.2f} - {R_max_actual:.1f} ohm")
print(f"  R nominal        = {R_NOM} ohm")
print(f"  Bits (N)         = {N_BITS}")
print(f"  Codes            = 0 to {2**N_BITS - 1}")
print(f"{'='*60}")
print(f"\n  N_base         = {N_BASE} unit resistors (always on)")
print(f"  R_base         = {R_max_actual:.1f} ohm")
print(f"  R_unit         = {R_unit:.1f} ohm")
print(f"  G_base         = {G_base*1e3:.4f} mS")
print(f"  G_LSB          = {G_lsb*1e3:.4f} mS")
print(f"  Total units    = {N_total} ({N_BASE} base + {2**N_BITS-1} switched)")

# Corner analysis
print(f"  Corner analysis (+/-16% process variation):")
for corner, factor in [("-16%", 0.84), ("nom", 1.0), ("+16%", 1.16)]:
    r_lo = R_min_actual * factor
    r_hi = R_max_actual * factor
    print(f"    {corner:>4s}: {r_lo:6.2f} - {r_hi:6.1f} ohm")

# Resistor values for each element
print(f"\n  {'Element':<8} {'Conductance':<15} {'Resistance':<15} {'Unit resistors'}")
print(f"  {'-'*60}")
print(f"  {'base':<8} {G_base*1e3:>10.4f} mS   {R_max_actual:>10.1f} ohm    {N_BASE}x {R_unit:.1f} ohm (always on)")
for i in range(N_BITS):
    g_bit = G_lsb * (2**i)
    r_bit = 1.0 / g_bit
    n_units = 2**i
    print(f"  b{i:<5} {g_bit*1e3:>10.4f} mS   {r_bit:>10.1f} ohm    {n_units}x {R_unit:.1f} ohm (switched)")

def r_from_code(code):
    return 1.0 / (G_base + code * G_lsb)

# Resolution at key points
print(f"\n  Resolution (step size in ohm) at key resistances:")
print(f"  {'R [ohm]':<10} {'Code':<8} {'Step dR [ohm]':<15} {'Step [%]'}")
print(f"  {'-'*45}")
for r_target in [R_min_actual, R_NOM, R_max_actual]:
    g_target = 1.0 / r_target
    code = int(round((g_target - G_base) / G_lsb))
    code = max(0, min(2**N_BITS - 1, code))
    r_actual = r_from_code(code)
    r_next = r_from_code(code + 1) if code < 2**N_BITS - 1 else r_actual
    step = abs(r_actual - r_next)
    pct = step / r_actual * 100
    print(f"  {r_actual:<10.2f} {code:<8d} {step:<15.4f} {pct:.2f}%")

# Code for nominal
g_nom = 1.0 / R_NOM
code_nom = int(round((g_nom - G_base) / G_lsb))
code_nom = max(0, min(2**N_BITS - 1, code_nom))
r_nom_actual = r_from_code(code_nom)
print(f"\n  Nominal: code={code_nom}, R={r_nom_actual:.3f} ohm (error={r_nom_actual-R_NOM:.3f} ohm)")

# Full sweep
print(f"\n  Full code sweep:")
print(f"  {'Code':<8} {'R [ohm]':<12} {'dR [ohm]'}")
print(f"  {'-'*30}")
for c in range(2**N_BITS):
    r_c = r_from_code(c)
    r_next = r_from_code(c + 1) if c < 2**N_BITS - 1 else 0
    dr = r_c - r_next if r_next > 0 else 0
    print(f"  {c:<8d} {r_c:<12.3f} {dr:.4f}")

# Comparison table
print(f"\n{'='*60}")
print(f"  Comparison: bits vs resolution at R={R_NOM} ohm")
print(f"{'='*60}")
print(f"  {'N bits':<8} {'N_base':<8} {'Codes':<8} {'dR at 50ohm':<12} {'% step':<10} {'R_unit'}")
print(f"  {'-'*60}")
for n in range(3, 9):
    n_b = round((2**n - 1) / (R_MAX / R_min_actual - 1))
    if n_b < 1:
        n_b = 1
    g_l = G_base / n_b
    g_50 = 1.0 / R_NOM
    code_50 = int(round((g_50 - G_base) / g_l))
    code_50 = max(0, min(2**n - 1, code_50))
    r_at = 1.0 / (G_base + code_50 * g_l)
    r_next = 1.0 / (G_base + (code_50 + 1) * g_l)
    dr = abs(r_at - r_next)
    pct = dr / R_NOM * 100
    r_u = 1.0 / g_l
    print(f"  {n:<8d} {n_b:<8d} {2**n:<8d} {dr:<12.3f} {pct:<10.2f} {r_u:.1f} ohm")

print(f"\n{'='*60}\n")
