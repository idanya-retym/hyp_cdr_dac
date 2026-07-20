"""
Thermometer MUX Shift Register — Gray-Code-Only Simulation (v1_1)

Tests ONLY valid gray-code transitions of vsel<1:0> where a single bit
toggles per step.  The gray code sequence is:

    00 → 01 → 11 → 10 → 00 → ...   (forward / UP)
    00 → 10 → 11 → 01 → 00 → ...   (reverse / DOWN)

Each transition changes exactly 1 select line.  This script tests whether
single-bit vsel toggles produce ±1 thermometer code changes.

Block: 4-bit bidirectional thermometer shift register
Cell:  hyp_adc_cdr_daq_mux_wr2 × 4

Connectivity (same as v1_0):
    I_mux0: in0=in_pre,       in1=I_mux1.vout,  sel=vsel<1>
    I_mux1: in0=I_mux0.vout,  in1=I_mux2.vout,  sel=vsel<0>
    I_mux2: in0=I_mux1.vout,  in1=I_mux3.vout,  sel=vsel<1>
    I_mux3: in0=I_mux2.vout,  in1=in_post,      sel=vsel<0>

Usage:
    python therm_sr_sim_v1_1.py
"""

import sys
from typing import List, Tuple

MAX_ITER = 20


# ── Mux cell model ──────────────────────────────────────────────────────────

def mux_wr2(in0: int, in1: int, sel: int, sel_rst: int, in_rst: int) -> int:
    if sel_rst:
        return in_rst
    return in0 if sel == 0 else in1


# ── 4-bit shift register ────────────────────────────────────────────────────

def evaluate(state: List[int], in_pre: int, in_post: int,
             vsel1: int, vsel0: int, sel_rst: int,
             in_rst: List[int]) -> Tuple[List[int], bool, int]:
    s = list(state)
    for it in range(1, MAX_ITER + 1):
        n = [0] * 4
        n[0] = mux_wr2(in_pre, s[1], vsel1, sel_rst, in_rst[0])
        n[1] = mux_wr2(s[0],  s[2], vsel0, sel_rst, in_rst[1])
        n[2] = mux_wr2(s[1],  s[3], vsel1, sel_rst, in_rst[2])
        n[3] = mux_wr2(s[2],  in_post, vsel0, sel_rst, in_rst[3])
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


# ── Gray code helpers ────────────────────────────────────────────────────────

GRAY_FWD = [(0,0), (0,1), (1,1), (1,0)]   # forward gray sequence
GRAY_REV = [(0,0), (1,0), (1,1), (0,1)]   # reverse gray sequence

GRAY_TRANSITIONS = {
    (0,0): [(0,1), (1,0)],   # neighbors in gray code
    (0,1): [(0,0), (1,1)],
    (1,1): [(0,1), (1,0)],
    (1,0): [(0,0), (1,1)],
}


# ── Tests ────────────────────────────────────────────────────────────────────

def test_single_bit_transitions():
    """Test every single-bit vsel toggle from every therm code."""
    header("TEST 1: ALL SINGLE-BIT VSEL TRANSITIONS")
    print("  For each (starting_therm_code, starting_vsel), toggle ONE bit of vsel.")
    print("  Check if the result is still thermometric and what the code change is.")
    print("  in_pre=1, in_post=0, sel_rst=0")
    print()

    therm_states = [
        [0,0,0,0], [1,0,0,0], [1,1,0,0], [1,1,1,0], [1,1,1,1]
    ]

    vsel_hdr = "vsel'"
    print(f"  {'therm':>5} | {'vsel':>4} -> {vsel_hdr:>5} | {'bit':>5} | "
          f"{'before':>6} -> {'after':>6} | {'delta':>5} | {'therm?':>6} | {'conv':>4} | note")
    print(f"  {'-'*5}-+-{'-'*4}---{'-'*5}-+-{'-'*5}-+-"
          f"{'-'*6}---{'-'*6}-+-{'-'*5}-+-{'-'*6}-+-{'-'*4}-+------")

    for tc in therm_states:
        for v1, v0 in GRAY_FWD:
            # First settle into this vsel state
            state, conv0, _ = evaluate(tc, 1, 0, v1, v0, 0, [0]*4)
            if not conv0 or state != tc:
                # This vsel doesn't hold this code — skip as starting point
                continue

            # Now try each single-bit toggle
            for nv1, nv0 in GRAY_TRANSITIONS[(v1, v0)]:
                toggled_bit = "vsel1" if nv1 != v1 else "vsel0"
                result, conv, it = evaluate(state, 1, 0, nv1, nv0, 0, [0]*4)
                delta = code(result) - code(state)
                therm = is_therm(result)
                note = ""
                if not conv:
                    note = "⚠ metastable"
                elif delta == 1:
                    note = "✓ UP"
                elif delta == -1:
                    note = "✓ DOWN"
                elif delta == 0:
                    note = "— hold"
                else:
                    note = f"✗ jump {delta:+d}"

                print(f"  {code(state):>5} | {v1}{v0:>3} → {nv1}{nv0:>4} | {toggled_bit:>5} | "
                      f"{fmt(state):>6} → {fmt(result):>6} | {delta:>+5} | {therm!s:>6} | "
                      f"{conv!s:>4} | {note}")
        print()


def test_gray_counting_forward():
    """Walk the gray code forward: 00→01→11→10→00→... and track therm code."""
    header("TEST 2: GRAY CODE FORWARD COUNTING (00→01→11→10→00...)")
    print("  Start from each therm code at vsel=10 (hold), step through")
    print("  the full gray cycle and track code changes per step.")
    print("  in_pre=1, in_post=0")
    print()

    therm_states = [
        [0,0,0,0], [1,0,0,0], [1,1,0,0], [1,1,1,0], [1,1,1,1]
    ]

    # Forward: 10 → 00 → 01 → 11 → 10 → 00 → 01 → 11 → 10
    fwd_seq = [(1,0), (0,0), (0,1), (1,1), (1,0), (0,0), (0,1), (1,1), (1,0)]

    for init in therm_states:
        print(f"  Start: {fmt(init)} (code {code(init)}), vsel=10 (hold)")
        state = list(init)
        prev_code = code(state)
        for step_i, (v1, v0) in enumerate(fwd_seq):
            state, conv, it = evaluate(state, 1, 0, v1, v0, 0, [0]*4)
            c = code(state)
            delta = c - prev_code
            therm = is_therm(state)
            conv_str = "conv" if conv else "META"
            print(f"    step {step_i}: vsel={v1}{v0} → {fmt(state)} "
                  f"code={c} Δ={delta:+d} {conv_str} "
                  f"{'✓' if therm else '✗ non-therm!'}")
            prev_code = c
        print()


def test_gray_counting_reverse():
    """Walk the gray code in reverse: 10→11→01→00→10→..."""
    header("TEST 3: GRAY CODE REVERSE COUNTING (10→11→01→00→10...)")
    print("  Start from each therm code at vsel=10 (hold), step through")
    print("  reverse gray cycle.")
    print("  in_pre=1, in_post=0")
    print()

    therm_states = [
        [0,0,0,0], [1,0,0,0], [1,1,0,0], [1,1,1,0], [1,1,1,1]
    ]

    # Reverse: 10 → 11 → 01 → 00 → 10 → 11 → 01 → 00 → 10
    rev_seq = [(1,0), (1,1), (0,1), (0,0), (1,0), (1,1), (0,1), (0,0), (1,0)]

    for init in therm_states:
        print(f"  Start: {fmt(init)} (code {code(init)}), vsel=10 (hold)")
        state = list(init)
        prev_code = code(state)
        for step_i, (v1, v0) in enumerate(rev_seq):
            state, conv, it = evaluate(state, 1, 0, v1, v0, 0, [0]*4)
            c = code(state)
            delta = c - prev_code
            therm = is_therm(state)
            conv_str = "conv" if conv else "META"
            print(f"    step {step_i}: vsel={v1}{v0} → {fmt(state)} "
                  f"code={c} Δ={delta:+d} {conv_str} "
                  f"{'✓' if therm else '✗ non-therm!'}")
            prev_code = c
        print()


def test_repeated_up_down():
    """Repeat gray forward/reverse cycles to see if ±1 steps accumulate correctly."""
    header("TEST 4: REPEATED GRAY CYCLES — ACCUMULATION CHECK")
    print("  Apply N forward gray cycles from code=0, then N reverse from result.")
    print("  If each cycle = +1 or -1, final code should match.")
    print("  in_pre=1, in_post=0")
    print()

    # One full forward gray cycle from hold: 10 → 00 → 01 → 11 → 10
    one_fwd = [(0,0), (0,1), (1,1), (1,0)]
    # One full reverse gray cycle from hold: 10 → 11 → 01 → 00 → 10
    one_rev = [(1,1), (0,1), (0,0), (1,0)]

    state = [0,0,0,0]
    print(f"  Start: {fmt(state)} code={code(state)}")
    print()

    # Forward 8 cycles
    print("  FORWARD (8 cycles):")
    for cycle in range(8):
        for v1, v0 in one_fwd:
            state, conv, _ = evaluate(state, 1, 0, v1, v0, 0, [0]*4)
        c = code(state)
        therm = is_therm(state)
        print(f"    cycle {cycle+1}: {fmt(state)} code={c} "
              f"{'✓' if therm else '✗'} {'conv' if conv else 'META'}")

    print()
    print("  REVERSE (8 cycles):")
    for cycle in range(8):
        for v1, v0 in one_rev:
            state, conv, _ = evaluate(state, 1, 0, v1, v0, 0, [0]*4)
        c = code(state)
        therm = is_therm(state)
        print(f"    cycle {cycle+1}: {fmt(state)} code={c} "
              f"{'✓' if therm else '✗'} {'conv' if conv else 'META'}")

    print()
    print(f"  Final: {fmt(state)} code={code(state)} "
          f"(should be 0 if symmetric)")


def test_half_cycle_steps():
    """Test if a HALF gray cycle (2 transitions) produces ±1."""
    header("TEST 5: HALF-CYCLE STEPS (2 transitions = 1 shift?)")
    print("  Maybe a full 4-step gray cycle is too much.")
    print("  Test if 2 transitions (half cycle) gives exactly ±1.")
    print("  in_pre=1, in_post=0")
    print()

    therm_states = [
        [0,0,0,0], [1,0,0,0], [1,1,0,0], [1,1,1,0], [1,1,1,1]
    ]

    half_cycles = {
        "UP-A: 10→00→01": [(0,0), (0,1)],
        "UP-B: 01→11→10": [(1,1), (1,0)],
        "DN-A: 10→11→01": [(1,1), (0,1)],
        "DN-B: 01→00→10": [(0,0), (1,0)],
    }

    for name, steps in half_cycles.items():
        # Determine starting vsel (first of the 3 states in the name)
        if name.startswith("UP-A") or name.startswith("DN-A"):
            start_vsel = (1, 0)
        else:
            start_vsel = (0, 1)

        print(f"  {name}  (start at vsel={start_vsel[0]}{start_vsel[1]})")
        print(f"    {'start':>6} → {'end':>6} | {'codeΔ':>5} | {'therm?':>6} | note")
        print(f"    {'-'*6}---{'-'*6}-+-{'-'*5}-+-{'-'*6}-+------")

        for init in therm_states:
            # First confirm we can hold at start_vsel
            state, conv, _ = evaluate(init, 1, 0, start_vsel[0], start_vsel[1], 0, [0]*4)
            if state != init:
                print(f"    {fmt(init):>6} → {'skip':>6} | {'':>5} | {'':>6} | "
                      f"can't hold at vsel={start_vsel[0]}{start_vsel[1]}")
                continue

            state = list(init)
            for v1, v0 in steps:
                state, conv, _ = evaluate(state, 1, 0, v1, v0, 0, [0]*4)

            # Return to hold
            state, conv, _ = evaluate(state, 1, 0, start_vsel[0], start_vsel[1], 0, [0]*4)

            delta = code(state) - code(init)
            therm = is_therm(state)
            if delta == 1:
                note = "✓ +1"
            elif delta == -1:
                note = "✓ -1"
            elif delta == 0:
                note = "— no change"
            else:
                note = f"✗ jump {delta:+d}"
            if not conv:
                note += " ⚠ META"

            print(f"    {fmt(init):>6} → {fmt(state):>6} | {delta:>+5} | {therm!s:>6} | {note}")
        print()


def test_alternating_hold_shift():
    """Test alternating between the two hold states with shift in between."""
    header("TEST 6: PING-PONG BETWEEN HOLD STATES")
    print("  vsel=10 and vsel=01 are both (partial) hold states.")
    print("  Test: 10→00→01 (shift thru 00) then 01→11→10 (shift thru 11)")
    print("  Each segment: hold → shift → hold")
    print("  in_pre=1, in_post=0")
    print()

    therm_states = [
        [0,0,0,0], [1,0,0,0], [1,1,0,0], [1,1,1,0], [1,1,1,1]
    ]

    # Ping-pong sequence: 10 → 00 → 01 → 11 → 10
    # This visits: hold10, shiftR, hold01, shiftL, hold10
    pingpong = [(1,0), (0,0), (0,1), (1,1), (1,0)]
    labels = ["hold10", "shiftR(00)", "hold01", "shiftL(11)", "hold10"]

    for init in therm_states:
        print(f"  Start: {fmt(init)} code={code(init)}")
        state = list(init)
        line = f"    "
        for i, (v1, v0) in enumerate(pingpong):
            state, conv, _ = evaluate(state, 1, 0, v1, v0, 0, [0]*4)
            c_str = "M" if not conv else str(code(state))
            t = "✓" if is_therm(state) else "✗"
            line += f"{labels[i]}→{fmt(state)}({c_str}{t})  "
        print(line)
    print()

    # Reverse ping-pong: 10 → 11 → 01 → 00 → 10
    print("  Reverse: 10 → 11 → 01 → 00 → 10")
    rev_pp = [(1,0), (1,1), (0,1), (0,0), (1,0)]
    rev_labels = ["hold10", "shiftL(11)", "hold01", "shiftR(00)", "hold10"]

    for init in therm_states:
        print(f"  Start: {fmt(init)} code={code(init)}")
        state = list(init)
        line = f"    "
        for i, (v1, v0) in enumerate(rev_pp):
            state, conv, _ = evaluate(state, 1, 0, v1, v0, 0, [0]*4)
            c_str = "M" if not conv else str(code(state))
            t = "✓" if is_therm(state) else "✗"
            line += f"{rev_labels[i]}→{fmt(state)}({c_str}{t})  "
        print(line)
    print()


def test_step_by_step_trace():
    """Detailed step-by-step trace showing each mux output per vsel transition."""
    header("TEST 7: DETAILED MUX-BY-MUX TRACE")
    print("  Shows individual mux outputs at each gray-code step.")
    print("  in_pre=1, in_post=0")
    print()

    # Start at code=2 (1100), vsel=10 (hold)
    init = [1, 1, 0, 0]
    print(f"  Initial state: {fmt(init)} (code 2)")
    print()

    # Forward gray: 10 → 00 → 01 → 11 → 10
    fwd = [(1,0), (0,0), (0,1), (1,1), (1,0)]
    fwd_names = ["HOLD(10)", "SHIFT_R(00)", "HOLD(01)", "SHIFT_L(11)", "HOLD(10)"]

    print(f"  {'step':>12} | vsel | {'mux0':>4} {'mux1':>4} {'mux2':>4} {'mux3':>4} | "
          f"code | {'conv':>4} | {'note'}")
    print(f"  {'-'*12}-+------+{'-'*20}-+------+{'-'*4}-+------")

    state = list(init)
    print(f"  {'(initial)':>12} |  --  | {state[0]:>4} {state[1]:>4} {state[2]:>4} {state[3]:>4} | "
          f"{code(state):>4} |      |")

    for i, (v1, v0) in enumerate(fwd):
        state, conv, it = evaluate(state, 1, 0, v1, v0, 0, [0]*4)
        c = code(state)
        note = ""
        if not conv:
            note = f"⚠ no convergence (iter={it})"
        print(f"  {fwd_names[i]:>12} | {v1}{v0:>3} | {state[0]:>4} {state[1]:>4} {state[2]:>4} {state[3]:>4} | "
              f"{c:>4} | {conv!s:>4} | {note}")

    print()
    print("  Now repeat from code=1 (1000):")
    state = [1, 0, 0, 0]
    print(f"  {'(initial)':>12} |  --  | {state[0]:>4} {state[1]:>4} {state[2]:>4} {state[3]:>4} | "
          f"{code(state):>4} |      |")
    for i, (v1, v0) in enumerate(fwd):
        state, conv, it = evaluate(state, 1, 0, v1, v0, 0, [0]*4)
        c = code(state)
        note = ""
        if not conv:
            note = f"⚠ no convergence (iter={it})"
        print(f"  {fwd_names[i]:>12} | {v1}{v0:>3} | {state[0]:>4} {state[1]:>4} {state[2]:>4} {state[3]:>4} | "
              f"{c:>4} | {conv!s:>4} | {note}")

    print()
    print("  Now repeat from code=3 (1110):")
    state = [1, 1, 1, 0]
    print(f"  {'(initial)':>12} |  --  | {state[0]:>4} {state[1]:>4} {state[2]:>4} {state[3]:>4} | "
          f"{code(state):>4} |      |")
    for i, (v1, v0) in enumerate(fwd):
        state, conv, it = evaluate(state, 1, 0, v1, v0, 0, [0]*4)
        c = code(state)
        note = ""
        if not conv:
            note = f"⚠ no convergence (iter={it})"
        print(f"  {fwd_names[i]:>12} | {v1}{v0:>3} | {state[0]:>4} {state[1]:>4} {state[2]:>4} {state[3]:>4} | "
              f"{c:>4} | {conv!s:>4} | {note}")


def print_summary():
    header("SUMMARY & INTERPRETATION")
    print("""
  GRAY CODE SEQUENCE:  00 → 01 → 11 → 10 → 00 → ...
  Each step changes exactly 1 bit of vsel<1:0>.

  EXPECTED BEHAVIOR:
    Forward gray (00→01→11→10): each step should produce +1 therm code
    Reverse gray (10→11→01→00): each step should produce -1 therm code

  KEY QUESTIONS ANSWERED BY THIS SIMULATION:
    1. Does a single gray code step produce exactly ±1?
    2. How many gray steps make one full therm increment?
       (1 step = ±1?  2 steps?  4 steps for full cycle?)
    3. Are there any states where gray stepping breaks thermometer validity?
    4. Is the behavior symmetric (UP path mirrors DOWN path)?

  IF RESULTS DON'T SHOW ±1 PER STEP:
    → The connectivity model may be wrong
    → Need to verify actual in0/in1 connections from schematic
    → Or the grey controller does NOT simply cycle through gray codes
""")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    try:
        print("=" * 72)
        print("  THERMOMETER MUX SR — GRAY-CODE-ONLY SIMULATION (v1.1)")
        print("  Only single-bit vsel transitions (valid gray code steps)")
        print("=" * 72)

        test_single_bit_transitions()
        test_gray_counting_forward()
        test_gray_counting_reverse()
        test_repeated_up_down()
        test_half_cycle_steps()
        test_alternating_hold_shift()
        test_step_by_step_trace()
        print_summary()

        print("=" * 72)
        print("  SIMULATION COMPLETE")
        print("=" * 72)

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
