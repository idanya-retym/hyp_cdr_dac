"""
Bias resistor bank design: series-switched resistor.

Nominal 240 ohm, programmable from 120 (half) to 480 (twice).
Built from a series string of identical sub-units; each extra sub-unit
has a bypass (short) switch. R = (N_min + code) * R_sub.

Sub-unit is composed of the 2100 ohm signal-bank unit in parallel:
  R_sub = 2100 / SUB_PAR
"""

# =============================================
# USER PARAMETERS -- change these and re-run
# =============================================
R_NOM      = 240      # nominal bias resistance [ohm]
R_MIN      = 120      # min = half nominal [ohm]
R_MAX      = 480      # max = twice nominal [ohm]
R_SIGNAL_UNIT = 2100  # signal bank unit resistor [ohm]
SUB_PAR    = 70       # sub-unit = R_SIGNAL_UNIT / SUB_PAR (parallel count)
# =============================================

R_sub = R_SIGNAL_UNIT / SUB_PAR

# Series counts (must be integers)
N_min = R_MIN / R_sub
N_nom = R_NOM / R_sub
N_max = R_MAX / R_sub
assert N_min == int(N_min) and N_nom == int(N_nom) and N_max == int(N_max), \
    f"R_sub={R_sub} does not divide R_MIN/R_NOM/R_MAX evenly -- pick another SUB_PAR"
N_min, N_nom, N_max = int(N_min), int(N_nom), int(N_max)

n_codes = N_max - N_min + 1            # code 0..(N_max-N_min)
n_switch = N_max - N_min              # bypass switches (base of N_min always in)
step_ohm = R_sub
step_pct = R_sub / R_NOM * 100
units_total = N_max * SUB_PAR         # total 2100 ohm resistors (full string)

print(f"\n{'='*60}")
print(f"  Bias Resistor Bank (series-switched)")
print(f"{'='*60}")
print(f"  R nominal      = {R_NOM} ohm")
print(f"  R range        = {R_MIN} - {R_MAX} ohm (half - twice)")
print(f"  Codes          = 0 to {n_codes-1} ({n_codes} values)")
print(f"  Bypass switches= {n_switch}")
print(f"{'='*60}")
print(f"\n  Signal bank unit = {R_SIGNAL_UNIT} ohm")
print(f"  Sub-unit         = {R_SIGNAL_UNIT}/{SUB_PAR} = {R_sub:.1f} ohm ({SUB_PAR}x {R_SIGNAL_UNIT} in parallel)")
print(f"  Series count     = {N_min} (min) .. {N_nom} (nom) .. {N_max} (max)")
print(f"  Step             = {step_ohm:.1f} ohm ({step_pct:.2f}% of nominal)")
print(f"  Total 2100 ohm units (full string) = {N_max} x {SUB_PAR} = {units_total}")

# Full code sweep
print(f"\n  Full code sweep:")
print(f"  {'Code':<8} {'Series':<10} {'R [ohm]':<12} {'dR [ohm]'}")
print(f"  {'-'*40}")
for code in range(n_codes):
    n_series = N_min + code
    r = n_series * R_sub
    dr = R_sub if code < n_codes - 1 else 0
    tag = ""
    if n_series == N_min:
        tag = "  <- min (half)"
    elif n_series == N_nom:
        tag = "  <- nominal"
    elif n_series == N_max:
        tag = "  <- max (twice)"
    print(f"  {code:<8d} {n_series:<10d} {r:<12.1f} {dr:.1f}{tag}")

# Comparison: sub-unit choice vs resolution / area
print(f"\n{'='*60}")
print(f"  Comparison: sub-unit choice")
print(f"{'='*60}")
print(f"  {'SUB_PAR':<9} {'R_sub':<9} {'Step':<9} {'% step':<9} {'Codes':<8} {'Units'}")
print(f"  {'-'*55}")
for sp in [35, 70, 105, 140, 210, 420]:
    rs = R_SIGNAL_UNIT / sp
    if R_MIN % rs != 0 or R_NOM % rs != 0 or R_MAX % rs != 0:
        continue
    nmn, nmx = int(R_MIN / rs), int(R_MAX / rs)
    codes = nmx - nmn + 1
    pct = rs / R_NOM * 100
    units = nmx * sp
    print(f"  {sp:<9d} {rs:<9.1f} {rs:<9.1f} {pct:<9.2f} {codes:<8d} {units}")

print(f"\n{'='*60}\n")
