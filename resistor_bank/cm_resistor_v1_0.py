"""
Common-mode resistor bank design: binary-weighted conductance DAC.

Sets V_cm = I_cm * R_cm where I_cm = 10mA (constant).
Separate switch to ground provides V_cm = 0.

Topology:
  R_base (always on, N_base sub-units in parallel)
  + 4 switched binary-weighted conductances (1,2,4,8 sub-units)
  Sub-unit = 2100/21 = 100 ohm (matches signal bank R_base)

  G(code) = G_base + code * G_LSB,  code = 0..15
"""

import numpy as np

# =============================================
# USER PARAMETERS -- change these and re-run
# =============================================
I_CM       = 10e-3    # common-mode current [A]
V_CM_MIN   = 50e-3    # min CM voltage [V]
V_CM_MAX   = 200e-3   # max CM voltage [V]
R_SIGNAL_UNIT = 2100  # signal bank unit resistor [ohm]
SUB_DIV    = 21       # sub-unit = R_SIGNAL_UNIT / SUB_DIV
N_BITS     = 4        # number of switched control bits
N_BASE     = 5        # sub-units in the always-on base
# =============================================

R_sub = R_SIGNAL_UNIT / SUB_DIV
R_cm_min = V_CM_MIN / I_CM
R_cm_max = V_CM_MAX / I_CM

G_base = 1.0 / R_cm_max
G_lsb  = G_base / N_BASE
N_total = N_BASE + (2**N_BITS - 1)
R_min_actual = 1.0 / (G_base + (2**N_BITS - 1) * G_lsb)
R_max_actual = 1.0 / G_base

print(f"\n{'='*60}")
print(f"  Common-Mode Resistor Bank (with base)")
print(f"{'='*60}")
print(f"  I_cm           = {I_CM*1e3:.1f} mA")
print(f"  V_cm target    = {V_CM_MIN*1e3:.0f} - {V_CM_MAX*1e3:.0f} mV")
print(f"  R_cm range     = {R_cm_min:.1f} - {R_cm_max:.1f} ohm")
print(f"  R_cm actual    = {R_min_actual:.2f} - {R_max_actual:.1f} ohm")
print(f"  V_cm actual    = {R_min_actual*I_CM*1e3:.1f} - {R_max_actual*I_CM*1e3:.1f} mV")
print(f"  Bits (N)       = {N_BITS}")
print(f"  Codes          = 0 to {2**N_BITS - 1} (+ separate switch for V_cm=0)")
print(f"{'='*60}")
print(f"\n  Signal bank unit = {R_SIGNAL_UNIT} ohm")
print(f"  Sub-unit         = {R_SIGNAL_UNIT}/{SUB_DIV} = {R_sub:.1f} ohm")
print(f"  N_base           = {N_BASE} sub-units (always on)")
print(f"  R_base           = {R_max_actual:.1f} ohm")
print(f"  G_base           = {G_base*1e3:.4f} mS")
print(f"  G_LSB            = {G_lsb*1e3:.4f} mS")
print(f"  Total sub-units  = {N_total} ({N_BASE} base + {2**N_BITS-1} switched)")

# Element table
print(f"\n  {'Element':<8} {'Conductance':<15} {'Resistance':<15} {'Sub-units'}")
print(f"  {'-'*60}")
print(f"  {'base':<8} {G_base*1e3:>10.4f} mS   {R_max_actual:>10.1f} ohm    {N_BASE}x {R_sub:.0f} ohm (always on)")
for i in range(N_BITS):
    g_bit = G_lsb * (2**i)
    r_bit = 1.0 / g_bit
    n_units = 2**i
    print(f"  b{i:<5} {g_bit*1e3:>10.4f} mS   {r_bit:>10.1f} ohm    {n_units}x {R_sub:.0f} ohm (switched)")

def r_from_code(code):
    return 1.0 / (G_base + code * G_lsb)

# Full sweep
print(f"\n  Full code sweep:")
print(f"  {'Code':<8} {'R [ohm]':<12} {'V_cm [mV]':<12} {'dR [ohm]':<12} {'dV [mV]'}")
print(f"  {'-'*55}")
for c in range(2**N_BITS):
    r_c = r_from_code(c)
    v_c = r_c * I_CM * 1e3
    if c < 2**N_BITS - 1:
        r_next = r_from_code(c + 1)
        dr = r_c - r_next
        dv = dr * I_CM * 1e3
    else:
        dr = 0
        dv = 0
    print(f"  {c:<8d} {r_c:<12.3f} {v_c:<12.2f} {dr:<12.4f} {dv:.2f}")
print(f"  {'short':<8} {'0.000':<12} {'0.00':<12} {'--':<12} --")

print(f"\n{'='*60}\n")
