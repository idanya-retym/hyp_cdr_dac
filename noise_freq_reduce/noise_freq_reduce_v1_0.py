#!/usr/bin/env python3
"""
noise_freq_reduce_v1_0.py

Reduce a dense PSD/noise sweep (frequency, value) into the *smallest* list of
frequencies that still reconstructs the noise curve within a chosen tolerance,
then write those frequencies (comma separated, one line) to a .txt file for
Spectre to simulate on.

Method
------
Adaptive Douglas-Peucker (a.k.a. Ramer-Douglas-Peucker) curve simplification
using a **vertical-error** criterion:

  * Start with just the two endpoints.
  * Between any two kept points, find the sample whose value deviates most from
    the straight line connecting them (measured in the chosen X/Y domain).
  * If that deviation exceeds TOLERANCE, keep the sample and recurse; otherwise
    drop every sample in that span.

Consequences:
  * A noise spike deviates a lot from its neighbours' interpolation, so it is
    ALWAYS kept (as long as it is taller than TOLERANCE).
  * A slowly-changing / flat region is well approximated by a straight line, so
    almost all of its points are dropped.

Axes can be treated as log or linear independently, because for noise the
"accuracy" you care about is usually error in dB over log-frequency.

Run from Python. Edit the CONFIG block below, then execute.
"""

import os
import sys
import logging

import numpy as np

# ----------------------------------------------------------------------------
# CONFIG - edit these
# ----------------------------------------------------------------------------

# Input CSV: 2 columns (freq_Hz, psd_value). First row is a header and skipped.
INPUT_FILE = r"C:\Users\idanya\OneDrive - Retym, Inc\Desktop\vcoldo_wdc2dc - Copy.csv"

# Output text file (comma separated frequencies, single line).
OUTPUT_FILE = r"C:\Users\idanya\OneDrive - Retym, Inc\Desktop\spectre_noise_freqs.txt"

# --- Frequency range to keep (Hz). Points outside are ignored. ---
START_FREQ = 0.0          # lower bound (Hz). 0 = no lower bound.
STOP_FREQ = 1.0e9         # upper bound (Hz).

# --- Accuracy domain (try both to see what suits your data) ---
# X_LOG: treat frequency axis as log (True, recommended for noise) or linear.
# Y_LOG: treat value axis as dB = 10*log10(value) (True) or raw linear value.
X_LOG = True
Y_LOG = True

# --- TOLERANCE: the knob to play with. ---
# Meaning depends on Y_LOG:
#   Y_LOG = True  -> tolerance is in dB   (e.g. 0.25 means "within 0.25 dB").
#   Y_LOG = False -> tolerance is in the raw linear units of the value column.
# Smaller = more points / more accurate. Larger = fewer points.
TOLERANCE = 0.25

# --- Optional hard cap on number of output frequencies. ---
# None            -> no cap; use TOLERANCE as-is (as few as possible for that tol).
# an integer (e.g. 800) -> automatically loosen TOLERANCE until the result fits
#                          within this many points (helps bound sim time).
TARGET_MAX_POINTS = None

# --- Always include the first and last in-range sample. ---
FORCE_ENDPOINTS = True

# --- Output number format for each frequency. ---
# "{:.1f}" -> 1000.0   "{:.0f}" -> 1000   "{:.6g}" -> compact
FREQ_FORMAT = "{:.1f}"

# ----------------------------------------------------------------------------
# End of CONFIG
# ----------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("noise_freq_reduce")

TINY = 1e-300  # guard against log10(0)


def load_csv(path):
    """Load a 2-column (freq, value) CSV, skipping a header row and bad lines."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Input file not found: {path}")

    freqs = []
    vals = []
    bad = 0
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        first = True
        for line_no, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) < 2:
                bad += 1
                continue
            # Take the first two fields as x,y.
            try:
                x = float(parts[0])
                y = float(parts[1])
            except ValueError:
                if first:
                    first = False  # this was the header row
                    continue
                bad += 1
                continue
            first = False
            freqs.append(x)
            vals.append(y)

    if not freqs:
        raise ValueError("No numeric (freq,value) rows were parsed from the file.")
    if bad:
        log.warning("Skipped %d unparparseable/short line(s).", bad)

    f = np.asarray(freqs, dtype=float)
    v = np.asarray(vals, dtype=float)

    # Sort by frequency ascending (defensive) and drop duplicate freqs.
    order = np.argsort(f, kind="mergesort")
    f = f[order]
    v = v[order]
    keep = np.concatenate(([True], np.diff(f) > 0))
    if not keep.all():
        log.warning("Dropped %d duplicate-frequency row(s).", int((~keep).sum()))
    return f[keep], v[keep]


def build_axes(f, v):
    """Apply range filtering and the chosen log/linear transforms.

    Returns (freq_in_range, X_transformed, Y_transformed).
    """
    mask = np.ones(f.shape, dtype=bool)
    if START_FREQ and START_FREQ > 0:
        mask &= f >= START_FREQ
    if STOP_FREQ:
        mask &= f <= STOP_FREQ

    if X_LOG:
        mask &= f > 0  # log needs strictly positive frequency

    f = f[mask]
    v = v[mask]
    if f.size < 2:
        raise ValueError("Fewer than 2 samples remain after range/transform filtering.")

    x = np.log10(f) if X_LOG else f.copy()

    if Y_LOG:
        if np.any(v <= 0):
            n_neg = int(np.sum(v <= 0))
            log.warning(
                "%d value(s) <= 0 clamped to a tiny positive number for dB.", n_neg
            )
        y = 10.0 * np.log10(np.maximum(v, TINY))
    else:
        y = v.copy()

    return f, x, y


def douglas_peucker_vertical(x, y, tol):
    """Return a boolean keep-mask over samples using vertical-error DP.

    A sample is kept if it (or a sample it protects) deviates more than `tol`
    from the piecewise-linear reconstruction through the currently kept points.
    Iterative to avoid recursion limits; vectorized per segment via numpy.
    """
    n = x.size
    keep = np.zeros(n, dtype=bool)
    keep[0] = True
    keep[-1] = True

    stack = [(0, n - 1)]
    while stack:
        i0, i1 = stack.pop()
        if i1 <= i0 + 1:
            continue

        x0, y0 = x[i0], y[i0]
        x1, y1 = x[i1], y[i1]
        dx = x1 - x0

        xk = x[i0 + 1:i1]
        yk = y[i0 + 1:i1]
        if dx == 0:
            interp = np.full(xk.shape, y0)
        else:
            interp = y0 + (y1 - y0) * (xk - x0) / dx

        dev = np.abs(yk - interp)
        j = int(np.argmax(dev))
        if dev[j] > tol:
            imax = i0 + 1 + j
            keep[imax] = True
            stack.append((i0, imax))
            stack.append((imax, i1))

    return keep


def reconstruct_error(x, y, keep):
    """Max |y - linear_interp_through_kept| over all samples (in Y units)."""
    idx = np.flatnonzero(keep)
    interp = np.interp(x, x[idx], y[idx])
    return float(np.max(np.abs(y - interp)))


def simplify_to_budget(x, y, tol, max_points):
    """Loosen tolerance (geometric search) until kept count <= max_points."""
    keep = douglas_peucker_vertical(x, y, tol)
    if keep.sum() <= max_points:
        return keep, tol

    log.info(
        "Result has %d points > cap %d; loosening tolerance...",
        int(keep.sum()), max_points,
    )
    cur = tol
    for _ in range(60):
        cur *= 1.5
        keep = douglas_peucker_vertical(x, y, cur)
        if keep.sum() <= max_points:
            log.info("Tolerance raised to %.4g to meet the cap.", cur)
            return keep, cur
    log.warning("Could not reach cap even after loosening; returning best effort.")
    return keep, cur


def main():
    try:
        log.info("Reading: %s", INPUT_FILE)
        f_all, v_all = load_csv(INPUT_FILE)
        log.info("Loaded %d samples.", f_all.size)

        f, x, y = build_axes(f_all, v_all)
        log.info(
            "In range [%s, %s] Hz: %d samples. X_LOG=%s Y_LOG=%s TOL=%g%s",
            f"{f[0]:.3g}", f"{f[-1]:.3g}", f.size, X_LOG, Y_LOG, TOLERANCE,
            " dB" if Y_LOG else "",
        )

        if TARGET_MAX_POINTS is not None:
            keep, used_tol = simplify_to_budget(x, y, TOLERANCE, TARGET_MAX_POINTS)
        else:
            keep, used_tol = douglas_peucker_vertical(x, y, TOLERANCE), TOLERANCE

        if FORCE_ENDPOINTS:
            keep[0] = True
            keep[-1] = True

        sel_freqs = f[keep]
        max_err = reconstruct_error(x, y, keep)

        # Write comma-separated single line.
        text = ",".join(FREQ_FORMAT.format(v) for v in sel_freqs)
        out_dir = os.path.dirname(OUTPUT_FILE)
        if out_dir and not os.path.isdir(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")

        reduction = 100.0 * (1.0 - sel_freqs.size / f.size)
        log.info("-" * 60)
        log.info("Kept %d of %d points (%.2f%% reduction).",
                 sel_freqs.size, f.size, reduction)
        log.info("Reconstruction max error: %.4g %s (tolerance %.4g%s).",
                 max_err, "dB" if Y_LOG else "linear", used_tol,
                 " dB" if Y_LOG else "")
        log.info("First freq: %s Hz   Last freq: %s Hz",
                 FREQ_FORMAT.format(sel_freqs[0]), FREQ_FORMAT.format(sel_freqs[-1]))
        log.info("Wrote: %s", OUTPUT_FILE)
        return 0

    except Exception as exc:  # noqa: BLE001 - top-level guard for a CLI tool
        log.error("FAILED: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
