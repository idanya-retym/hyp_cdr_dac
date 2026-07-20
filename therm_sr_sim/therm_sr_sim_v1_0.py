"""
Thermometer MUX Shift Register — Exhaustive Functional Simulation

Block: 4-bit bidirectional thermometer shift register
Cell:  hyp_adc_cdr_daq_mux_wr2 (2:1 mux with async reset, 0.9V SLVT)

Assumed connectivity (from schematic):
    I_mux0: in0=in_pre,       in1=I_mux1.vout,  sel=vsel<1>, rst_val=in_rst0
    I_mux1: in0=I_mux0.vout,  in1=I_mux2.vout,  sel=vsel<0>, rst_val=in_rst1
    I_mux2: in0=I_mux1.vout,  in1=I_mux3.vout,  sel=vsel<1>, rst_val=in_rst2
    I_mux3: in0=I_mux2.vout,  in1=in_post,      sel=vsel<0>, rst_val=in_rst3

    in0 = left neighbor  (RIGHT/UP shift path)
    in1 = right neighbor (LEFT/DOWN shift path)
    sel=0 → in0,  sel=1 → in1
    sel_rst=1 → output forced to in_rst (async reset override)

Gray-coded control vsel<1:0>:
    vsel=10: HOLD  (pairs 0↔1, 2↔3 cross-coupled)
    vsel=01: HOLD  (pairs 1↔2 cross-coupled, 0→in_pre, 3→in_post)
    vsel=00: SHIFT RIGHT / UP  (all select in0 = left neighbor)
    vsel=11: SHIFT LEFT / DOWN (all select in1 = right neighbor)

Usage:
    python therm_sr_sim_v1_0.py
"""

import sys
from typing import List, Tuple, Optional

MAX_ITER = 20  # max iterations for feedback convergence


# ── Mux cell model ──────────────────────────────────────────────────────────

def mux_wr2(in0: int, in1: int, sel: int, sel_rst: int, in_rst: int) -> int:
    """hyp_adc_cdr_daq_mux_wr2: 2-input MUX with async reset.

    sel_rst=1 → vout = in_rst  (async override)
    sel_rst=0, sel=0 → vout = in0
    sel_rst=0, sel=1 → vout = in1
    """
    if sel_rst:
        return in_rst
    return in0 if sel == 0 else in1


# ── 4-bit shift register model ─────────────────────────────────────────────

def evaluate(state: List[int], in_pre: int, in_post: int,
             vsel1: int, vsel0: int, sel_rst: int,
             in_rst: List[int]) -> Tuple[List[int], bool, int]:
    """Evaluate all 4 muxes simultaneously until convergence.

    Returns (new_state, converged, iterations).
    """
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


def fmt(state: List[int]) -> str:
    return "".join(str(b) for b in state)


def is_therm(state: List[int]) -> bool:
    """Check if state is a valid thermometer code (contiguous 1s from left)."""
    saw_zero = False
    for b in state:
        if saw_zero and b == 1:
            return False
        if b == 0:
            saw_zero = True
    return True


# ── Test harness ────────────────────────────────────────────────────────────

def header(title: str):
    print(f"\n{'=' * 72}")
    print(f"  {title}")
    print(f"{'=' * 72}")


def test_reset():
    """Test 1: Reset behavior and 'toggle to stick' requirement."""
    header("TEST 1: RESET BEHAVIOR")

    in_rst = [1, 1, 0, 0]   # reset to therm code=2 (1100)
    print(f"  in_rst = {fmt(in_rst)}  (thermometer code 2)")
    print()

    # 1a: Assert reset
    print("  Step 1: Assert sel_rst=1  (any vsel)")
    for vsel1, vsel0 in [(0, 0), (0, 1), (1, 0), (1, 1)]:
        state = [0, 0, 0, 0]
        s, conv, it = evaluate(state, 1, 0, vsel1, vsel0, 1, in_rst)
        print(f"    vsel={vsel1}{vsel0}, start={fmt(state)} → {fmt(s)}  conv={conv}  "
              f"{'✓ reset applied' if s == in_rst else '✗ UNEXPECTED'}")

    # 1b: Release reset with different vsel (the "toggle to stick" question)
    print()
    print("  Step 2: Release sel_rst=0  (which vsel holds the reset value?)")
    print("  Starting from reset state [1,1,0,0], in_pre=1, in_post=0")
    for vsel1, vsel0 in [(0, 0), (0, 1), (1, 0), (1, 1)]:
        state = list(in_rst)  # start from reset state
        s, conv, it = evaluate(state, 1, 0, vsel1, vsel0, 0, in_rst)
        held = (s == in_rst)
        therm = is_therm(s)
        status = "✓ HELD" if held else ("~ changed but therm" if therm else "✗ CORRUPTED")
        print(f"    vsel={vsel1}{vsel0}: {fmt(state)} → {fmt(s)}  conv={conv} iter={it}  {status}")

    # 1c: Show correct reset sequence
    print()
    print("  CORRECT RESET SEQUENCE:")
    print("    1. Assert sel_rst=1            → outputs forced to in_rst")
    print("    2. Set vsel to HOLD mode       → (find which vsel holds)")
    print("    3. Deassert sel_rst=0          → mux uses hold path, value sticks")
    print("    If vsel is in SHIFT mode when sel_rst deasserts → value LOST!")


def test_hold_states():
    """Test 2: Which vsel combinations produce HOLD for each starting state."""
    header("TEST 2: HOLD STATE ANALYSIS")
    print("  For each vsel, test if output = input (HOLD) across all 5 therm codes")
    print("  in_pre=1 (UP boundary), in_post=0 (DOWN boundary)")
    print()

    therm_codes = [
        [0, 0, 0, 0],  # code 0
        [1, 0, 0, 0],  # code 1
        [1, 1, 0, 0],  # code 2
        [1, 1, 1, 0],  # code 3
        [1, 1, 1, 1],  # code 4
    ]

    print(f"  {'vsel':>6} | {'code':>4} | {'start':>6} → {'end':>6} | {'hold?':>5} | {'conv':>4} | {'iter':>4}")
    print(f"  {'-'*6}-+-{'-'*4}-+-{'-'*6}---{'-'*6}-+-{'-'*5}-+-{'-'*4}-+-{'-'*4}")

    hold_map = {}
    for vsel1, vsel0 in [(0, 0), (0, 1), (1, 0), (1, 1)]:
        vsel_key = f"{vsel1}{vsel0}"
        holds_all = True
        for code_idx, state in enumerate(therm_codes):
            s, conv, it = evaluate(state, 1, 0, vsel1, vsel0, 0, [0]*4)
            held = (s == state)
            if not held:
                holds_all = False
            print(f"  {vsel_key:>6} | {code_idx:>4} | {fmt(state):>6} → {fmt(s):>6} | "
                  f"{'YES' if held else 'NO':>5} | {conv!s:>4} | {it:>4}")
        hold_map[vsel_key] = holds_all
        print()

    print("  SUMMARY:")
    for vsel, holds in hold_map.items():
        print(f"    vsel={vsel}: {'HOLD for all codes ✓' if holds else 'NOT a universal hold state'}")


def test_shift_right():
    """Test 3: Shift RIGHT (UP) — boundary moves right, more 1s."""
    header("TEST 3: SHIFT RIGHT (UP) — vsel=00 (all select in0 = left neighbor)")
    print("  in_pre=1 (feeds 1 from left), in_post=0")
    print()

    therm_codes = [
        [0, 0, 0, 0],
        [1, 0, 0, 0],
        [1, 1, 0, 0],
        [1, 1, 1, 0],
        [1, 1, 1, 1],
    ]

    print(f"  {'start':>6} → {'after vsel=00':>12} | {'therm?':>6} | {'conv':>4} | {'shift?':>6}")
    print(f"  {'-'*6}---{'-'*12}-+-{'-'*6}-+-{'-'*4}-+-{'-'*6}")

    for code_idx, state in enumerate(therm_codes):
        s, conv, it = evaluate(state, 1, 0, 0, 0, 0, [0]*4)
        therm = is_therm(s)
        expected_up = therm_codes[min(code_idx + 1, 4)]
        shifted = (s == expected_up)
        print(f"  {fmt(state):>6} → {fmt(s):>12} | {therm!s:>6} | {conv!s:>4} | "
              f"{'✓ +1' if shifted else ('✓ sat' if code_idx == 4 and s == state else '✗')}")

    print()
    print("  NOTE: vsel=00 makes entire chain transparent (combinational).")
    print("  All stages resolve in one pass — data floods from in_pre.")
    print("  For SINGLE-BIT shift, must use 2-phase sequence (see Test 6).")


def test_shift_left():
    """Test 4: Shift LEFT (DOWN) — boundary moves left, fewer 1s."""
    header("TEST 4: SHIFT LEFT (DOWN) — vsel=11 (all select in1 = right neighbor)")
    print("  in_pre=1, in_post=0 (feeds 0 from right)")
    print()

    therm_codes = [
        [0, 0, 0, 0],
        [1, 0, 0, 0],
        [1, 1, 0, 0],
        [1, 1, 1, 0],
        [1, 1, 1, 1],
    ]

    print(f"  {'start':>6} → {'after vsel=11':>12} | {'therm?':>6} | {'conv':>4} | {'shift?':>6}")
    print(f"  {'-'*6}---{'-'*12}-+-{'-'*6}-+-{'-'*4}-+-{'-'*6}")

    for code_idx, state in enumerate(therm_codes):
        s, conv, it = evaluate(state, 1, 0, 1, 1, 0, [0]*4)
        therm = is_therm(s)
        expected_dn = therm_codes[max(code_idx - 1, 0)]
        shifted = (s == expected_dn)
        print(f"  {fmt(state):>6} → {fmt(s):>12} | {therm!s:>6} | {conv!s:>4} | "
              f"{'✓ -1' if shifted else ('✓ sat' if code_idx == 0 and s == state else '✗')}")

    print()
    print("  NOTE: Same as vsel=00 — full chain transparent, floods from in_post.")


def test_state_transitions():
    """Test 5: Full state transition table for all vsel from all therm codes."""
    header("TEST 5: COMPLETE STATE TRANSITION TABLE")
    print("  in_pre=1, in_post=0, sel_rst=0")
    print()

    therm_codes = [
        [0, 0, 0, 0],
        [1, 0, 0, 0],
        [1, 1, 0, 0],
        [1, 1, 1, 0],
        [1, 1, 1, 1],
    ]

    vsel_combos = [(0, 0), (0, 1), (1, 0), (1, 1)]

    print(f"  {'start':>6} | {'vsel=00':>8} | {'vsel=01':>8} | {'vsel=10':>8} | {'vsel=11':>8}")
    print(f"  {'-'*6}-+-{'-'*8}-+-{'-'*8}-+-{'-'*8}-+-{'-'*8}")

    for state in therm_codes:
        row = f"  {fmt(state):>6} |"
        for v1, v0 in vsel_combos:
            s, conv, it = evaluate(state, 1, 0, v1, v0, 0, [0]*4)
            marker = ""
            if not conv:
                marker = " !"
            elif s == state:
                marker = " H"  # hold
            row += f" {fmt(s):>6}{marker} |"
        print(row)

    print()
    print("  Legend: H=hold, !=did not converge (metastability risk)")

    # Also test non-thermometer states
    print()
    print("  NON-THERMOMETER STARTING STATES (error recovery):")
    bad_states = [
        [0, 1, 0, 0],
        [1, 0, 1, 0],
        [0, 1, 0, 1],
        [0, 0, 1, 0],
        [0, 1, 1, 0],
    ]
    print(f"  {'start':>6} | {'vsel=00':>8} | {'vsel=01':>8} | {'vsel=10':>8} | {'vsel=11':>8} | {'therm?'}")
    print(f"  {'-'*6}-+-{'-'*8}-+-{'-'*8}-+-{'-'*8}-+-{'-'*8}-+-------")
    for state in bad_states:
        row = f"  {fmt(state):>6} |"
        any_therm = False
        for v1, v0 in vsel_combos:
            s, conv, it = evaluate(state, 1, 0, v1, v0, 0, [0]*4)
            t = is_therm(s)
            if t:
                any_therm = True
            marker = ""
            if not conv:
                marker = "!"
            row += f" {fmt(s):>6}{marker} |"
        row += f" {'recovers' if any_therm else 'NO'}"
        print(row)


def test_two_phase_shift():
    """Test 6: 2-phase gray-code shift sequences for single-bit UP/DOWN."""
    header("TEST 6: 2-PHASE GRAY-CODE SHIFT SEQUENCES")
    print("  in_pre=1, in_post=0")
    print()

    # UP shift using gray code: HOLD → phase_A → HOLD → phase_B → HOLD
    # Try all possible 2-phase sequences

    sequences = {
        "UP: 10→00→10 (hold→shiftR→hold)": [(1, 0), (0, 0), (1, 0)],
        "UP: 10→00→01→11→10 (full gray)": [(1, 0), (0, 0), (0, 1), (1, 1), (1, 0)],
        "UP: 01→00→01 (hold→shiftR→hold)": [(0, 1), (0, 0), (0, 1)],
        "UP: 10→00→10→11→10 (phase A→B)": [(1, 0), (0, 0), (1, 0), (1, 1), (1, 0)],
        "DN: 10→11→10 (hold→shiftL→hold)": [(1, 0), (1, 1), (1, 0)],
        "DN: 01→11→01 (hold→shiftL→hold)": [(0, 1), (1, 1), (0, 1)],
    }

    therm_codes = [
        [0, 0, 0, 0],
        [1, 0, 0, 0],
        [1, 1, 0, 0],
        [1, 1, 1, 0],
        [1, 1, 1, 1],
    ]

    for seq_name, vsel_seq in sequences.items():
        print(f"  Sequence: {seq_name}")
        seq_str = " → ".join(f"{v1}{v0}" for v1, v0 in vsel_seq)
        print(f"  vsel: {seq_str}")
        print(f"    {'start':>6} → {'end':>6} | {'Δcode':>5} | {'therm?':>6}")
        print(f"    {'-'*6}---{'-'*6}-+-{'-'*5}-+-{'-'*6}")

        for code_idx, init_state in enumerate(therm_codes):
            state = list(init_state)
            for v1, v0 in vsel_seq:
                state, conv, it = evaluate(state, 1, 0, v1, v0, 0, [0]*4)
            end_code = sum(state)
            delta = end_code - code_idx
            therm = is_therm(state)
            print(f"    {fmt(init_state):>6} → {fmt(state):>6} | {delta:>+5} | {therm!s:>6}")
        print()


def test_metastability():
    """Test 7: Identify cross-coupled pair metastability conditions."""
    header("TEST 7: CROSS-COUPLED PAIR ANALYSIS")
    print("  When adjacent muxes form feedback loops, the pair must resolve")
    print("  to a consistent value. If the two muxes held different values")
    print("  before pairing, there is a metastability risk.")
    print()

    # Test: what happens when we form a pair from mismatched states?
    print("  Scenario: Force mismatch via reset, then release to hold")
    print()

    # Create non-matching states and see if pairs resolve
    test_cases = [
        ("Pair 0↔1 mismatch (0 vs 1)", [0, 1, 0, 0], (1, 0)),
        ("Pair 0↔1 mismatch (1 vs 0)", [1, 0, 0, 0], (1, 0)),
        ("Pair 2↔3 mismatch (0 vs 1)", [0, 0, 0, 1], (1, 0)),
        ("Pair 2↔3 mismatch (1 vs 0)", [0, 0, 1, 0], (1, 0)),
        ("Pair 1↔2 mismatch (0 vs 1)", [0, 0, 1, 0], (0, 1)),
        ("Pair 1↔2 mismatch (1 vs 0)", [0, 1, 0, 0], (0, 1)),
    ]

    print(f"  {'case':>35} | {'vsel':>4} | {'start':>6} → {'end':>6} | {'conv':>4} | {'iter':>4} | {'note'}")
    print(f"  {'-'*35}-+-{'-'*4}-+-{'-'*6}---{'-'*6}-+-{'-'*4}-+-{'-'*4}-+------")

    for name, state, (v1, v0) in test_cases:
        s, conv, it = evaluate(state, 1, 0, v1, v0, 0, [0]*4)
        note = ""
        if not conv:
            note = "⚠ METASTABLE — oscillates!"
        elif it > 1:
            note = f"resolved after {it} iterations"
        else:
            note = "clean"
        print(f"  {name:>35} | {v1}{v0:>3} | {fmt(state):>6} → {fmt(s):>6} | {conv!s:>4} | {it:>4} | {note}")


def test_boundary_saturation():
    """Test 8: Saturation — what happens at code 0 and code 4."""
    header("TEST 8: BOUNDARY SATURATION")
    print("  What happens when trying to shift UP from code 4 (all 1s)")
    print("  or DOWN from code 0 (all 0s)?")
    print()

    # UP from full
    state_full = [1, 1, 1, 1]
    sequences_up = [
        ("vsel=00 (shift R)", [(0, 0)]),
        ("10→00→10", [(1, 0), (0, 0), (1, 0)]),
    ]

    for name, seq in sequences_up:
        state = list(state_full)
        for v1, v0 in seq:
            state, conv, it = evaluate(state, 1, 0, v1, v0, 0, [0]*4)
        clipped = (state == state_full)
        print(f"  UP from {fmt(state_full)}: {name:>20} → {fmt(state)}  "
              f"{'✓ clipped (safe)' if clipped else '✗ changed!'}")

    print()

    # DOWN from empty
    state_empty = [0, 0, 0, 0]
    sequences_dn = [
        ("vsel=11 (shift L)", [(1, 1)]),
        ("10→11→10", [(1, 0), (1, 1), (1, 0)]),
    ]

    for name, seq in sequences_dn:
        state = list(state_empty)
        for v1, v0 in seq:
            state, conv, it = evaluate(state, 1, 0, v1, v0, 0, [0]*4)
        clipped = (state == state_empty)
        print(f"  DN from {fmt(state_empty)}: {name:>20} → {fmt(state)}  "
              f"{'✓ clipped (safe)' if clipped else '✗ changed!'}")


def test_reset_sequences():
    """Test 9: Full reset sequences — correct vs. incorrect."""
    header("TEST 9: RESET SEQUENCES — CORRECT vs INCORRECT")
    in_rst = [1, 1, 0, 0]
    print(f"  Target reset state: {fmt(in_rst)}")
    print()

    sequences = [
        ("CORRECT: rst=1, vsel=10(hold), rst=0",
         [(1, 0, 1), (1, 0, 0)]),
        ("CORRECT: rst=1, vsel=01(hold), rst=0",
         [(0, 1, 1), (0, 1, 0)]),
        ("WRONG: rst=1, vsel=00(shiftR), rst=0",
         [(0, 0, 1), (0, 0, 0)]),
        ("WRONG: rst=1, vsel=11(shiftL), rst=0",
         [(1, 1, 1), (1, 1, 0)]),
        ("WRONG: rst=1 only (never release → always overridden)",
         [(0, 0, 1)]),
    ]

    for name, steps in sequences:
        state = [0, 0, 0, 0]
        for v1, v0, rst in steps:
            state, conv, it = evaluate(state, 1, 0, v1, v0, rst, in_rst)
        held = (state == in_rst)
        print(f"  {name}")
        print(f"    Result: {fmt(state)}  {'✓ CORRECT' if held else '✗ LOST reset value!'}")
        print()


def print_risks():
    """Print risk analysis and verification recommendations."""
    header("RISK ANALYSIS")
    print("""
  1. METASTABILITY AT PAIR FORMATION
     When cross-coupled pairs reform (vsel transition), if the two muxes
     held different values, the pair must fight to resolve. In real silicon,
     this depends on parasitic capacitance and drive strength.
     Risk: output could settle to wrong value or oscillate.
     Mitigation: ensure shift sequences only change 1 bit of boundary
     per step, so pairs always reform from consistent values.

  2. RESET RELEASE TIMING
     sel_rst deassertion MUST happen when vsel is in HOLD mode.
     If sel_rst deasserts during SHIFT mode, the reset value is immediately
     overwritten by the shift input (in_pre or in_post).
     Risk: reset value lost → wrong initial DAC code → CDR loop starts
     at wrong frequency.

  3. COMBINATIONAL SHIFT-THROUGH
     vsel=00 or vsel=11 makes the ENTIRE chain transparent.
     Data floods from boundary (in_pre or in_post) through all stages.
     This is NOT a single-bit shift — it's a full reset to all-1s or all-0s.
     Risk: if used directly, always jumps to code 0 or code 4, never ±1.
     Must use 2-phase gray-code sequence for single-bit steps.

  4. GRAY CODE VIOLATION
     If vsel transitions change 2 bits simultaneously (e.g., 10→01),
     there's a brief state where both sels are at an intermediate value,
     potentially causing a glitch or race condition.
     Risk: momentary wrong shift direction → corrupted thermometer code.
     Mitigation: ONLY transition between adjacent gray codes (1-bit change).

  5. NON-THERMOMETER STATE TRAP
     If the register enters a non-thermometer state (e.g., 0101 from noise),
     shift operations may NOT recover to a valid thermometer code.
     Risk: stuck in invalid state → DAC output undefined.
     Mitigation: reset after any detected anomaly. Consider adding a
     thermometer code checker.

  6. BOUNDARY INPUT INTEGRITY
     in_pre MUST always be 1 and in_post MUST always be 0 for correct
     thermometer operation. If these float or glitch:
     Risk: invalid codes injected at boundary → corrupted DAC state.

  7. SINGLE-EVENT UPSET (SEU)
     No redundancy or error correction. A single bit flip in any mux
     output breaks the thermometer code.
     Risk: in radiation environments or with very small devices.
""")


def print_verification():
    """Print verification recommendations."""
    header("VERIFICATION PLAN")
    print("""
  1. FUNCTIONAL VERIFICATION (gate-level sim)
     a. Reset to each valid thermometer code (0-4), verify output matches
     b. UP shift from each code, verify code increments by 1
     c. DOWN shift from each code, verify code decrements by 1
     d. HOLD at each code for 100+ cycles, verify no drift
     e. Direction reversal: UP→DOWN→UP, verify clean transition
     f. Saturation: UP from code 4, DOWN from code 0 → verify clip

  2. TIMING VERIFICATION
     a. sel_rst setup/hold relative to vsel transitions
     b. vsel pulse width minimum (transparent phase must be long enough
        for mux to resolve)
     c. vsel non-overlap (between phases): verify no simultaneous
        transparent windows in adjacent stages
     d. Propagation delay: in_pre/in_post → vout settled

  3. METASTABILITY ANALYSIS
     a. Monte Carlo with process variation: does the cross-coupled pair
        always resolve correctly?
     b. Vary vsel transition slopes: at what rise/fall time does the
        pair fail to resolve?
     c. Post-layout with extracted parasitics: verify pair resolution
        under worst-case RC

  4. STRESS TESTS
     a. Rapid UP/DOWN toggling (max rate) — no code corruption
     b. Random vsel sequences — should never produce non-therm code
        (if it does, identify the illegal sequence)
     c. Supply noise injection during hold — verify state retention
     d. Temperature corners: verify hold and shift at -40°C and 125°C

  5. EQUIVALENCE / FORMAL
     a. Formally prove: starting from any valid therm code, the output
        after any legal vsel sequence is always a valid therm code
     b. Prove: no legal sequence can produce code > 4 or < 0
     c. Prove: HOLD sequences are truly non-modifying

  6. SILICON VALIDATION
     a. Scan chain or direct probe of thermometer outputs
     b. Sweep all codes via shift, measure DAC output at each
     c. Verify reset to mid-code with scope on analog output
     d. High-speed UP/DOWN toggle, check for glitch energy on analog out
""")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    try:
        print("=" * 72)
        print("  THERMOMETER MUX SHIFT REGISTER — EXHAUSTIVE SIMULATION")
        print("  Block: hyp_adc_cdr_daq_mux_wr2 × 4")
        print("  Assumed: 4 therm bits, in0=left, in1=right, gray-coded vsel<1:0>")
        print("=" * 72)

        test_reset()
        test_hold_states()
        test_shift_right()
        test_shift_left()
        test_state_transitions()
        test_two_phase_shift()
        test_metastability()
        test_boundary_saturation()
        test_reset_sequences()
        print_risks()
        print_verification()

        print("=" * 72)
        print("  SIMULATION COMPLETE")
        print("=" * 72)

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
