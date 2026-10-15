"""
Common-mode resistor bank design: binary-weighted conductance DAC.

Sets V_cm = I_cm * R_cm where I_cm = 10mA (constant).
Separate switch to ground provides V_cm = 0.

Topology:
  R_base (always on, N_BASE sub-units in parallel)
  + 2 switched binary-weighted conductances
  Sub-unit = 2100/35 = 60 ohm

  G(code) = G_base + code * G_LSB,  code = 0..2^N-1
"""

import numpy as np

# =============================================
# USER PARAMETERS -- change these and re-run
# =============================================
I_CM       = 10e-3    # common-mode current [A]
V_CM_MIN   = 100e-3   # min CM voltage [V]
V_CM_MAX   = 200e-3   # max CM voltage [V]
R_SIGNAL_UNIT = 2100  # signal bank unit resistor [ohm]
SUB_DIV    = 35       # sub-unit = R_SIGNAL_UNIT / SUB_DIV
N_BITS     = 2        # number of switched control bits
N_BASE     = 3        # sub-units in the always-on base
# =============================================

R_sub = R_SIGNAL_UNIT / SUB_DIV
G_sub = 1.0 / R_sub
R_cm_min = V_CM_MIN / I_CM
R_cm_max = V_CM_MAX / I_CM

G_base = N_BASE * G_sub
G_lsb  = G_sub
R_min_actual = 1.0 / ((N_BASE + 2**N_BITS - 1) * G_sub)
R_max_actual = 1.0 / G_base
N_total_sub = N_BASE + (2**N_BITS - 1)
N_total_unit = N_total_sub * SUB_DIV

print(f"\n{'='*60}")
print(f"  Common-Mode Resistor Bank (with base)")
print(f"{'='*60}")
print(f"  I_cm           = {I_CM*1e3:.1f} mA")
print(f"  V_cm target    = {V_CM_MIN*1e3:.0f} - {V_CM_MAX*1e3:.0f} mV")
print(f"  R_cm range     = {R_cm_min:.1f} - {R_cm_max:.1f} ohm")
print(f"  R_cm actual    = {R_min_actual:.2f} - {R_max_actual:.2f} ohm")
print(f"  V_cm actual    = {R_min_actual*I_CM*1e3:.1f} - {R_max_actual*I_CM*1e3:.1f} mV")
print(f"  Bits (N)       = {N_BITS}")
print(f"  Codes          = 0 to {2**N_BITS - 1} (+ separate switch for V_cm=0)")
print(f"{'='*60}")
print(f"\n  Signal bank unit = {R_SIGNAL_UNIT} ohm")
print(f"  Sub-unit         = {R_SIGNAL_UNIT}/{SUB_DIV} = {R_sub:.1f} ohm")
print(f"  N_base           = {N_BASE} sub-units (always on)")
print(f"  R_base           = {R_max_actual:.2f} ohm")
print(f"  G_sub            = {G_sub*1e3:.4f} mS")
print(f"  G_LSB            = {G_lsb*1e3:.4f} mS (= 1 sub-unit)")
print(f"  Total sub-units  = {N_total_sub} ({N_BASE} base + {2**N_BITS-1} switched)")
print(f"  Total 2100 ohm units = {N_total_sub} x {SUB_DIV} = {N_total_unit}")

# Element table
print(f"\n  {'Element':<8} {'Sub-units':<12} {'Resistance':<15} {'2100 ohm units'}")
print(f"  {'-'*55}")
print(f"  {'base':<8} {N_BASE:<12d} {R_max_actual:>10.2f} ohm    {N_BASE*SUB_DIV} (always on)")
for i in range(N_BITS):
    n_sub = 2**i
    r_bit = R_sub / n_sub
    n_unit = n_sub * SUB_DIV
    print(f"  b{i:<5} {n_sub:<12d} {r_bit:>10.2f} ohm    {n_unit} (switched)")

def r_from_code(code):
    return 1.0 / ((N_BASE + code) * G_sub)

# Full sweep
print(f"\n  Full code sweep:")
print(f"  {'Code':<8} {'Sub-units':<12} {'R [ohm]':<12} {'V_cm [mV]':<12} {'dV [mV]'}")
print(f"  {'-'*55}")
for c in range(2**N_BITS):
    n = N_BASE + c
    r_c = r_from_code(c)
    v_c = r_c * I_CM * 1e3
    if c < 2**N_BITS - 1:
        r_next = r_from_code(c + 1)
        dv = (r_c - r_next) * I_CM * 1e3
    else:
        dv = 0
    print(f"  {c:<8d} {n:<12d} {r_c:<12.3f} {v_c:<12.2f} {dv:.2f}")
print(f"  {'short':<8} {'--':<12} {'0.000':<12} {'0.00':<12} --")

print(f"\n{'='*60}\n")
