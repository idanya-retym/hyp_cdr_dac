#!/usr/bin/env python3
"""
noise_freq_reduce_v1_5.py

Reduce a dense PSD/noise sweep (frequency, value) into the *smallest* list of
frequencies that still reproduces the noise within a target accuracy, then write
those frequencies (one per line, full original precision) to a .txt file for
Spectre.

Two methods
-----------
METHOD = "area"  (NEW in v1.3, recommended for total-noise accuracy)
    Integral-preserving reduction (Visvalingam-style). Starts from the full
    curve and repeatedly removes the point whose removal changes the integrated
    noise power the least (the exact trapezoidal area it contributes), until
    removing any more would push the total-noise (RMS) error past
    TARGET_NOISE_ERROR_PCT. This directly optimises the number you care about
    (total integrated noise), so it needs FAR fewer points than curve-shape
    methods on spur-forest data: flat floor collapses, tall-but-narrow spurs
    (little area) are cheap to drop, broad humps keep points where the area is.

METHOD = "curve"  (v1.0-v1.2 behaviour)
    Douglas-Peucker vertical-error simplification in log/dB space, with optional
    floor smoothing + spike protection. Preserves the visual curve shape but is
    inefficient when the goal is the integrated-noise number.

Accuracy metric (both methods)
------------------------------
Total RMS = sqrt(integral of PSD df), integrated as a linear-PSD trapezoid over
linear frequency (exactly how a noise number is built from sampled points). The
reported "noise err %" is what you should gate on.

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
INPUT_FILE = r"C:\Users\idanya\OneDrive - Retym, Inc\Desktop\vcoldo_wdc2dc.csv"

# Output text file (one frequency per line).
OUTPUT_FILE = r"C:\Users\idanya\OneDrive - Retym, Inc\Desktop\spectre_noise_freqs.txt"

# --- Frequency range to keep (Hz). Points outside are ignored. ---
START_FREQ = 10e3          # lower bound (Hz). 0 = no lower bound.
STOP_FREQ = 1.0e9          # upper bound (Hz).

# --- Reduction method: "area" (recommended) or "curve" (legacy DP). ---
METHOD = "area"

# ======================= AREA method knobs ==================================
# The single knob: keep as few points as possible while total integrated-noise
# (RMS) error stays within this percentage. 1.0 = "within 1% of true noise".
TARGET_NOISE_ERROR_PCT = 1.0
# Optional extra safety cap on point count (None = purely accuracy-driven).
# If set, stops removing once this many points remain even if more accuracy
# budget is left. Leave None to get the minimum points for the target error.
AREA_MAX_POINTS = None

# ======================= CURVE method knobs (METHOD="curve") =================
# X_LOG/Y_LOG: axes for the curve-shape decision (log freq / dB value).
X_LOG = True
Y_LOG = True
# Tolerance for curve method (dB if Y_LOG). Ignored by the area method.
TOLERANCE = 0.25
# Optional point cap for curve method (auto-loosens tolerance).
TARGET_MAX_POINTS = None
# Floor smoothing for the drop decision (curve method only).
SMOOTHING = "median"       # "none" | "median" | "moving_avg"
SMOOTH_WINDOW = 21
SPIKE_THRESHOLD = 3.0      # protect raw spurs above smoothed floor (dB if Y_LOG)
PROTECT_NULLS = False      # also protect deep downward nulls

# --- Common options ---
FORCE_ENDPOINTS = True
# "{}" -> full original precision (all decimals). "{:.1f}"->1000.0  "{:.0f}"->1000
FREQ_FORMAT = "{}"

# --- Sweep: print a table across several settings, then exit (no file). ---
# METHOD="area"  -> list is TARGET_NOISE_ERROR_PCT values, e.g. [0.5,1,2,5].
# METHOD="curve" -> list is TOLERANCE values, e.g. [0.25,0.5,1.0,2.0].
SWEEP_VALUES = None

# --- Reconstruction plot (recommended ON for a final verify run). ---
PLOT = True
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

    order = np.argsort(f, kind="mergesort")
    f = f[order]
    v = v[order]
    keep = np.concatenate(([True], np.diff(f) > 0))
    if not keep.all():
        log.warning("Dropped %d duplicate-frequency row(s).", int((~keep).sum()))
    return f[keep], v[keep]


def build_axes(f, v):
    """Range-filter and build transformed axes.

    Returns (freq, X_transformed, Y_transformed, psd_linear).
    """
    mask = np.ones(f.shape, dtype=bool)
    if START_FREQ and START_FREQ > 0:
        mask &= f >= START_FREQ
    if STOP_FREQ:
        mask &= f <= STOP_FREQ
    if X_LOG:
        mask &= f > 0

    f = f[mask]
    v = v[mask]
    if f.size < 2:
        raise ValueError("Fewer than 2 samples remain after range/transform filtering.")

    x = np.log10(f) if X_LOG else f.copy()
    if Y_LOG:
        if np.any(v <= 0):
            log.warning("%d value(s) <= 0 clamped to a tiny positive number for dB.",
                        int(np.sum(v <= 0)))
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
    windows = np.lib.stride_tricks.sliding_window_view(padded, w)
    if kind == "median":
        return np.median(windows, axis=1)
    if kind == "moving_avg":
        return np.mean(windows, axis=1)
    return y


# ---------------------------------------------------------------------------
# CURVE method (Douglas-Peucker vertical error)
# ---------------------------------------------------------------------------
def douglas_peucker_vertical(x, y_decide, tol, force_keep=None):
    """Boolean keep-mask via vertical-error DP on `y_decide`."""
    n = x.size
    keep = np.zeros(n, dtype=bool)
    keep[0] = True
    keep[-1] = True
    if force_keep is not None:
        keep |= force_keep

    anchors = np.flatnonzero(keep)
    stack = [(int(a), int(b)) for a, b in zip(anchors[:-1], anchors[1:])]
    while stack:
        i0, i1 = stack.pop()
        if i1 <= i0 + 1:
            continue
        x0, x1 = x[i0], x[i1]
        dx = x1 - x0
        xk = x[i0 + 1:i1]
        y0, y1 = y_decide[i0], y_decide[i1]
        interp = np.full(xk.shape, y0) if dx == 0 else y0 + (y1 - y0) * (xk - x0) / dx
        dev = np.abs(y_decide[i0 + 1:i1] - interp)
        j = int(np.argmax(dev))
        if dev[j] > tol:
            imax = i0 + 1 + j
            keep[imax] = True
            stack.append((i0, imax))
            stack.append((imax, i1))
    return keep


def simplify_to_budget(x, y_decide, tol, max_points, force_keep=None):
    """Loosen tolerance until kept count <= max_points (curve method)."""
    keep = douglas_peucker_vertical(x, y_decide, tol, force_keep=force_keep)
    if keep.sum() <= max_points:
        return keep, tol
    log.info("Result has %d points > cap %d; loosening tolerance...",
             int(keep.sum()), max_points)
    cur = tol
    for _ in range(60):
        cur *= 1.5
        keep = douglas_peucker_vertical(x, y_decide, cur, force_keep=force_keep)
        if keep.sum() <= max_points:
            log.info("Tolerance raised to %.4g to meet the cap.", cur)
            return keep, cur
    log.warning("Could not reach cap even after loosening; returning best effort.")
    return keep, cur


def curve_reduce(x, y_raw, y_units):
    """Run the curve (DP) method with optional smoothing/spike protection."""
    force_keep = None
    if SMOOTHING != "none":
        y_decide = rolling_stat(y_raw, SMOOTH_WINDOW, SMOOTHING)
        residual = y_raw - y_decide
        force_keep = residual > SPIKE_THRESHOLD
        if PROTECT_NULLS:
            force_keep |= residual < -SPIKE_THRESHOLD
        log.info("Smoothing: %s (window=%d), protected %d feature(s) beyond +-%.4g %s.",
                 SMOOTHING, SMOOTH_WINDOW, int(force_keep.sum()), SPIKE_THRESHOLD, y_units)
    else:
        y_decide = y_raw

    if TARGET_MAX_POINTS is not None:
        return simplify_to_budget(x, y_decide, TOLERANCE, TARGET_MAX_POINTS,
                                  force_keep=force_keep)
    return douglas_peucker_vertical(x, y_decide, TOLERANCE, force_keep=force_keep), TOLERANCE


# ---------------------------------------------------------------------------
# AREA method (integral-preserving, O(n) forward pass)
# ---------------------------------------------------------------------------
def _area_forward(f, psd, cumC, eps):
    """Keep-mask from a single forward greedy pass (guaranteed O(n)).

    Walks an anchor forward, extending the span while the straight-line
    (linear PSD vs linear freq) reconstruction area differs from the true area
    (from the precomputed cumulative integral `cumC`) by no more than `eps`.
    When it would exceed `eps`, the last in-tolerance point is kept and becomes
    the next anchor. No recursion, no heap -> cannot blow up on flat runs.
    """
    n = f.size
    keep = np.zeros(n, dtype=bool)
    keep[0] = True
    a = 0
    b = 1
    while b < n:
        recon = 0.5 * (f[b] - f[a]) * (psd[a] + psd[b])
        true_area = cumC[b] - cumC[a]
        if abs(recon - true_area) <= eps:
            b += 1
            continue
        kept = b - 1 if (b - 1) > a else b  # guarantee forward progress
        keep[kept] = True
        a = kept
        b = a + 1
    keep[-1] = True
    return keep


def area_reduce(f, psd, target_pct, max_points=None):
    """Integral-preserving reduction gated on total-noise (RMS) error.

    Bisects the per-span area tolerance `eps` to find the FEWEST points whose
    reconstruction keeps the integrated-noise error within `target_pct`
    (or, if `max_points` is set, within that point budget).
    """
    n = f.size
    if n < 3:
        return np.ones(n, dtype=bool)
    i_full = float(_trapezoid(psd, f))
    if i_full <= 0:
        raise ValueError("Non-positive integrated PSD; area method needs PSD > 0.")

    # Cumulative trapezoidal integral for O(1) true-area lookups.
    cumC = np.concatenate(([0.0], np.cumsum(0.5 * np.diff(f) * (psd[1:] + psd[:-1]))))

    lo = np.log(i_full * 1e-15)  # tiny eps -> many points, ~0 error
    hi = np.log(i_full)          # huge eps -> ~endpoints only
    best = None
    for _ in range(15):
        mid = 0.5 * (lo + hi)
        keep = _area_forward(f, psd, cumC, float(np.exp(mid)))
        if max_points is not None:
            if int(keep.sum()) <= max_points:
                best = keep
                hi = mid  # try finer (smaller eps) for more accuracy
            else:
                lo = mid
        else:
            _, _, pct = integrated_noise_error(f, psd, keep)
            if abs(pct) <= target_pct:
                best = keep
                lo = mid  # try coarser (larger eps) for fewer points
            else:
                hi = mid
    if best is None:
        best = _area_forward(f, psd, cumC, float(np.exp(lo)))
    best[0] = True
    best[-1] = True
    return best


# ---------------------------------------------------------------------------
# Metrics / plotting
# ---------------------------------------------------------------------------
def integrated_noise_error(f, psd_full, keep):
    """Total-RMS noise error (%) using linear-PSD / linear-freq trapezoid."""
    idx = np.flatnonzero(keep)
    psd_recon = np.interp(f, f[idx], psd_full[idx])
    rms_full = float(np.sqrt(_trapezoid(psd_full, f)))
    rms_recon = float(np.sqrt(_trapezoid(psd_recon, f)))
    if rms_full <= 0:
        return rms_full, rms_recon, float("nan")
    return rms_full, rms_recon, 100.0 * (rms_recon / rms_full - 1.0)


def save_plot(path, f, y_raw, keep, y_units):
    """Save an overlay of kept points on the full curve."""
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
    ax.plot(f, recon, color="tab:blue", lw=1.0, label="reconstruction")
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


def run_sweep(f, x, y_raw, psd_full, values, y_units):
    """Print a table across sweep values for the active method (no file)."""
    n = f.size
    log.info("Sweep for METHOD=%s (no output file written):", METHOD)
    header = f"{'setting':>10} | {'kept':>8} | {'reduction':>9} | {'noise err %':>11}"
    log.info(header)
    log.info("-" * len(header))
    for val in values:
        if METHOD == "area":
            keep = area_reduce(f, psd_full, val, max_points=AREA_MAX_POINTS)
            label = f"{val:g}%"
        else:
            keep = douglas_peucker_vertical(x, y_raw, val)
            label = f"{val:g}"
        if FORCE_ENDPOINTS:
            keep[0] = True
            keep[-1] = True
        kept = int(keep.sum())
        red = 100.0 * (1.0 - kept / n)
        _, _, npct = integrated_noise_error(f, psd_full, keep)
        log.info("%10s | %8d | %8.2f%% | %+10.4f%%", label, kept, red, npct)


def main():
    try:
        y_units = "dB" if Y_LOG else "linear"

        log.info("Reading: %s", INPUT_FILE)
        f_all, v_all = load_csv(INPUT_FILE)
        log.info("Loaded %d samples.", f_all.size)

        f, x, y_raw, psd_full = build_axes(f_all, v_all)
        log.info("In range [%s, %s] Hz: %d samples. METHOD=%s",
                 f"{f[0]:.3g}", f"{f[-1]:.3g}", f.size, METHOD)

        if SWEEP_VALUES:
            run_sweep(f, x, y_raw, psd_full, SWEEP_VALUES, y_units)
            return 0

        if METHOD == "area":
            keep = area_reduce(f, psd_full, TARGET_NOISE_ERROR_PCT,
                               max_points=AREA_MAX_POINTS)
            used = f"{TARGET_NOISE_ERROR_PCT:g}% target"
        elif METHOD == "curve":
            keep, tol = curve_reduce(x, y_raw, y_units)
            used = f"{tol:g} {y_units} tol"
        else:
            raise ValueError(f"Unknown METHOD: {METHOD!r} (use 'area' or 'curve').")

        if FORCE_ENDPOINTS:
            keep[0] = True
            keep[-1] = True

        sel_freqs = f[keep]
        rms_full, rms_recon, noise_pct = integrated_noise_error(f, psd_full, keep)

        text = "\n".join(FREQ_FORMAT.format(v) for v in sel_freqs)
        out_dir = os.path.dirname(OUTPUT_FILE)
        if out_dir and not os.path.isdir(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")

        reduction = 100.0 * (1.0 - sel_freqs.size / f.size)
        log.info("-" * 60)
        log.info("Method=%s (%s).", METHOD, used)
        log.info("Kept %d of %d points (%.2f%% reduction).",
                 sel_freqs.size, f.size, reduction)
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
