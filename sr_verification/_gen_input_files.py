"""Generate input stimulus and expected output files for SR chain verification."""
import sys

MAX_ITER = 50

def mux_wr2(in0, in1, sel, sel_rst, in_rst):
    if sel_rst:
        return 1 - in_rst
    return in1 if sel else in0

def evaluate_unit(state, in_pre, in_post, vsel1, vsel0, sel_rst, in_rst):
    s = list(state)
    for _ in range(MAX_ITER):
        n = [0] * 4
        n[0] = mux_wr2(in_pre, s[1], vsel1, sel_rst, in_rst)
        n[1] = mux_wr2(s[0],  s[2], vsel0, sel_rst, in_rst)
        n[2] = mux_wr2(s[3],  s[1], vsel1, sel_rst, in_rst)
        n[3] = mux_wr2(in_post, s[2], vsel0, sel_rst, in_rst)
        if n == s:
            return n
        s = n
    return s

def evaluate_chain(states, vsel1, vsel0, sel_rst, vin_rst_b):
    n_units = len(states)
    s = [list(u) for u in states]
    for _ in range(MAX_ITER * n_units):
        new_s = [None] * n_units
        changed = False
        for i in range(n_units):
            in_pre = 1 if i == 0 else s[i-1][3]
            in_post = 0 if i == n_units - 1 else s[i+1][0]
            new_s[i] = evaluate_unit(s[i], in_pre, in_post, vsel1, vsel0, sel_rst, vin_rst_b[i])
            if new_s[i] != s[i]:
                changed = True
        s = new_s
        if not changed:
            break
    return [tuple(u) for u in s]

CW = [(1,1),(0,1),(0,0),(1,0)]
CCW = [(1,1),(1,0),(0,0),(0,1)]

def vsel_to_decimal(v1, v0):
    return v1 * 2 + v0

N_UNITS = 64
vin_rst_b = [0]*32 + [1]*32

def run_sequence(step_list):
    states = [(0,0,0,0)] * N_UNITS
    states = evaluate_chain(states, 1, 1, 1, vin_rst_b)
    states = evaluate_chain(states, 1, 1, 0, vin_rst_b)
    vsel1, vsel0 = 1, 1

    MONITOR = [30, 31, 32, 33]

    results = []

    def get_decimal(states):
        # 16 bits: vout0..3 of units 30,31,32,33 → single decimal
        # unit30 = bits 0-3 (LSB), unit33 = bits 12-15 (MSB)
        val = 0
        bit_pos = 0
        for u in MONITOR:
            for b in states[u]:
                val += b * (1 << bit_pos)
                bit_pos += 1
        return val

    results.append((vsel_to_decimal(vsel1, vsel0), get_decimal(states)))

    for direction in step_list:
        curr = (vsel1, vsel0)
        if direction == 'cw':
            idx = CW.index(curr)
            vsel1, vsel0 = CW[(idx + 1) % 4]
        else:
            idx = CCW.index(curr)
            vsel1, vsel0 = CCW[(idx + 1) % 4]
        states = evaluate_chain(states, vsel1, vsel0, 0, vin_rst_b)
        results.append((vsel_to_decimal(vsel1, vsel0), get_decimal(states)))

    return results

# === Main stimulus sequence ===
main_steps = []
main_steps += ['cw'] * 8
main_steps += ['ccw'] * 4
main_steps += ['ccw'] * 12
main_steps += ['cw'] * 2
main_steps += ['cw'] * 10
for _ in range(4):
    main_steps += ['ccw', 'cw']
main_steps += ['cw'] * 8
main_steps += ['ccw'] * 20
main_steps += ['cw', 'ccw'] + ['cw'] * 3

main_results = run_sequence(main_steps)
print(f'Main: {len(main_results)} lines')

# === Stress sequence ===
stress_steps = []
# Test 1: Boundary oscillation at 128/129
for _ in range(10):
    stress_steps += ['cw', 'ccw']
# Test 2: Reversal at every vsel state
stress_steps += ['cw', 'ccw', 'cw', 'cw', 'ccw', 'cw', 'cw', 'ccw', 'cw', 'cw', 'ccw']
# Test 3: Multi-unit cross + snap back
stress_steps += ['cw'] * 17 + ['ccw'] * 17
# Test 4: Full intra-unit pair sweep
stress_steps += ['cw'] * 4 + ['ccw'] * 4
# Test 5: Reversal at each intra-unit code
stress_steps += ['cw', 'ccw', 'cw', 'cw', 'ccw', 'cw', 'cw', 'ccw', 'cw', 'cw', 'ccw', 'cw']
# Test 6: Double reversal patterns
stress_steps += ['cw', 'ccw', 'ccw', 'cw', 'cw', 'ccw', 'ccw', 'ccw', 'cw']
# Test 7: Navigate to 124 then oscillate
# Global code = 128 + net steps taken
net_steps = sum(1 if s == 'cw' else -1 for s in stress_steps)
curr_code = 128 + net_steps
steps_to_124 = curr_code - 124
stress_steps += ['ccw'] * steps_to_124
for _ in range(8):
    stress_steps += ['ccw', 'cw']

stress_results = run_sequence(stress_steps)
print(f'Stress: {len(stress_results)} lines')

# === Write files ===
with open('input_files/vsel_stimulus.txt', 'w') as f:
    for vsel_dec, _ in main_results:
        f.write(f'{vsel_dec}\n')

with open('input_files/expected_outputs.txt', 'w') as f:
    for _, val in main_results:
        f.write(f'{val}\n')

with open('input_files/vsel_stress.txt', 'w') as f:
    for vsel_dec, _ in stress_results:
        f.write(f'{vsel_dec}\n')

with open('input_files/expected_stress.txt', 'w') as f:
    for _, val in stress_results:
        f.write(f'{val}\n')

print('Done. Expected files: one decimal per line (16-bit word from units 30-33, range 0-65535).')
print(f'  expected_outputs.txt: {len(main_results)} lines')
print(f'  expected_stress.txt: {len(stress_results)} lines')
