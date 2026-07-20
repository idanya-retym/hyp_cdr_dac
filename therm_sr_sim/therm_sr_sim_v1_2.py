"""
Thermometer MUX Shift Register — CORRECT Netlist-Based Simulation (v1_2)

Connectivity extracted from actual Spectre netlist (hyp_adc_cdr_dac_sr_unit).

Cell: hyp_adc_cdr_dac_mux_wr2 = two cascaded inverting muxes
    I_mux:     net2 = !(sel ? in1 : in0)
    I_mux_rst: vout = !(sel_rst ? in_rst : net2)
    Normal (sel_rst=0): vout = sel ? in1 : in0   (double inversion cancels)
    Reset  (sel_rst=1): vout = !in_rst            (INVERTED reset!)

Top-level wiring:
    I_mux0: in0=in_pre,  in1=vout1, sel=vsel<1>, vout=vout0
    I_mux1: in0=vout0,   in1=vout2, sel=vsel<0>, vout=vout1
    I_mux2: in0=vout3,   in1=vout1, sel=vsel<1>, vout=vout2
    I_mux3: in0=in_post, in1=vout2, sel=vsel<0>, vout=vout3

Usage:
    python therm_sr_sim_v1_2.py
"""

import sys
from typing import List, Tuple

MAX_ITER = 50


# -- Mux model (non-inverting for normal mode, from netlist) ----------------

def mux_wr2(in0: int, in1: int, sel: int, sel_rst: int, in_rst: int) -> int:
    """Normal: vout = sel ? in1 : in0.  Reset: vout = !in_rst."""
    if sel_rst:
        return 1 - in_rst   # INVERTED reset!
    return in1 if sel else in0


# -- 4-bit shift register (actual netlist connectivity) ---------------------

def evaluate(state: List[int], in_pre: int, in_post: int,
             vsel1: int, vsel0: int, sel_rst: int,
             in_rst: List[int]) -> Tuple[List[int], bool, int]:
    """Evaluate all 4 muxes simultaneously until convergence."""
    s = list(state)
    for it in range(1, MAX_ITER + 1):
        n = [0] * 4
        # ACTUAL NETLIST CONNECTIVITY:
        n[0] = mux_wr2(in_pre,  s[1], vsel1, sel_rst, in_rst[0])   # I_mux0
        n[1] = mux_wr2(s[0],   s[2], vsel0, sel_rst, in_rst[1])    # I_mux1
        n[2] = mux_wr2(s[3],   s[1], vsel1, sel_rst, in_rst[2])    # I_mux2
        n[3] = mux_wr2(in_post, s[2], vsel0, sel_rst, in_rst[3])   # I_mux3
        if n == s:
            return n, True, it
        s = n
    return s, False, MAX_ITER


def fmt(s): return "".join(str(b) for b in s)
def code(s): return sum(s)
def is_therm(s):
    saw0 = False
    for b in s:
        if saw0 and b == 1: return False
        if b == 0: saw0 = True
    return True

def header(t):
    print(f"\n{'='*72}")
    print(f"  {t}")
    print(f"{'='*72}")


# -- Tests -----------------------------------------------------------------

def test_vsel_states():
    """Analyze what each vsel state does (hold, force, etc.)."""
    header("TEST 1: VSEL STATE ANALYSIS")
    print("  For each vsel<1:0>, determine structure (pairs, forced bits)")
    print("  and which thermometer codes are stable.")
    print("  in_pre=1, in_post=0")
    print()

    # For each vsel, which connections form?
    print("  vsel=00 (vsel<1>=0, vsel<0>=0):")
    print("    mux0: sel=0 -> vout0 = in_pre = 1")
    print("    mux1: sel=0 -> vout1 = vout0")
    print("    mux2: sel=0 -> vout2 = vout3")
    print("    mux3: sel=0 -> vout3 = in_post = 0")
    print("    => vout3=0, vout2=vout3=0, vout1=vout0=1, vout0=1")
    print("    => FORCED to [1,1,0,0] = code 2 (MID-CODE)")
    print()

    print("  vsel=01 (vsel<1>=0, vsel<0>=1):")
    print("    mux0: sel=0 -> vout0 = in_pre = 1")
    print("    mux1: sel=1 -> vout1 = vout2")
    print("    mux2: sel=0 -> vout2 = vout3")
    print("    mux3: sel=1 -> vout3 = vout2")
    print("    => vout0=1, vout2<->vout3 CROSS-COUPLED PAIR (hold)")
    print("    => vout1 follows pair value")
    print("    => Holds: code 1 [1,0,0,0] (pair=0) or code 4 [1,1,1,1] (pair=1)")
    print()

    print("  vsel=10 (vsel<1>=1, vsel<0>=0):")
    print("    mux0: sel=1 -> vout0 = vout1")
    print("    mux1: sel=0 -> vout1 = vout0")
    print("    mux2: sel=1 -> vout2 = vout1")
    print("    mux3: sel=0 -> vout3 = in_post = 0")
    print("    => vout0<->vout1 CROSS-COUPLED PAIR (hold)")
    print("    => vout2 follows pair, vout3=0")
    print("    => Holds: code 0 [0,0,0,0] (pair=0) or code 3 [1,1,1,0] (pair=1)")
    print()

    print("  vsel=11 (vsel<1>=1, vsel<0>=1):")
    print("    mux0: sel=1 -> vout0 = vout1")
    print("    mux1: sel=1 -> vout1 = vout2")
    print("    mux2: sel=1 -> vout2 = vout1")
    print("    mux3: sel=1 -> vout3 = vout2")
    print("    => vout1<->vout2 CROSS-COUPLED PAIR (hold)")
    print("    => vout0 and vout3 follow pair")
    print("    => Holds: code 0 [0,0,0,0] (pair=0) or code 4 [1,1,1,1] (pair=1)")
    print()

    # Verify with simulation
    print("  VERIFICATION (simulate all codes at each vsel):")
    therm = [[0,0,0,0],[1,0,0,0],[1,1,0,0],[1,1,1,0],[1,1,1,1]]
    for v1, v0 in [(0,0),(0,1),(1,0),(1,1)]:
        holds = []
        for tc in therm:
            s, conv, it = evaluate(tc, 1, 0, v1, v0, 0, [0]*4)
            if s == tc and conv:
                holds.append(code(tc))
        forced = None
        results = set()
        for tc in therm:
            s, conv, it = evaluate(tc, 1, 0, v1, v0, 0, [0]*4)
            results.add(fmt(s))
        if len(results) == 1:
            forced = results.pop()
        label = f"FORCED={forced}" if forced else f"holds codes {holds}"
        print(f"    vsel={v1}{v0}: {label}")
    print()


def test_gray_cw_up():
    """CW gray code: 00->10->11->01->00 = UP (+1 per step)."""
    header("TEST 2: CW GRAY CODE = UP (+1)")
    print("  Sequence: 00 -> 10 -> 11 -> 01 -> 00 -> ...")
    print("  in_pre=1, in_post=0")
    print()

    # Full traversal starting from code 0
    # Code 0 is held at vsel=11 (or vsel=10)
    # Let's start from vsel=11 with code 0
    print("  Full UP traversal from code 0:")
    state = [0, 0, 0, 0]
    vsel_seq = [(1,1), (0,1), (0,0), (1,0), (1,1), (0,1), (0,0), (1,0), (1,1)]
    labels = ["11(start)", "01(CW)", "00(CW)", "10(CW)", "11(CW)",
              "01(CW)", "00(CW)", "10(CW)", "11(CW)"]

    print(f"    {'step':>12} | {'state':>6} | code | {'conv':>4} | delta")
    print(f"    {'-'*12}-+-{'-'*6}-+------+{'-'*4}-+------")

    prev = code(state)
    for i, (v1, v0) in enumerate(vsel_seq):
        state, conv, it = evaluate(state, 1, 0, v1, v0, 0, [0]*4)
        c = code(state)
        d = c - prev
        note = ""
        if d == 1: note = "+1 UP"
        elif d == -1: note = "-1 ??"
        elif d == 0 and i > 0: note = "sat" if (c == 4 or c == 0) else "hold"
        elif d == 0: note = "init"
        else: note = f"JUMP {d:+d}!"
        print(f"    {labels[i]:>12} | {fmt(state):>6} | {c:>4} | {conv!s:>4} | {note}")
        prev = c
    print()


def test_gray_ccw_down():
    """CCW gray code: 00->01->11->10->00 = DOWN (-1 per step)."""
    header("TEST 3: CCW GRAY CODE = DOWN (-1)")
    print("  Sequence: 00 -> 01 -> 11 -> 10 -> 00 -> ...")
    print("  in_pre=1, in_post=0")
    print()

    # Full traversal starting from code 4
    print("  Full DOWN traversal from code 4:")
    state = [1, 1, 1, 1]
    vsel_seq = [(1,1), (1,0), (0,0), (0,1), (1,1), (1,0), (0,0), (0,1), (1,1)]
    labels = ["11(start)", "10(CCW)", "00(CCW)", "01(CCW)", "11(CCW)",
              "10(CCW)", "00(CCW)", "01(CCW)", "11(CCW)"]

    print(f"    {'step':>12} | {'state':>6} | code | {'conv':>4} | delta")
    print(f"    {'-'*12}-+-{'-'*6}-+------+{'-'*4}-+------")

    prev = code(state)
    for i, (v1, v0) in enumerate(vsel_seq):
        state, conv, it = evaluate(state, 1, 0, v1, v0, 0, [0]*4)
        c = code(state)
        d = c - prev
        note = ""
        if d == -1: note = "-1 DN"
        elif d == 1: note = "+1 ??"
        elif d == 0 and i > 0: note = "sat" if (c == 4 or c == 0) else "hold"
        elif d == 0: note = "init"
        else: note = f"JUMP {d:+d}!"
        print(f"    {labels[i]:>12} | {fmt(state):>6} | {c:>4} | {conv!s:>4} | {note}")
        prev = c
    print()


def test_full_range_sweep():
    """Sweep full range: UP from 0 to 4, then DOWN from 4 to 0."""
    header("TEST 4: FULL RANGE SWEEP (0->4->0)")
    print("  CW steps until saturated, then CCW steps until saturated.")
    print("  in_pre=1, in_post=0")
    print()

    # Start at code 0, vsel=11
    state = [0, 0, 0, 0]
    vsel = (1, 1)

    # CW sequence: 11->01->00->10->11->01->00->10->11...
    cw_order = [(0,1), (0,0), (1,0), (1,1)]
    ccw_order = [(1,0), (0,0), (0,1), (1,1)]

    print("  === UP (CW gray code) ===")
    print(f"    start: {fmt(state)} code={code(state)} vsel={vsel[0]}{vsel[1]}")

    prev_c = code(state)
    for step in range(12):  # max 12 CW steps
        nv = cw_order[step % 4]
        state, conv, it = evaluate(state, 1, 0, nv[0], nv[1], 0, [0]*4)
        c = code(state)
        d = c - prev_c
        sat = " (SATURATED)" if d == 0 and c == 4 else ""
        print(f"    step {step+1:>2}: vsel={nv[0]}{nv[1]} -> {fmt(state)} "
              f"code={c} d={d:+d} {sat}")
        prev_c = c
        vsel = nv
        if d == 0 and c == 4:
            break

    print()
    print("  === DOWN (CCW gray code) ===")
    print(f"    start: {fmt(state)} code={code(state)} vsel={vsel[0]}{vsel[1]}")

    # Need to get to a CCW starting point. We're at vsel=01 or 11 with code 4
    # CCW from 11: 11->10->00->01->11
    for step in range(12):
        nv = ccw_order[step % 4]
        state, conv, it = evaluate(state, 1, 0, nv[0], nv[1], 0, [0]*4)
        c = code(state)
        d = c - prev_c
        sat = " (SATURATED)" if d == 0 and c == 0 else ""
        print(f"    step {step+1:>2}: vsel={nv[0]}{nv[1]} -> {fmt(state)} "
              f"code={c} d={d:+d} {sat}")
        prev_c = c
        vsel = nv
        if d == 0 and c == 0:
            break

    print()


def test_single_bit_transitions():
    """Test every valid single-bit vsel toggle from every holdable state."""
    header("TEST 5: ALL SINGLE-BIT VSEL TRANSITIONS")
    print("  Only test from (vsel, code) pairs that are stable hold states.")
    print("  in_pre=1, in_post=0")
    print()

    # Stable (vsel, code, state) triples
    stable = [
        ((0,0), 2, [1,1,0,0]),   # forced
        ((0,1), 1, [1,0,0,0]),   # pair(2,3)=0
        ((0,1), 4, [1,1,1,1]),   # pair(2,3)=1
        ((1,0), 0, [0,0,0,0]),   # pair(0,1)=0
        ((1,0), 3, [1,1,1,0]),   # pair(0,1)=1
        ((1,1), 0, [0,0,0,0]),   # pair(1,2)=0
        ((1,1), 4, [1,1,1,1]),   # pair(1,2)=1
    ]

    gray_neighbors = {
        (0,0): [(0,1), (1,0)],
        (0,1): [(0,0), (1,1)],
        (1,0): [(0,0), (1,1)],
        (1,1): [(0,1), (1,0)],
    }

    # Which direction is CW vs CCW?
    # CW: 00->10->11->01->00
    cw_next = {(0,0):(1,0), (1,0):(1,1), (1,1):(0,1), (0,1):(0,0)}
    ccw_next = {(0,0):(0,1), (0,1):(1,1), (1,1):(1,0), (1,0):(0,0)}

    print(f"  {'from':>8} | {'vsel':>4} | {'to_vsel':>7} | {'dir':>3} | "
          f"{'before':>6} -> {'after':>6} | {'delta':>5} | {'therm':>5} | note")
    print(f"  {'-'*8}-+-{'-'*4}-+-{'-'*7}-+-{'-'*3}-+-"
          f"{'-'*6}----{'-'*6}-+-{'-'*5}-+-{'-'*5}-+------")

    for (v1, v0), c, st in stable:
        for nv in gray_neighbors[(v1, v0)]:
            direction = "CW" if nv == cw_next[(v1,v0)] else "CCW"
            result, conv, it = evaluate(st, 1, 0, nv[0], nv[1], 0, [0]*4)
            rc = code(result)
            d = rc - c
            therm = is_therm(result)
            note = ""
            if d == 1: note = "UP +1"
            elif d == -1: note = "DN -1"
            elif d == 0: note = "sat" if (c == 0 or c == 4) else "hold"
            else: note = f"JUMP {d:+d}!"
            if not conv: note += " META!"
            print(f"  code={c:>2} | {v1}{v0:>3} | {nv[0]}{nv[1]:>5} | {direction:>3} | "
                  f"{fmt(st):>6} -> {fmt(result):>6} | {d:>+5} | {therm!s:>5} | {note}")
    print()


def test_up_down_zigzag():
    """UP 3 steps, DOWN 2, UP 1 — verify code tracks correctly."""
    header("TEST 6: ZIGZAG (UP 3, DOWN 2, UP 1)")
    print("  in_pre=1, in_post=0")
    print()

    cw_order = [(0,1), (0,0), (1,0), (1,1)]   # CW from 11
    ccw_order = [(1,0), (0,0), (0,1), (1,1)]   # CCW from 11

    state = [0, 0, 0, 0]
    vsel = (1, 1)
    vsel_idx_cw = 0   # next CW step index
    vsel_idx_ccw = 0  # next CCW step index

    print(f"    {'action':>8} | vsel | {'state':>6} | code | delta")
    print(f"    {'-'*8}-+------+-{'-'*6}-+------+------")
    print(f"    {'init':>8} | {vsel[0]}{vsel[1]:>3} | {fmt(state):>6} | {code(state):>4} |")

    def step_cw():
        nonlocal state, vsel, vsel_idx_cw, vsel_idx_ccw
        nv = cw_order[vsel_idx_cw % 4]
        prev = code(state)
        state, conv, _ = evaluate(state, 1, 0, nv[0], nv[1], 0, [0]*4)
        d = code(state) - prev
        print(f"    {'UP(CW)':>8} | {nv[0]}{nv[1]:>3} | {fmt(state):>6} | {code(state):>4} | {d:+d}")
        vsel = nv
        vsel_idx_cw += 1
        # Sync CCW index to match current vsel position
        ccw_map = {(1,1):0, (1,0):1, (0,0):2, (0,1):3}
        vsel_idx_ccw = ccw_map.get(vsel, 0)

    def step_ccw():
        nonlocal state, vsel, vsel_idx_cw, vsel_idx_ccw
        nv = ccw_order[vsel_idx_ccw % 4]
        prev = code(state)
        state, conv, _ = evaluate(state, 1, 0, nv[0], nv[1], 0, [0]*4)
        d = code(state) - prev
        print(f"    {'DN(CCW)':>8} | {nv[0]}{nv[1]:>3} | {fmt(state):>6} | {code(state):>4} | {d:+d}")
        vsel = nv
        vsel_idx_ccw += 1
        cw_map = {(1,1):0, (0,1):1, (0,0):2, (1,0):3}
        vsel_idx_cw = cw_map.get(vsel, 0)

    # UP 3
    for _ in range(3): step_cw()
    # DOWN 2
    for _ in range(2): step_ccw()
    # UP 1
    step_cw()

    expected = 0 + 3 - 2 + 1
    actual = code(state)
    print(f"\n    Expected code: {expected}, Actual: {actual}  "
          f"{'PASS' if actual == expected else 'FAIL'}")


def test_reset():
    """Test reset with INVERTED in_rst values."""
    header("TEST 7: RESET (in_rst is INVERTED in hardware)")
    print("  vout = !in_rst when sel_rst=1")
    print("  To reset to code N, set in_rst = inverted target bits")
    print()

    targets = [
        (0, [0,0,0,0], [1,1,1,1]),   # want 0000 -> in_rst=1111
        (1, [1,0,0,0], [0,1,1,1]),   # want 1000 -> in_rst=0111
        (2, [1,1,0,0], [0,0,1,1]),   # want 1100 -> in_rst=0011
        (3, [1,1,1,0], [0,0,0,1]),   # want 1110 -> in_rst=0001
        (4, [1,1,1,1], [0,0,0,0]),   # want 1111 -> in_rst=0000
    ]

    # For each target, try: assert rst, set vsel to hold, release rst
    for tgt_code, tgt_state, in_rst in targets:
        print(f"  Reset to code {tgt_code} ({fmt(tgt_state)}), in_rst={fmt(in_rst)}:")

        # Find which vsel holds this code
        hold_vsels = []
        for v1, v0 in [(0,0),(0,1),(1,0),(1,1)]:
            s, conv, _ = evaluate(tgt_state, 1, 0, v1, v0, 0, [0]*4)
            if s == tgt_state:
                hold_vsels.append((v1, v0))

        for v1, v0 in [(0,0),(0,1),(1,0),(1,1)]:
            # Step 1: assert reset
            state = [0,0,0,0]
            state, _, _ = evaluate(state, 1, 0, v1, v0, 1, in_rst)
            rst_ok = state == tgt_state

            # Step 2: release reset
            state2, conv, _ = evaluate(state, 1, 0, v1, v0, 0, in_rst)
            held = state2 == tgt_state

            status = ""
            if rst_ok and held:
                status = "CORRECT (reset + hold)"
            elif rst_ok and not held:
                status = "LOST on release!"
            elif not rst_ok:
                status = f"rst gave {fmt(state)}"

            is_hold = (v1, v0) in hold_vsels
            print(f"    vsel={v1}{v0}: rst->{fmt(state)} rel->{fmt(state2)} "
                  f"{'[HOLD vsel]' if is_hold else '[NOT hold]':>12} {status}")
        print()


def test_convergence_all_states():
    """Test convergence for all 16 possible states at each vsel."""
    header("TEST 8: CONVERGENCE MAP (all 16 states x 4 vsel)")
    print("  Check if non-thermometer states can get stuck.")
    print("  in_pre=1, in_post=0")
    print()

    print(f"  {'state':>6} | {'vsel=00':>10} | {'vsel=01':>10} | {'vsel=10':>10} | {'vsel=11':>10}")
    print(f"  {'-'*6}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}")

    for bits in range(16):
        st = [(bits >> (3-i)) & 1 for i in range(4)]
        row = f"  {fmt(st):>6} |"
        for v1, v0 in [(0,0),(0,1),(1,0),(1,1)]:
            s, conv, it = evaluate(st, 1, 0, v1, v0, 0, [0]*4)
            t = "T" if is_therm(s) else "X"
            c = "!" if not conv else " "
            row += f" {fmt(s)}({code(s)}){t}{c} |"
        print(row)
    print()
    print("  T=thermometer, X=non-therm, !=no convergence")


def test_direction_reversal():
    """Test rapid direction reversal (CW then immediately CCW)."""
    header("TEST 9: DIRECTION REVERSAL")
    print("  Start at code 2, go UP 2, then immediately DOWN 3.")
    print("  in_pre=1, in_post=0")
    print()

    # Start at code 2, vsel=00
    state = [1, 1, 0, 0]
    vsel = (0, 0)

    # CW: 00->10->11  (UP 2 steps, should reach code 4)
    # Then CCW from 11: 11->10->00->01  (DOWN 3 steps, should reach code 1)
    steps = [
        ("UP", (1,0)), ("UP", (1,1)),
        ("DN", (1,0)), ("DN", (0,0)), ("DN", (0,1)),
    ]

    print(f"    {'dir':>4} | vsel | {'state':>6} | code | delta")
    print(f"    {'-'*4}-+------+-{'-'*6}-+------+------")
    print(f"    {'init':>4} | {vsel[0]}{vsel[1]:>3} | {fmt(state):>6} | {code(state):>4} |")

    prev = code(state)
    for direction, (v1, v0) in steps:
        state, conv, _ = evaluate(state, 1, 0, v1, v0, 0, [0]*4)
        c = code(state)
        d = c - prev
        print(f"    {direction:>4} | {v1}{v0:>3} | {fmt(state):>6} | {c:>4} | {d:+d}"
              f"{'  !' if not conv else ''}")
        prev = c

    expected = 2 + 2 - 3
    actual = code(state)
    print(f"\n    Expected: {expected}, Actual: {actual}  "
          f"{'PASS' if actual == expected else 'FAIL'}")


def print_summary():
    header("SUMMARY")
    print("""
  ARCHITECTURE (from netlist):
    The 4-mux SR uses cross-coupled pairs for state retention:
    - vsel=00: FORCED to code 2 [1,1,0,0] (mid-code anchor)
    - vsel=01: pair(2,3) + vout0=1 -> holds code 1 or 4
    - vsel=10: pair(0,1) + vout3=0 -> holds code 0 or 3
    - vsel=11: pair(1,2)           -> holds code 0 or 4

  GRAY CODE OPERATION:
    CW  (00->10->11->01->00): each step = +1 (UP)
    CCW (00->01->11->10->00): each step = -1 (DOWN)

  CODE-VSEL MAPPING (each code lives at a specific vsel):
    code 0 -> vsel=10 or 11
    code 1 -> vsel=01
    code 2 -> vsel=00 (forced anchor)
    code 3 -> vsel=10
    code 4 -> vsel=11

  RESET: vout = !in_rst (hardware inverts reset input)
    To reset to code N, in_rst bits must be INVERTED target.
    Release sel_rst only when vsel is a valid hold state for that code.

  SATURATION: natural clipping at code 0 and code 4.

  SCALING TO 9-BIT (511 codes):
    This 4-mux unit handles 5 codes (0-4).
    For 511 codes, chain ~128 of these units with in_pre/in_post
    connecting between adjacent units.
""")


# -- Main ------------------------------------------------------------------

def main():
    try:
        print("=" * 72)
        print("  THERMOMETER MUX SR — NETLIST-VERIFIED SIMULATION (v1.2)")
        print("  Connectivity from hyp_adc_cdr_dac_sr_unit Spectre netlist")
        print("=" * 72)

        test_vsel_states()
        test_gray_cw_up()
        test_gray_ccw_down()
        test_full_range_sweep()
        test_single_bit_transitions()
        test_up_down_zigzag()
        test_reset()
        test_convergence_all_states()
        test_direction_reversal()
        print_summary()

        print("=" * 72)
        print("  SIMULATION COMPLETE")
        print("=" * 72)

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
