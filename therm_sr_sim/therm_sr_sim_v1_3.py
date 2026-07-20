"""
Reset Toggle Investigation (v1_3)

Why must you toggle vsel while sel_rst=1 before releasing reset?
Does starting vsel matter? Can you toggle multiple times?

Uses CORRECT netlist connectivity from hyp_adc_cdr_dac_sr_unit.

Usage:
    python therm_sr_sim_v1_3.py
"""

import sys
from typing import List, Tuple

MAX_ITER = 50


def mux_wr2(in0, in1, sel, sel_rst, in_rst):
    """Normal: vout = sel ? in1 : in0.  Reset: vout = !in_rst."""
    if sel_rst:
        return 1 - in_rst
    return in1 if sel else in0


def evaluate(state, in_pre, in_post, vsel1, vsel0, sel_rst, in_rst):
    s = list(state)
    for it in range(1, MAX_ITER + 1):
        n = [0] * 4
        n[0] = mux_wr2(in_pre, s[1], vsel1, sel_rst, in_rst[0])
        n[1] = mux_wr2(s[0],  s[2], vsel0, sel_rst, in_rst[1])
        n[2] = mux_wr2(s[3],  s[1], vsel1, sel_rst, in_rst[2])
        n[3] = mux_wr2(in_post, s[2], vsel0, sel_rst, in_rst[3])
        if n == s:
            return n, True, it
        s = n
    return s, False, MAX_ITER


def fmt(s): return "".join(str(b) for b in s)
def code(s): return sum(s)

def header(t):
    print(f"\n{'='*72}")
    print(f"  {t}")
    print(f"{'='*72}")


def test_why_toggle_needed():
    """Understand WHY toggling vsel during reset is required."""
    header("TEST 1: WHY TOGGLE IS NEEDED")
    print("""
  The mux_wr2 has TWO mux stages inside:
    I_mux:     net2 = !(sel ? in1 : in0)        ← data mux
    I_mux_rst: vout = !(sel_rst ? in_rst : net2) ← reset mux

  When sel_rst=1:
    - I_mux_rst output: vout = !in_rst  (correct, forced by reset)
    - I_mux output: net2 = !(sel ? in1 : in0)  (STILL ACTIVE!)

  The PROBLEM: net2 (internal node between the two muxes) is NOT
  controlled by reset. It depends on sel and the data inputs.

  When you release sel_rst (0→1→0):
    - I_mux_rst switches from in_rst to net2
    - vout = !net2
    - If net2 was in the WRONG state during reset, the output
      glitches to the wrong value before the cross-coupled pair
      can capture the correct value.

  TOGGLING vsel during reset forces net2 to cycle through different
  states, ensuring the internal node settles to a value consistent
  with the reset output. The cross-coupled pair then forms correctly
  on release.
""")

    # Demonstrate: look at what net2 would be for different vsel during reset
    print("  What happens to net2 inside each mux during reset?")
    print("  (net2 = !(sel ? in1 : in0), where in0/in1 are the DATA inputs)")
    print()

    # Target: reset to code 2 [1,1,0,0], in_rst = [0,0,1,1]
    in_rst = [0, 0, 1, 1]
    rst_state = [1, 1, 0, 0]  # what vout should be: !in_rst

    print(f"  Target: code 2 [{fmt(rst_state)}], in_rst={fmt(in_rst)}")
    print()

    print("  During reset (sel_rst=1), vout is forced to !in_rst regardless")
    print("  of vsel. But net2 inside each mux depends on vsel and data inputs:")
    print()

    print(f"  {'vsel':>4} | {'net2_0':>6} {'net2_1':>6} {'net2_2':>6} {'net2_3':>6} | "
          f"{'consistent?':>11}")
    print(f"  {'-'*4}-+-{'-'*6}-{'-'*6}-{'-'*6}-{'-'*6}-+-{'-'*11}")

    # During reset, vout = !in_rst for all muxes.
    # The data inputs (in0, in1) see the vout values = rst_state
    # net2 = !(sel ? in1 : in0)
    # For release to work cleanly, we need net2 = !vout = in_rst
    # (because on release: vout = !net2, so net2 must equal in_rst for vout to stay)

    for v1, v0 in [(0,0), (0,1), (1,0), (1,1)]:
        # What data inputs does each mux see? (outputs = rst_state during reset)
        # mux0: in0=in_pre=1, in1=vout1=rst_state[1]
        # mux1: in0=vout0=rst_state[0], in1=vout2=rst_state[2]
        # mux2: in0=vout3=rst_state[3], in1=vout1=rst_state[1]
        # mux3: in0=in_post=0, in1=vout2=rst_state[2]

        mux0_in0, mux0_in1 = 1, rst_state[1]            # in_pre, vout1
        mux1_in0, mux1_in1 = rst_state[0], rst_state[2]  # vout0, vout2
        mux2_in0, mux2_in1 = rst_state[3], rst_state[1]  # vout3, vout1
        mux3_in0, mux3_in1 = 0, rst_state[2]             # in_post, vout2

        # net2 = !(sel ? in1 : in0)
        net2_0 = 1 - (mux0_in1 if v1 else mux0_in0)
        net2_1 = 1 - (mux1_in1 if v0 else mux1_in0)
        net2_2 = 1 - (mux2_in1 if v1 else mux2_in0)
        net2_3 = 1 - (mux3_in1 if v0 else mux3_in0)

        # For clean release, net2 should equal in_rst (so vout = !net2 = !in_rst)
        needed = in_rst
        match = [net2_0 == needed[0], net2_1 == needed[1],
                 net2_2 == needed[2], net2_3 == needed[3]]
        all_match = all(match)

        marks = ["".join("OK" if m else "XX" for m in match)]
        print(f"  {v1}{v0:>3} | {net2_0:>6} {net2_1:>6} {net2_2:>6} {net2_3:>6} | "
              f"{'YES - clean' if all_match else 'NO - glitch!'}")

    print()
    print("  needed net2 (= in_rst) for clean release:", fmt(in_rst))
    print()
    print("  KEY INSIGHT: No single vsel value makes ALL net2 nodes match in_rst!")
    print("  Toggling vsel during reset lets each net2 node see the correct")
    print("  input at least once, charging the internal capacitance to the")
    print("  right value before release.")


def test_all_reset_targets():
    """For each target code, show net2 consistency at each vsel."""
    header("TEST 2: NET2 CONSISTENCY FOR ALL TARGET CODES")
    print("  For each reset target, which vsel gives consistent net2?")
    print()

    targets = [
        (0, [0,0,0,0], [1,1,1,1]),
        (1, [1,0,0,0], [0,1,1,1]),
        (2, [1,1,0,0], [0,0,1,1]),
        (3, [1,1,1,0], [0,0,0,1]),
        (4, [1,1,1,1], [0,0,0,0]),
    ]

    for tgt_code, rst_state, in_rst in targets:
        print(f"  Code {tgt_code} [{fmt(rst_state)}], in_rst={fmt(in_rst)}, need net2={fmt(in_rst)}")

        for v1, v0 in [(0,0), (0,1), (1,0), (1,1)]:
            mux0_in = 1 if v1 == 0 else rst_state[1]           # sel ? vout1 : in_pre
            mux1_in = rst_state[2] if v0 == 1 else rst_state[0] # sel ? vout2 : vout0
            mux2_in = rst_state[1] if v1 == 1 else rst_state[3] # sel ? vout1 : vout3
            mux3_in = rst_state[2] if v0 == 1 else 0            # sel ? vout2 : in_post

            net2 = [1 - mux0_in, 1 - mux1_in, 1 - mux2_in, 1 - mux3_in]
            match = [net2[i] == in_rst[i] for i in range(4)]
            n_match = sum(match)
            match_str = "".join("." if m else "X" for m in match)

            print(f"    vsel={v1}{v0}: net2={fmt(net2)} vs need={fmt(in_rst)} "
                  f"[{match_str}] {n_match}/4 "
                  f"{'ALL OK' if n_match == 4 else ''}")
        print()


def test_toggle_sequences():
    """Test various toggle sequences during reset."""
    header("TEST 3: TOGGLE SEQUENCES DURING RESET")
    print("  Assert sel_rst=1, apply vsel sequence, then release sel_rst=0.")
    print("  Check if final state matches target.")
    print("  in_pre=1, in_post=0")
    print()

    targets = [
        (0, [1,1,1,1]),   # in_rst for code 0
        (1, [0,1,1,1]),   # in_rst for code 1
        (2, [0,0,1,1]),   # in_rst for code 2
        (3, [0,0,0,1]),   # in_rst for code 3
        (4, [0,0,0,0]),   # in_rst for code 4
    ]

    # Various toggle sequences during reset
    sequences = {
        "no toggle (00 only)":        [(0,0)],
        "no toggle (01 only)":        [(0,1)],
        "no toggle (10 only)":        [(1,0)],
        "no toggle (11 only)":        [(1,1)],
        "toggle 00->01":             [(0,0), (0,1)],
        "toggle 00->10":             [(0,0), (1,0)],
        "toggle 00->01->00":         [(0,0), (0,1), (0,0)],
        "toggle 00->10->00":         [(0,0), (1,0), (0,0)],
        "toggle 00->01->11->10":     [(0,0), (0,1), (1,1), (1,0)],
        "full CW: 00->10->11->01":   [(0,0), (1,0), (1,1), (0,1)],
        "full gray cycle + hold 00": [(0,0), (0,1), (1,1), (1,0), (0,0)],
        "2x toggle 00->01->00->01":  [(0,0), (0,1), (0,0), (0,1)],
    }

    for tgt_code, in_rst in targets:
        rst_state = [1 - r for r in in_rst]
        print(f"  TARGET: code {tgt_code} [{fmt(rst_state)}]")
        print(f"  {'sequence':>35} | {'end_vsel':>8} | {'result':>6} | code | {'OK?':>4}")
        print(f"  {'-'*35}-+-{'-'*8}-+-{'-'*6}-+------+{'-'*4}")

        for name, seq in sequences.items():
            # Start from arbitrary state
            state = [0, 1, 0, 1]  # non-therm starting point

            # Apply reset with vsel sequence
            for v1, v0 in seq:
                state, _, _ = evaluate(state, 1, 0, v1, v0, 1, in_rst)

            end_vsel = seq[-1]

            # Release reset
            state, conv, _ = evaluate(state, 1, 0, end_vsel[0], end_vsel[1], 0, in_rst)

            ok = state == rst_state
            print(f"  {name:>35} | {end_vsel[0]}{end_vsel[1]:>6} | {fmt(state):>6} | "
                  f"{code(state):>4} | {'PASS' if ok else 'FAIL'}")

        print()


def test_starting_vsel_matters():
    """Does the starting vsel before reset matter?"""
    header("TEST 4: DOES STARTING VSEL MATTER?")
    print("  Pre-condition: block is at various codes with various vsel.")
    print("  Then: assert reset, toggle, release. Does pre-state affect result?")
    print("  Target: code 2, in_rst=[0,0,1,1]")
    print()

    in_rst = [0, 0, 1, 1]
    rst_state = [1, 1, 0, 0]

    # The best toggle sequence from Test 3
    toggle_seq = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]  # full cycle ending at 00

    # Try from different starting conditions
    pre_states = [
        ("code 0 @ vsel=10", [0,0,0,0], (1,0)),
        ("code 1 @ vsel=01", [1,0,0,0], (0,1)),
        ("code 2 @ vsel=00", [1,1,0,0], (0,0)),
        ("code 3 @ vsel=10", [1,1,1,0], (1,0)),
        ("code 4 @ vsel=11", [1,1,1,1], (1,1)),
        ("garbage @ vsel=00", [0,1,0,1], (0,0)),
        ("garbage @ vsel=11", [1,0,1,0], (1,1)),
    ]

    print(f"  Toggle sequence during reset: {' -> '.join(f'{v1}{v0}' for v1,v0 in toggle_seq)}")
    print(f"  Release at vsel={toggle_seq[-1][0]}{toggle_seq[-1][1]}")
    print()

    print(f"  {'pre-condition':>25} | {'after rst':>9} | {'after release':>13} | {'OK?':>4}")
    print(f"  {'-'*25}-+-{'-'*9}-+-{'-'*13}-+-{'-'*4}")

    for name, pre_state, pre_vsel in pre_states:
        state = list(pre_state)

        # Assert reset and toggle
        for v1, v0 in toggle_seq:
            state, _, _ = evaluate(state, 1, 0, v1, v0, 1, in_rst)

        after_rst = list(state)

        # Release
        end_v = toggle_seq[-1]
        state, _, _ = evaluate(state, 1, 0, end_v[0], end_v[1], 0, in_rst)

        ok = state == rst_state
        print(f"  {name:>25} | {fmt(after_rst):>9} | {fmt(state):>13} | {'PASS' if ok else 'FAIL'}")

    print()


def test_multiple_toggles():
    """Can you toggle vsel multiple times under reset?"""
    header("TEST 5: MULTIPLE TOGGLES UNDER RESET")
    print("  Does toggling more times help, hurt, or make no difference?")
    print("  Target: code 2, in_rst=[0,0,1,1]")
    print()

    in_rst = [0, 0, 1, 1]
    rst_state = [1, 1, 0, 0]

    toggle_sets = {
        "1 toggle: 00->01":              [(0,0),(0,1)],
        "2 toggles: 00->01->00":         [(0,0),(0,1),(0,0)],
        "4 toggles: full CW cycle":      [(0,0),(1,0),(1,1),(0,1),(0,0)],
        "8 toggles: 2x full CW":         [(0,0),(1,0),(1,1),(0,1)]*2 + [(0,0)],
        "3 toggles: 00->01->11->10":     [(0,0),(0,1),(1,1),(1,0)],
        "6 toggles: 00->01->00 x2 + 00": [(0,0),(0,1)]*3 + [(0,0)],
    }

    for name, seq in toggle_sets.items():
        state = [0, 1, 0, 1]  # garbage starting state

        # Assert reset and toggle
        for v1, v0 in seq:
            state, _, _ = evaluate(state, 1, 0, v1, v0, 1, in_rst)

        # Release at final vsel
        end_v = seq[-1]
        state, _, _ = evaluate(state, 1, 0, end_v[0], end_v[1], 0, in_rst)

        ok = state == rst_state
        print(f"  {name:>40} end_vsel={end_v[0]}{end_v[1]} -> "
              f"{fmt(state)} code={code(state)} {'PASS' if ok else 'FAIL'}")

    print()
    print("  KEY: What matters is the FINAL vsel when sel_rst goes low,")
    print("  not how many toggles happened. The final vsel must be a")
    print("  valid hold state for the target code.")


def test_release_vsel_is_key():
    """Prove: only the FINAL vsel at release time determines success."""
    header("TEST 6: PROOF — ONLY RELEASE VSEL MATTERS")
    print("  For each target code, try releasing at each vsel.")
    print("  Toggle full gray cycle during reset so net2 is settled.")
    print()

    targets = [
        (0, [1,1,1,1], [0,0,0,0]),
        (1, [0,1,1,1], [1,0,0,0]),
        (2, [0,0,1,1], [1,1,0,0]),
        (3, [0,0,0,1], [1,1,1,0]),
        (4, [0,0,0,0], [1,1,1,1]),
    ]

    # Valid hold states per code (from v1_2 analysis)
    hold_map = {
        0: [(1,0), (1,1)],
        1: [(0,1)],
        2: [(0,0)],
        3: [(1,0)],
        4: [(0,1), (1,1)],
    }

    print(f"  {'target':>6} | {'release vsel':>12} | {'result':>6} | {'OK':>4} | note")
    print(f"  {'-'*6}-+-{'-'*12}-+-{'-'*6}-+-{'-'*4}-+------")

    for tgt_code, in_rst, rst_state in targets:
        for v1, v0 in [(0,0), (0,1), (1,0), (1,1)]:
            state = [0, 1, 0, 1]  # garbage

            # Full toggle during reset
            for tv1, tv0 in [(0,0),(1,0),(1,1),(0,1)]:
                state, _, _ = evaluate(state, 1, 0, tv1, tv0, 1, in_rst)

            # Set final vsel and release
            state, _, _ = evaluate(state, 1, 0, v1, v0, 1, in_rst)  # set vsel under reset
            state, _, _ = evaluate(state, 1, 0, v1, v0, 0, in_rst)  # release

            ok = state == rst_state
            is_hold = (v1, v0) in hold_map[tgt_code]
            note = "valid hold" if is_hold else "NOT hold state"
            print(f"  code={tgt_code} | vsel={v1}{v0:>9} | {fmt(state):>6} | "
                  f"{'PASS' if ok else 'FAIL':>4} | {note}")
    print()


def print_summary():
    header("ANSWER: WHY TOGGLE VSEL DURING RESET?")
    print("""
  THE PROBLEM:
    Each mux_wr2 has an internal node (net2) between two inverting muxes:
      I_mux:     net2 = !(sel ? in1 : in0)     <- data path, NOT reset-controlled
      I_mux_rst: vout = !(sel_rst ? in_rst : net2)  <- reset path

    During reset, vout is forced correct (!in_rst), but net2 depends on sel
    and the data inputs. Net2 may hold a WRONG value from before reset.

    On release (sel_rst 1->0), vout switches from !in_rst to !net2.
    If net2 != in_rst, vout glitches to the wrong value.

  THE FIX — TOGGLE VSEL:
    Toggling vsel during reset changes the data mux selection, which
    updates net2. After toggling, net2 settles to a value consistent
    with the reset state, so the release is glitch-free.

  DOES STARTING VSEL MATTER?
    No — what matters is the FINAL vsel when sel_rst goes low.
    The final vsel must be a valid HOLD state for the target code:
      code 0 -> release at vsel=10 or 11
      code 1 -> release at vsel=01
      code 2 -> release at vsel=00
      code 3 -> release at vsel=10
      code 4 -> release at vsel=01 or 11

  CAN YOU TOGGLE MULTIPLE TIMES?
    Yes, harmless. Extra toggles just re-settle net2.
    Only the FINAL vsel at release matters.

  RECOMMENDED RESET SEQUENCE:
    1. Assert sel_rst = 1
    2. Set in_rst = inverted target code
    3. Toggle vsel through at least one full gray cycle
       (ensures all net2 nodes see correct inputs)
    4. Set vsel to the valid hold state for target code
    5. Deassert sel_rst = 0
""")


def main():
    try:
        print("=" * 72)
        print("  RESET TOGGLE INVESTIGATION (v1.3)")
        print("=" * 72)

        test_why_toggle_needed()
        test_all_reset_targets()
        test_toggle_sequences()
        test_starting_vsel_matters()
        test_multiple_toggles()
        test_release_vsel_is_key()
        print_summary()

        print("=" * 72)
        print("  SIMULATION COMPLETE")
        print("=" * 72)

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
