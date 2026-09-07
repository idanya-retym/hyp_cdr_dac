"""
Unified resistor-bank generator.

Designs any number of binary-weighted conductance banks (base resistor
always on + N switched binary bits) from a SINGLE physical unit resistor.
Each bank may use a different multiplier of that unit (series stack or
parallel group) to reach its range with the smallest resistor count.

You only edit the BANKS table below: name, Rmin, Rmax, step [ohm], short.
  - step is the target resistance step at the COARSE end (near Rmax);
    the step gets finer toward Rmin (conductance is what's linear).
  - short=True adds one extra switch that shorts the bank to 0 ohm
    (used by the common-mode bank for V_cm = 0).

Structure per bank:
  R(code) = 1 / (g_lsb * (N_base + code)),  code = 0 .. 2^N - 1
  Each leg = the bank's unit (mult x 3k series, or 3k / mult parallel).
  base = N_base legs (always on); bit i = 2^i legs (one switch).
"""

import math

# =============================================
# GLOBAL: the one physical unit resistor
# =============================================
UNIT_R = 3000.0        # ohm (a bit more is fine; change here)

# =============================================
# BANKS: edit Rmin, Rmax, step (ohm), short
# =============================================
BANKS = [
    dict(name="diff",        Rmin=25,  Rmax=100, step=5,  short=False, nom=50),
    dict(name="common_mode", Rmin=10,  Rmax=20,  step=5,  short=True,  nom=15),
    dict(name="bias",        Rmin=120, Rmax=480, step=40, short=False, nom=240),
]

FULL_SWEEP = False      # True -> print every code for every bank
# =============================================


def snap_unit(R_ideal):
    """Snap the bank's leg resistance to a multiple of the 3k unit.
    Returns (R_leg, mult, mode, units_per_leg)."""
    if R_ideal >= UNIT_R:
        m = max(1, round(R_ideal / UNIT_R))          # series stack
        return UNIT_R * m, m, "series", m
    else:
        p = max(1, round(UNIT_R / R_ideal))          # parallel group
        return UNIT_R / p, p, "parallel", p


def design(cfg):
    Rmin, Rmax, step = float(cfg["Rmin"]), float(cfg["Rmax"]), float(cfg["step"])
    if step >= Rmax:
        step = Rmax * 0.5
    Gmin, Gmax = 1.0 / Rmax, 1.0 / Rmin

    # LSB conductance so the first step (at Rmax) ~ requested step
    g_ideal = 1.0 / (Rmax - step) - 1.0 / Rmax
    R_leg, mult, mode, upl = snap_unit(1.0 / g_ideal)
    g_lsb = 1.0 / R_leg

    N_base = max(1, round(Gmin / g_lsb))
    code_Rmin = max(1, round(Gmax / g_lsb) - N_base)
    N_bits = max(1, math.ceil(math.log2(code_Rmin + 1)))
    max_code = 2 ** N_bits - 1

    def R(code):
        return 1.0 / (g_lsb * (N_base + code))

    total_legs = N_base + max_code
    total_units = total_legs * upl
    switches = N_bits + (1 if cfg["short"] else 0)

    # nominal target -> code that gets closest
    nom = cfg.get("nom")
    if nom:
        ideal = (1.0 / float(nom) - Gmin) / g_lsb
        cands = [int(math.floor(ideal)), int(math.ceil(ideal))]
        cands = [max(0, min(max_code, c)) for c in cands]
        code_nom = min(cands, key=lambda c: abs(R(c) - float(nom)))
        R_nom = R(code_nom)
    else:
        code_nom = None
        R_nom = None

    return dict(
        cfg=cfg, Rmin=Rmin, Rmax=Rmax, step=step,
        R_leg=R_leg, mult=mult, mode=mode, upl=upl, g_lsb=g_lsb,
        N_base=N_base, N_bits=N_bits, max_code=max_code, code_Rmin=code_Rmin,
        R=R, total_legs=total_legs, total_units=total_units, switches=switches,
        R_top=R(0), R_at_Rmin=R(code_Rmin), R_floor=R(max_code),
        nom=nom, code_nom=code_nom, R_nom=R_nom,
    )


def report(d):
    cfg = d["cfg"]
    print(f"\n{'='*64}")
    print(f"  BANK: {cfg['name']}")
    print(f"{'='*64}")
    print(f"  Requested   : {d['Rmin']:.1f} - {d['Rmax']:.1f} ohm, step ~{d['step']:.1f} ohm")
    print(f"  Achieved    : {d['R_floor']:.2f} - {d['R_top']:.2f} ohm  (reaches {d['Rmin']:.1f} at code {d['code_Rmin']})")
    if d["nom"]:
        print(f"  Nominal     : {d['nom']:.1f} ohm -> code {d['code_nom']}  (R = {d['R_nom']:.2f} ohm, error {d['R_nom']-d['nom']:+.2f} ohm)")
    print(f"  Bits        : {d['N_bits']}   (codes 0..{d['max_code']})")
    if cfg["short"]:
        print(f"  Short switch: yes  (code 'short' -> 0 ohm)")

    # leg / unit description
    if d["mode"] == "series":
        leg_desc = f"{d['mult']}x {UNIT_R:.0f} in series = {d['R_leg']:.1f} ohm"
    else:
        leg_desc = f"{d['mult']}x {UNIT_R:.0f} in parallel = {d['R_leg']:.1f} ohm"
    print(f"  Bank unit   : {leg_desc}  ({d['upl']} unit-R per leg)")

    # element table
    print(f"\n  {'Element':<8} {'Legs':<6} {'Resistance':<14} {'3k units'}")
    print(f"  {'-'*46}")
    print(f"  {'base':<8} {d['N_base']:<6d} {d['R_top']:>10.2f} ohm  {d['N_base']*d['upl']:>6d}  (always on)")
    for i in range(d["N_bits"]):
        legs = 2 ** i
        r = d["R_leg"] / legs
        print(f"  b{i:<7d} {legs:<6d} {r:>10.2f} ohm  {legs*d['upl']:>6d}  (switch)")

    # key codes
    print(f"\n  {'Code':<10} {'R [ohm]':<12} {'dR [ohm]'}")
    print(f"  {'-'*34}")
    show = range(d["max_code"] + 1) if FULL_SWEEP else \
        sorted(set([0, 1, d["code_Rmin"], d["max_code"]] +
                    ([d["code_nom"]] if d["nom"] else [])))
    for c in show:
        if c < 0 or c > d["max_code"]:
            continue
        dr = d["R"](c) - d["R"](c + 1) if c < d["max_code"] else 0.0
        tag = ""
        if c == 0:
            tag = "  <- max"
        elif d["nom"] and c == d["code_nom"]:
            tag = "  <- nominal"
        elif c == d["code_Rmin"]:
            tag = "  <- reaches Rmin"
        elif c == d["max_code"]:
            tag = "  <- floor (extra range)"
        print(f"  {c:<10d} {d['R'](c):<12.3f} {dr:.4f}{tag}")
    if cfg["short"]:
        print(f"  {'short':<10} {'0.000':<12} --")

    print(f"\n  SIZE: {d['total_legs']} legs, {d['total_units']} unit-R ({UNIT_R:.0f} ohm each), {d['switches']} switches")


def main():
    designs = [design(b) for b in BANKS]
    for d in designs:
        report(d)

    # grand summary
    print(f"\n{'='*64}")
    print(f"  SUMMARY  (unit resistor = {UNIT_R:.0f} ohm)")
    print(f"{'='*64}")
    print(f"  {'Bank':<14} {'Range [ohm]':<16} {'Nominal':<18} {'Bits':<6} {'Legs':<6} {'Size [3k units]':<16} {'Switch'}")
    print(f"  {'-'*84}")
    tot_units = 0
    tot_sw = 0
    for d in designs:
        rng = f"{d['R_floor']:.0f}-{d['R_top']:.0f}"
        nom = f"{d['nom']:.0f} @ code {d['code_nom']}" if d["nom"] else "-"
        print(f"  {d['cfg']['name']:<14} {rng:<16} {nom:<18} {d['N_bits']:<6d} {d['total_legs']:<6d} {d['total_units']:<16d} {d['switches']}")
        tot_units += d["total_units"]
        tot_sw += d["switches"]
    print(f"  {'-'*84}")
    print(f"  {'TOTAL SIZE':<14} {'':<16} {'':<18} {'':<6} {'':<6} {tot_units:<16d} {tot_sw}")
    print(f"\n{'='*64}\n")


if __name__ == "__main__":
    main()
