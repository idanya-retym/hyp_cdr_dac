# DAC ↔ Digital Interface — System Questions

## Q1: Step Size Requirement

**Question:** Can the CDR digital loop filter work with ±1 LSB steps only, or is a larger step jump required (e.g., ±2, ±4, ±8)?

- If ±1 only → pure async pulse interface (2 wires, minimum latency)
- If variable step needed → defines whether we need burst pulses, parallel step bus, or hybrid sync/async

**Context:** With a 7-bit thermometric DAC (127 codes), worst-case full-scale traversal at ±1 LSB/pulse = 127 pulses. At 500 ps pulse spacing that's ~63 ns. Is this acceptable for frequency acquisition?

**Answer:**

---

## Q2: Frequency Acquisition Mode

**Question:** Does the CDR have a separate frequency acquisition mode (FLL) that needs fast large jumps, or is it pure bang-bang tracking from the start?

- If FLL exists → may need a parallel load / preset to mid-code or target code
- If pure BBPD → ±1 step with fast pulse rate may suffice

**Answer:**

---

## Q3: Pulse Rate / Update Rate

**Question:** What is the maximum rate at which the digital will send UP/DN pulses? (related to PD clock, CTLE adaptation clock, etc.)

- Defines the minimum pulse spacing the DAC must support
- Defines effective DAC bandwidth

**Answer:**

---

## Q4: Initial DAC State on Power-Up

**Question:** What code should the DAC start at after reset? Mid-code (64)? Min (0)? Programmable?

- Affects whether we need a parallel preset mechanism
- Mid-code start reduces acquisition time by 2×

**Answer:**

---

## Q5: Saturation Behavior

**Question:** When the DAC hits code 0 or 127, what should happen?

- Option A: Clip (ignore further pulses in that direction)
- Option B: Flag to digital (overflow/underflow status bit)
- Option C: Both — clip + flag

**Answer:**

---

## Q6: UP/DN Mutual Exclusivity

**Question:** Does the digital guarantee that UP and DN are never asserted simultaneously?

- If yes → simple implementation
- If no → need priority/arbitration logic in the DAC

**Answer:**

---

## Q7: Feedback to Digital

**Question:** Does the digital need to read back the current DAC code? (e.g., for diagnostics, calibration, or saturation detection)

- If yes → need a readback path (adds clock-domain crossing if async)
- If no → fully one-directional interface

**Answer:**

---

## Q8: Clock Domain Relationship

**Question:** Are the digital loop filter and DAC in the same clock domain, or is the DAC truly free-running (async)?

- Same domain → synchronous interface is trivial, async optional for latency
- Different domains → async interface avoids synchronizer penalty

**Answer:**

---

## Q9: Supply / IO Levels

**Question:** What voltage domain does the digital interface run in? Same as DAC supply or separate?

- If different → need level shifters on UP/DN lines (adds delay)
- If same → direct connection

**Answer:**

---

## Q10: Noise Budget on Interface Lines

**Question:** How close do the UP/DN signal lines route to the VCO / sensitive analog? Any shielding constraints?

- Defines whether UP/DN should be differential (more robust, 4 wires) or single-ended (2 wires, simpler)

**Answer:**

---
