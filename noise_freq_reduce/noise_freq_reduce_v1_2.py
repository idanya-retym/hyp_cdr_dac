#!/usr/bin/env python3
"""
noise_freq_reduce_v1_2.py

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

New in v1.2
-----------
  * INTEGRATED-NOISE ERROR: reports total RMS = sqrt(integral of PSD df) for the
    full curve vs the reduced+interpolated curve, as a percentage. THIS is the
    number to gate on for noise - a local dB error in a deep null barely moves
    total power, whereas a lost spur/hump does. Also shown per row in the sweep.
  * PROTECT_NULLS: optionally also force-keep deep downward excursions (nulls),
    not just upward spurs. Off by default (nulls carry little noise power).

New in v1.1
-----------
  * SMOOTHING: smooth the noise floor for the *drop decision only* so scattery
    flat regions collapse hard while genuine spurs stay protected.
  * SWEEP_TOLERANCES: reduction/error table across several tolerances in one run.
  * PLOT: PNG overlay of kept points on the full curve for visual verification.

Run from Python. Edit the CONFIG block below, then execute.
"""

import os
import sys
import logging

import numpy as np

# ----------------------------------------------------------------------------
# CONFIG - edit these   (values below are the recommended fast+accurate defaults)
# ----------------------------------------------------------------------------

# Input CSV: 2 columns (freq_Hz, psd_value). First row is a header and skipped.
INPUT_FILE = r"C:\Users\idanya\OneDrive - Retym, Inc\Desktop\vcoldo_wdc2dc.csv"

# Output text file (comma separated frequencies, single line).
OUTPUT_FILE = r"C:\Users\idanya\OneDrive - Retym, Inc\Desktop\spectre_noise_freqs.txt"

# --- Frequency range to keep (Hz). Points outside are ignored. ---
START_FREQ = 10e3          # lower bound (Hz). 0 = no lower bound.
STOP_FREQ = 1.0e9          # upper bound (Hz).

# --- Accuracy domain (recommended: log freq, dB value) ---
# X_LOG: treat frequency axis as log (True, recommended for noise) or linear.
# Y_LOG: treat value axis as dB = 10*log10(value) (True) or raw linear value.
X_LOG = True
Y_LOG = True

# --- TOLERANCE: the accuracy floor. Meaning depends on Y_LOG. ---
#   Y_LOG = True  -> tolerance is in dB   (e.g. 0.5 means "within 0.5 dB").
#   Y_LOG = False -> tolerance is in the raw linear units of the value column.
# With TARGET_MAX_POINTS set, this is only the *starting* (tightest) tolerance.
# NOTE for spur-forest data: integrated-noise error is very sensitive here.
# Measured on this dataset: 0.25 -> +1.9% (106k pts), 0.5 -> +5.9% (35k pts),
# 1.0 -> +58% (6.6k pts). Do NOT loosen past ~0.5 if you care about total noise.
TOLERANCE = 0.25

# --- Hard cap on number of output frequencies (bounds Spectre sim time). ---
# None            -> no cap; use TOLERANCE as-is (recommended for this data,
#                    because a small point budget wrecks the noise integral).
# an integer      -> auto-loosen TOLERANCE until the result fits this many points
#                    (WARNING: on spur-forest data a tight cap => huge noise err).
TARGET_MAX_POINTS = None

# --- Always include the first and last in-range sample. ---
FORCE_ENDPOINTS = True

# --- Output number format for each frequency. ---
# "{:.1f}" -> 1000.0   "{:.0f}" -> 1000   "{:.6g}" -> compact
FREQ_FORMAT = "{:.1f}"

# --- Smoothing (affects the DROP decision only, never your written values). ---
# Raw PSD bins scatter randomly, which can look like spikes and block reduction.
# When smoothing is on, flatness is judged against the SMOOTHED floor, so the
# scattery floor collapses hard. Genuine spurs are protected separately: any
# raw sample rising more than SPIKE_THRESHOLD above the smoothed floor is
# force-kept, so real spikes are never lost.
#   "none"        -> no smoothing (v1.0 behaviour: DP on the raw curve).
#   "median"      -> rolling median (robust; best at keeping spikes crisp).
#   "moving_avg"  -> rolling mean (smoother but blurs spikes a little).
SMOOTHING = "median"
SMOOTH_WINDOW = 21         # samples per window (odd number recommended).
# Spike protection when smoothing is on. Units match Y_LOG (dB if Y_LOG=True).
# A raw point kept whenever (raw - smoothed_floor) > SPIKE_THRESHOLD.
SPIKE_THRESHOLD = 3.0
# Also protect deep downward nulls (raw below floor by SPIKE_THRESHOLD)?
# Off by default: nulls carry little noise power, so dropping them is harmless.
PROTECT_NULLS = False

# --- Tolerance sweep: print a table across several tolerances, then exit. ---
# None                      -> normal single run (writes OUTPUT_FILE / plot).
# a list e.g. [0.25,0.5,1.0,2.0] -> just print the table (no output written).
SWEEP_TOLERANCES = None

# --- Reconstruction plot (recommended ON for a final verify run). ---
PLOT = True                # True to save a PNG overlay of kept points.
PLOT_FILE = r"C:\Users\idanya\OneDrive - Retym, Inc\Desktop\spectre_noise_freqs.png"

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

# np.trapz was renamed to np.trapezoid in newer numpy.
_trapezoid = getattr(np, "trapezoid", None) or np.trapz


def load_csv(path):
    """Load a 2-column (freq, value) CSV, skipping a header row and bad lines."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Input file not found: {path}")

    freqs = []
    vals = []
    bad = 0
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        first = True
        for raw in fh:
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
        log.warning("Skipped %d unparseable/short line(s).", bad)

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

    Returns (freq_in_range, X_transformed, Y_transformed, PSD_linear_in_range).
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

    return f, x, y, v


def rolling_stat(y, window, kind):
    """Rolling median or mean with edge-preserving reflection padding."""
    if window is None or window < 3 or kind == "none":
        return y
    w = int(window)
    if w % 2 == 0:
        w += 1
    half = w // 2
    padded = np.pad(y, half, mode="reflect")
    # Sliding window view -> (N, w).
    windows = np.lib.stride_tricks.sliding_window_view(padded, w)
    if kind == "median":
        return np.median(windows, axis=1)
    if kind == "moving_avg":
        return np.mean(windows, axis=1)
    return y


def douglas_peucker_vertical(x, y_decide, tol, force_keep=None):
    """Return a boolean keep-mask using vertical-error DP on `y_decide`.

    `force_keep` is an optional boolean array of samples that must be kept (used
    to protect genuine spikes when the decision curve is smoothed). Forced
    points seed the recursion so their neighbourhoods are refined too.
    Iterative + vectorized per segment.
    """
    n = x.size
    keep = np.zeros(n, dtype=bool)
    keep[0] = True
    keep[-1] = True
    if force_keep is not None:
        keep |= force_keep

    # Seed DP with every consecutive pair of already-kept anchors.
    anchors = np.flatnonzero(keep)
    stack = [(int(a), int(b)) for a, b in zip(anchors[:-1], anchors[1:])]

    while stack:
        i0, i1 = stack.pop()
        if i1 <= i0 + 1:
            continue

        x0 = x[i0]
        x1 = x[i1]
        dx = x1 - x0
        xk = x[i0 + 1:i1]

        y0, y1 = y_decide[i0], y_decide[i1]
        if dx == 0:
            interp = np.full(xk.shape, y0)
        else:
            interp = y0 + (y1 - y0) * (xk - x0) / dx
        dev = np.abs(y_decide[i0 + 1:i1] - interp)

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


def integrated_noise_error(f, x, y, keep):
    """Total-RMS noise error (%) from integrating PSD over frequency.

    Uses the physically-standard estimate a noise integral is built from: linear
    PSD trapezoid over linear frequency, with the reduced curve linearly
    interpolated through the kept samples (exactly what you get when Spectre
    reports PSD only at the kept freqs and you integrate the result). The log/dB
    settings only affect which points are *selected*, not this accuracy check.
    Returns (rms_full, rms_recon, percent_error).
    """
    if Y_LOG:
        psd_full = np.power(10.0, y / 10.0)
    else:
        psd_full = np.asarray(y, dtype=float)

    idx = np.flatnonzero(keep)
    psd_recon = np.interp(f, f[idx], psd_full[idx])

    rms_full = float(np.sqrt(_trapezoid(psd_full, f)))
    rms_recon = float(np.sqrt(_trapezoid(psd_recon, f)))
    if rms_full <= 0:
        return rms_full, rms_recon, float("nan")
    pct = 100.0 * (rms_recon / rms_full - 1.0)
    return rms_full, rms_recon, pct


def simplify_to_budget(x, y_decide, tol, max_points, force_keep=None):
    """Loosen tolerance (geometric search) until kept count <= max_points."""
    keep = douglas_peucker_vertical(x, y_decide, tol, force_keep=force_keep)
    if keep.sum() <= max_points:
        return keep, tol

    log.info(
        "Result has %d points > cap %d; loosening tolerance...",
        int(keep.sum()), max_points,
    )
    cur = tol
    for _ in range(60):
        cur *= 1.5
        keep = douglas_peucker_vertical(x, y_decide, cur, force_keep=force_keep)
        if keep.sum() <= max_points:
            log.info("Tolerance raised to %.4g to meet the cap.", cur)
            return keep, cur
    log.warning("Could not reach cap even after loosening; returning best effort.")
    return keep, cur


def save_plot(path, f, y_raw, keep, y_units):
    """Save an overlay of kept points on the full curve (returns True on success)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001
        log.warning("Plot skipped (matplotlib unavailable: %s).", exc)
        return False

    idx = np.flatnonzero(keep)
    recon = np.interp(f, f[idx], y_raw[idx])

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(f, y_raw, color="0.7", lw=0.8, label=f"full data ({f.size})")
    ax.plot(f, recon, color="tab:blue", lw=1.0,
            label="reconstruction (linear interp)")
    ax.plot(f[idx], y_raw[idx], "o", color="tab:red", ms=3,
            label=f"kept points ({idx.size})")
    if X_LOG:
        ax.set_xscale("log")
    ax.set_xlabel("Frequency [Hz]")
    ax.set_ylabel(f"Value [{y_units}]")
    ax.set_title("noise_freq_reduce: kept frequencies vs full curve")
    ax.grid(True, which="both", ls=":", alpha=0.5)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()

    out_dir = os.path.dirname(path)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    log.info("Wrote plot: %s", path)
    return True


def run_sweep(f, x, y_decide, y_raw, n_total, tolerances, y_units, force_keep=None):
    """Print a reduction / dB-error / integrated-noise-error table."""
    log.info("Tolerance sweep (no output file written):")
    header = (f"{'tolerance':>10} | {'kept':>8} | {'reduction':>9} | "
              f"{'max dB err':>10} | {'noise err %':>11}")
    log.info(header)
    log.info("-" * len(header))
    for tol in tolerances:
        keep = douglas_peucker_vertical(x, y_decide, tol, force_keep=force_keep)
        if FORCE_ENDPOINTS:
            keep[0] = True
            keep[-1] = True
        kept = int(keep.sum())
        red = 100.0 * (1.0 - kept / n_total)
        err = reconstruct_error(x, y_raw, keep)
        _, _, npct = integrated_noise_error(f, x, y_raw, keep)
        log.info("%10.4g | %8d | %8.2f%% | %8.4g %s | %+10.4f%%",
                 tol, kept, red, err, y_units, npct)


def main():
    try:
        y_units = "dB" if Y_LOG else "linear"

        log.info("Reading: %s", INPUT_FILE)
        f_all, v_all = load_csv(INPUT_FILE)
        log.info("Loaded %d samples.", f_all.size)

        f, x, y_raw, _psd = build_axes(f_all, v_all)
        log.info(
            "In range [%s, %s] Hz: %d samples. X_LOG=%s Y_LOG=%s",
            f"{f[0]:.3g}", f"{f[-1]:.3g}", f.size, X_LOG, Y_LOG,
        )

        # Curve used for the flatness decision (optionally smoothed) plus a
        # force-keep mask that protects genuine spikes above the smoothed floor.
        force_keep = None
        if SMOOTHING != "none":
            y_decide = rolling_stat(y_raw, SMOOTH_WINDOW, SMOOTHING)
            residual = y_raw - y_decide
            force_keep = residual > SPIKE_THRESHOLD
            if PROTECT_NULLS:
                force_keep |= residual < -SPIKE_THRESHOLD
            log.info("Smoothing for drop-decision: %s (window=%d). "
                     "Protected %d feature(s) beyond +-%.4g %s (nulls=%s).",
                     SMOOTHING, SMOOTH_WINDOW, int(force_keep.sum()),
                     SPIKE_THRESHOLD, y_units, PROTECT_NULLS)
        else:
            y_decide = y_raw

        if SWEEP_TOLERANCES:
            run_sweep(f, x, y_decide, y_raw, f.size, SWEEP_TOLERANCES, y_units,
                      force_keep=force_keep)
            return 0

        if TARGET_MAX_POINTS is not None:
            keep, used_tol = simplify_to_budget(
                x, y_decide, TOLERANCE, TARGET_MAX_POINTS, force_keep=force_keep
            )
        else:
            keep = douglas_peucker_vertical(x, y_decide, TOLERANCE,
                                            force_keep=force_keep)
            used_tol = TOLERANCE

        if FORCE_ENDPOINTS:
            keep[0] = True
            keep[-1] = True

        sel_freqs = f[keep]
        max_err = reconstruct_error(x, y_raw, keep)
        rms_full, rms_recon, noise_pct = integrated_noise_error(f, x, y_raw, keep)

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
                 max_err, y_units, used_tol, " dB" if Y_LOG else "")
        log.info("Integrated noise: full=%.6g  reduced=%.6g  error=%+.4f%%  "
                 "<-- gate on this.", rms_full, rms_recon, noise_pct)
        log.info("First freq: %s Hz   Last freq: %s Hz",
                 FREQ_FORMAT.format(sel_freqs[0]), FREQ_FORMAT.format(sel_freqs[-1]))
        log.info("Wrote: %s", OUTPUT_FILE)

        if PLOT:
            save_plot(PLOT_FILE, f, y_raw, keep, y_units)

        return 0

    except Exception as exc:  # noqa: BLE001 - top-level guard for a CLI tool
        log.error("FAILED: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
