#!/usr/bin/env python3
"""
noise_freq_reduce.py

v1.7: spur protection for the area method (spur peaks are always kept),
coverage report of an existing frequency list (noise error, gaps, missed
spurs), and optional merge of that list into the output.

Reduce a dense PSD/noise sweep (frequency, value) into the *smallest* list of
frequencies that still reproduces the noise within a target accuracy, then write
those frequencies (one per line, full original precision, Unix LF endings) to a
.txt file for Spectre.

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
import re
import sys
import logging

import numpy as np

# ----------------------------------------------------------------------------
# CONFIG - edit these
# ----------------------------------------------------------------------------

# All files live next to this script.
HERE = os.path.dirname(os.path.abspath(__file__))

# Input CSV: 2 columns (freq_Hz, psd_value). First row is a header and skipped.
INPUT_FILE = os.path.join(HERE, "VCO_LDO_4p7uF_0p1uF_noise_v_sqr.csv")

# Outputs are named after the noise file: <noise>_freqs.txt / _freqs.png / .log
OUT_BASE = os.path.splitext(INPUT_FILE)[0]

# Output text file (one frequency per line).
OUTPUT_FILE = OUT_BASE + "_freqs.txt"

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

# ======================= Spur protection (area method) ======================
# Spur peaks are force-kept so they are sampled even when they hold little area.
SPUR_PROTECT = True
SPUR_THRESHOLD_DB = 6.0    # peak must rise this many dB above the local floor
SPUR_WINDOW = 51           # samples in the rolling-median floor estimate
SPUR_NEIGHBORS = 1         # also keep +-N samples around each peak (spur shape)

# ======================= Existing frequency list ============================
# Your current Spectre list. Gets a coverage report; None = skip.
EXISTING_FREQ_FILE = os.path.join(HERE, "freq_points_noise.txt")
MERGE_EXISTING = True      # include the existing freqs in the output list
SPUR_MISS_DB = 3.0         # a spur is "missed" if a list under-reads it by more

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
PLOT_FILE = OUT_BASE + "_freqs.png"

# Run log (also printed to the console).
LOG_FILE = OUT_BASE + ".log"

# ----------------------------------------------------------------------------
# End of CONFIG
# ----------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(),
              logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")],
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
    if kind == "median":
        try:
            from scipy.ndimage import median_filter
            return median_filter(y, size=w, mode="reflect")
        except ImportError:
            pass
    half = w // 2
    padded = np.pad(y, half, mode="reflect")
    out = np.empty_like(y)
    chunk = 100_000  # bounds memory on ~1M-point files
    for s in range(0, y.size, chunk):
        e = min(s + chunk, y.size)
        win = np.lib.stride_tricks.sliding_window_view(padded[s:e + w - 1], w)
        if kind == "median":
            out[s:e] = np.median(win, axis=1)
        elif kind == "moving_avg":
            out[s:e] = np.mean(win, axis=1)
        else:
            return y
    return out


# ---------------------------------------------------------------------------
# Spurs / existing frequency list
# ---------------------------------------------------------------------------
_SUFFIX = {"T": 1e12, "G": 1e9, "M": 1e6, "K": 1e3, "k": 1e3,
           "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15}
_NUM_RE = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)([a-zA-Z]*)$")


def _parse_num(tok):
    """Parse a number with optional Spectre suffix (1k, 10M, 2.5G, 100Hz)."""
    m = _NUM_RE.match(tok)
    if not m:
        return None
    val = float(m.group(1))
    suf = m.group(2)
    if suf and suf.lower() != "hz":
        mult = _SUFFIX.get(suf[0])
        if mult is None:
            return None
        val *= mult
    return val


def load_freq_list(path):
    """Load a frequency list (one per line, or a Spectre values=[...] list)."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Existing frequency file not found: {path}")
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        text = fh.read()
    vals = [v for v in (_parse_num(t) for t in re.split(r"[\s,;\[\]=()]+", text) if t)
            if v is not None]
    if not vals:
        raise ValueError(f"No frequencies parsed from: {path}")
    return np.unique(np.asarray(vals, dtype=float))


def nearest_indices(f, targets):
    """Indices of the samples in sorted `f` nearest to each target."""
    pos = np.clip(np.searchsorted(f, targets), 1, f.size - 1)
    left = pos - 1
    pick = np.where(np.abs(targets - f[left]) <= np.abs(f[pos] - targets), left, pos)
    return np.unique(pick)


def detect_spurs(f, psd):
    """Indices of local maxima that rise SPUR_THRESHOLD_DB above a median floor."""
    y = 10.0 * np.log10(np.maximum(psd, TINY))
    floor = rolling_stat(y, SPUR_WINDOW, "median")
    resid = y - floor
    is_max = np.zeros(y.size, dtype=bool)
    is_max[1:-1] = (y[1:-1] >= y[:-2]) & (y[1:-1] >= y[2:])
    return np.flatnonzero(is_max & (resid > SPUR_THRESHOLD_DB))


def spur_errors_db(f, psd, keep, peaks):
    """dB error of the reconstruction at each spur peak (negative = under-read)."""
    idx = np.flatnonzero(keep)
    recon = np.interp(f[peaks], f[idx], psd[idx])
    return 10.0 * np.log10(np.maximum(recon, TINY) / np.maximum(psd[peaks], TINY))


def report_existing(f, psd, ex_freqs, peaks):
    """Log how well an existing list covers the data. Returns (index mask, freqs in range)."""
    in_rng = ex_freqs[(ex_freqs >= f[0]) & (ex_freqs <= f[-1])]
    log.info("Existing list: %d freqs, %d inside [%.3g, %.3g] Hz, %d outside.",
             ex_freqs.size, in_rng.size, f[0], f[-1], ex_freqs.size - in_rng.size)
    mask = np.zeros(f.size, dtype=bool)
    if in_rng.size < 2:
        log.warning("Existing list has < 2 points in range; skipping coverage report.")
        return mask, in_rng
    mask[nearest_indices(f, in_rng)] = True

    _, _, pct = integrated_noise_error(f, psd, mask)
    log.info("Existing list alone: integrated-noise error = %+.4f%%", pct)

    if in_rng[0] > f[0] * 1.01:
        log.warning("Existing list does not cover the low end: %.3g -> %.3g Hz.", f[0], in_rng[0])
    if in_rng[-1] < f[-1] * 0.99:
        log.warning("Existing list does not cover the high end: %.3g -> %.3g Hz.", in_rng[-1], f[-1])
    gaps = np.diff(np.log10(in_rng))
    g = int(np.argmax(gaps))
    log.info("Largest gap in existing list: %.3g decades (%.4g -> %.4g Hz).",
             gaps[g], in_rng[g], in_rng[g + 1])

    if peaks.size:
        err = spur_errors_db(f, psd, mask, peaks)
        missed = np.flatnonzero(err < -SPUR_MISS_DB)
        log.info("Existing list misses %d of %d spurs (under-reads by > %.1f dB).",
                 missed.size, peaks.size, SPUR_MISS_DB)
        worst = missed[np.argsort(err[missed])][:15]
        for k in worst:
            p = peaks[k]
            log.info("    missed spur %14.6g Hz  %8.2f dB  (list reads %+.1f dB)",
                     f[p], 10.0 * np.log10(max(psd[p], TINY)), err[k])
    return mask, in_rng


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
def _area_forward(f, psd, cumC, eps, force=None):
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
            if force is not None and force[b]:
                keep[b] = True
                a = b
                b = a + 1
                continue
            b += 1
            continue
        kept = b - 1 if (b - 1) > a else b  # guarantee forward progress
        keep[kept] = True
        a = kept
        b = a + 1
    keep[-1] = True
    return keep


def area_reduce(f, psd, target_pct, max_points=None, force=None):
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
        keep = _area_forward(f, psd, cumC, float(np.exp(mid)), force)
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
        best = _area_forward(f, psd, cumC, float(np.exp(lo)), force)
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


def save_plot(path, f, y_raw, keep, y_units, peaks=None):
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
    if peaks is not None and peaks.size:
        ax.plot(f[peaks], y_raw[peaks], "x", color="tab:orange", ms=4,
                label=f"detected spurs ({peaks.size})")
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


def run_sweep(f, x, y_raw, psd_full, values, y_units, force=None):
    """Print a table across sweep values for the active method (no file)."""
    n = f.size
    log.info("Sweep for METHOD=%s (no output file written):", METHOD)
    header = f"{'setting':>10} | {'kept':>8} | {'reduction':>9} | {'noise err %':>11}"
    log.info(header)
    log.info("-" * len(header))
    for val in values:
        if METHOD == "area":
            keep = area_reduce(f, psd_full, val, max_points=AREA_MAX_POINTS, force=force)
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

        peaks = np.array([], dtype=int)
        force = None
        if SPUR_PROTECT:
            peaks = detect_spurs(f, psd_full)
            force = np.zeros(f.size, dtype=bool)
            for k in range(-SPUR_NEIGHBORS, SPUR_NEIGHBORS + 1):
                force[np.clip(peaks + k, 0, f.size - 1)] = True
            log.info("Detected %d spur(s) > %.1f dB above floor; force-keeping %d point(s).",
                     peaks.size, SPUR_THRESHOLD_DB, int(force.sum()))

        exist_mask = None
        ex_in = None
        if EXISTING_FREQ_FILE:
            ex = load_freq_list(EXISTING_FREQ_FILE)
            log.info("-" * 60)
            exist_mask, ex_in = report_existing(f, psd_full, ex, peaks)
            log.info("-" * 60)
            if MERGE_EXISTING:
                force = exist_mask if force is None else (force | exist_mask)

        if SWEEP_VALUES:
            run_sweep(f, x, y_raw, psd_full, SWEEP_VALUES, y_units, force=force)
            return 0

        if METHOD == "area":
            keep = area_reduce(f, psd_full, TARGET_NOISE_ERROR_PCT,
                               max_points=AREA_MAX_POINTS, force=force)
            used = f"{TARGET_NOISE_ERROR_PCT:g}% target"
        elif METHOD == "curve":
            keep, tol = curve_reduce(x, y_raw, y_units)
            if MERGE_EXISTING and exist_mask is not None:
                keep |= exist_mask
            used = f"{tol:g} {y_units} tol"
        else:
            raise ValueError(f"Unknown METHOD: {METHOD!r} (use 'area' or 'curve').")

        if FORCE_ENDPOINTS:
            keep[0] = True
            keep[-1] = True

        if MERGE_EXISTING and exist_mask is not None:
            # write existing freqs with their original values, not the nearest CSV sample
            sel_freqs = np.union1d(f[keep & ~exist_mask], ex_in)
        else:
            sel_freqs = f[keep]
        rms_full, rms_recon, noise_pct = integrated_noise_error(f, psd_full, keep)
        if peaks.size:
            err = spur_errors_db(f, psd_full, keep, peaks)
            log.info("Output list misses %d of %d spurs (under-reads by > %.1f dB).",
                     int(np.sum(err < -SPUR_MISS_DB)), peaks.size, SPUR_MISS_DB)

        text = "\n".join(FREQ_FORMAT.format(v) for v in sel_freqs)
        out_dir = os.path.dirname(OUTPUT_FILE)
        if out_dir and not os.path.isdir(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        # newline="\n" forces Unix LF endings so Spectre on Linux parses cleanly
        # (avoids the CRLF/\r that would otherwise need dos2unix).
        with open(OUTPUT_FILE, "w", encoding="utf-8", newline="\n") as fh:
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
            save_plot(PLOT_FILE, f, y_raw, keep, y_units, peaks=peaks)
        return 0

    except Exception as exc:  # noqa: BLE001 - top-level guard for a CLI tool
        log.error("FAILED: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
