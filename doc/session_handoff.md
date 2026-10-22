# hyp_cdr_dac - session handoff (Windows -> Linux), 2026-10-22

Context for continuing work in a new Claude session. To start, tell Claude:
"read doc/session_handoff.md and continue from there".

## 1. Project
- HYP Gen1 CDR DAC: 8-bit, fully thermometric, differential PMOS current-steering DAC driving the CDR VCO. TSMC 2nm.
- 256 unit current sources (each = 4 sub-sources, one SR unit of 4 bits), 257 levels (code 0..256).
- Digital: thermometer shift register (SR) of mux_wr2 cells, driven by gray-code vsel<1:0> plus UP/DN.
  - CW (UP): 3 -> 1 -> 0 -> 2 -> 3. CCW (DN): 3 -> 2 -> 0 -> 1 -> 3.
  - Reset to mid-code with vsel=3 held, one shared vin_rst_b.
- Repo map:
  - dac_sigma_vs_dnl.py, dac_mc_dnl/: mismatch vs DNL/INL
  - therm_sr_sim/, sr_verification/, ocean/: SR model, Spectre TB, checkers
  - resistor_bank/: diff, CM and bias resistor banks (3k unit)
  - noise_freq_reduce/: frequency list reduction for Spectre noise
  - vout_gen/: prints the bus names
  - doc/: spec (generate_spec.py), SR block doc (generate_sr_doc.py), system_questions.md

## 2. Working rules (user preferences)
- Scripts: parameters in a block at the top, no CLI args (edit and press Run). ASCII-only output. Text files read by Spectre use LF endings. Output files are named after their input files.
- Versioning: one unversioned script with a `Version:` line in its header. Old `_vX_Y` files go to `<tool>/tmp/`. Git holds the history.
  - Converted so far: noise_freq_reduce, resistor_bank, sr_verification.
  - Still on the old `_vX_Y` style: dac_mc_dnl, therm_sr_sim, ocean, vout_gen. Ask before converting these.
- When Claude asks questions, it stops and waits for the answers.
- If a file is locked (open in Word or another app) or read-only, Claude stops and tells the user to close it.
- Spec changes:
  1. Edit doc/generate_spec.py (never the docx) and add a revision-history row.
  2. Regenerate the docx, then commit and push.
  3. Copy the docx to the SharePoint CDR_DAC folder and put the previous version in `CDR_DAC/spec_versions/` as `HYP_Gen1_CDR_DAC_Spec_<date>_<hash>_v0.X.docx`.
  - The SharePoint folder is Windows-only: `C:\Users\idanya\Retym, Inc\Retym, Inc. - Documents\Engineering\Analog\Projects\G3\Clocking\CDR\CDR_DAC`.

## 3. Spec state (v0.7, docx committed 78fb848)
- V_FS 1000 mVpp diff +-5%, self spec. LSB 3.906 mV. VCM 350 mV +-5%.
- DNL +-0.3 LSB including VCO error (VCO share still open). INL, PSRR: TBD, report only.
- Supplies 1.14/1.2/1.26 V and 0.85/0.9/0.95 V. Temperature -10 / 50 & 85 / 110 C.
- R_L 50 ohm per side +-20%; the current tracks R_L, so V_FS stays constant. C_L TBD. Input clock 1 GHz max.
- Removed: I_FS/I_LSB rows (internal only: ~10 mA FS, ~39 uA per unit), gain error, full-scale settling.
- Still TBD: 1-LSB settling (to 2 tau), power per supply, noise table (user will provide).

## 4. Analog notes
- Unit cell: PMOS current source + cascode + switch pair, all the same Vt flavour. LVT/ULVT recommended.
  - Headroom at Vout = 600 mV is 450 mV for the 3 devices.
- Mismatch scales as 1/sqrt(WL): going from 15% to 5% needs 9x the area.
- Bias: an amp loop sets I_ref = V_ref/R through a reference PMOS that drives `vcur` to all cell gates.
  - The reference PMOS thermal noise dominates and adds coherently across cells (scales with mirror ratio N).
  - A series-R gate filter was rejected (gate-leakage IR drop gives a mirror error).
  - Remaining options: lower N, raise Vov (reference and cells together), source degeneration, R inside the loop (amp -> R -> common gate node -> C to the PMOS source rail), or C only on vcur. Use MOM/MIM caps, not MOS caps.

## 5. sr_verification review (2026-10-22), waiting for the user to pick fixes
Done:
- sr_chain_checker_v1_0.py moved to sr_verification/tmp/.
- Unversioned copy sr_chain_checker.py created (Version: v1.0).

Flows:
- **A:** tb_sr_chain4.scs (4 units, codes 0-16) checked by sr_chain_checker.py (CSV or raw file, or `--self-test`).
- **B (the one in use):** _gen_input_files.py (64-unit model, reset 128) writes input_files/*.txt. shift_reg_checker.ocn compares the sim with these files in ADE, with rst_val 0-5 selecting the file.
  - The committed files match a regeneration.

Bugs found:
1. OCEAN uses `rst_val` on line 17, before `rst_val = VAR("rst_val")` on line 31.
2. In tb_sr_chain4.scs the vsel PWL has one point per 2 ns, so every edge is a 2 ns ramp and t_rise=50p is never used. The timing check is about 1 ns off.
3. The checker's saturation checks always pass (`<=16` and `>=0`). CCW saturation samples from T_SAT_CCW_END instead of T_CCW_END, so it samples during reset 3.
4. In the checker, a missing signal counts as 0 (a wrong signal name passes "reset to 0").
5. The checker prints the unicode ticks and crosses, which crash on a Windows console. `--vth` is unused, and `--format psf` is accepted but not implemented.

Gaps:
6. tb_sr_chain4.scs rebuilds the unit from mux_wr2 inside the TB and the netlist include is commented out, so it doesn't test the real hyp_adc_cdr_dac_sr_unit.
7. input_files/README still describes the 128-unit setup. Current: 64 units, monitored units 30-33, bit 0 = u30 vout0, first expected value 255.
8. expected_stimulus.txt (used by OCEAN for rst_val 2) is a duplicate of expected_outputs.txt (written by the generator). The rst_val 0/1 files (unit_*_expected.txt) are not in the repo.
9. OCEAN samples 100 ps after the clock edge. To check settling within a 1 GHz cycle, sample just before the next edge. Also check that i=1 lines up with expected line 1.
10. The model is copied into both Python scripts, has zero delay, and can't catch races. The generator writes CRLF on Windows.

Suggested fixes, in priority order:
1. OCEAN: move rst_val up, add t_sample, output n_lines_file/n_lines_sim.
2. Drop expected_stimulus.txt; handle the rst_val 0/1 files.
3. Rewrite the README.
4. Checker v1.1: ASCII output, settings at the top, error on missing signals, real saturation checks.
5. TB: two PWL points per edge, include the real unit, or drop flow A.
6. Shared model module, LF output, paths relative to the script.
7. Optional: corners/MC at 1 GHz, glitch check.

## 6. Other open items
- Old GitHub Copilot "Mater chat" (Jul-Oct 2026) exists on Windows only:
  - Session log: `%APPDATA%\Code\User\workspaceStorage\afe5378905cac7339bd6b06e710217e7\chatSessions\a28a384c-3461-42ce-9236-c5ac1b5c8d85.jsonl`
  - A markdown transcript was made but not yet saved anywhere permanent.
- doc/system_questions.md: DAC-to-digital interface questions are still unanswered.
