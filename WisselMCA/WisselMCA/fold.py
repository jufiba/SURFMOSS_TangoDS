# -*- coding: utf-8 -*-
#
# This file is part of the WisselMCA project
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""Mirror-chi2 folding of a constant-acceleration Mossbauer MCS spectrum.

`fold()` here is a VERBATIM copy of the function of the same name in the
group's offline analysis pipeline:

    Normos-distri/gui/calibration.py   (fold, and the B5 note above it)

so that the device server and the offline fit agree channel for channel on
the same raw spectrum. Keep the two in step: if `fold()` changes there, copy
it here unchanged.

`fold_at()` and `curvature_ratio()` are NOT in the upstream module. They are
thin helpers over the exact same arithmetic, added so the Tango server can
refold on every FoldedSpectrum read at a stored fold point (without
re-searching) and expose the chi2-minimum sharpness as an attribute.
"""

import numpy as np


# ---------------------------------------------------------------------------
# Verbatim from Normos-distri/gui/calibration.py -- do not edit, mirror.
# ---------------------------------------------------------------------------
#
# B5 history -- read before changing the guard in the caller:
# an earlier version of this module gated on "raw input must have exactly
# 512 channels", reasoning that a reduced-velocity-range acquisition would
# have fewer channels than a full-range one. That reasoning was WRONG: a
# real reduced-range acquisition keeps the SAME channel count (the MCA's ND
# doesn't change, only the drive's VMAX does) -- what actually has fewer
# channels is a TRUNCATED array, an artifact of how the synthetic B1-B3
# tests build their reduced-range cases (slicing a window out of a wider
# array), not something a real acquisition ever produces. The 512 gate
# therefore blocked nothing it was meant to block, while wrongly rejecting
# any legitimate raw spectrum from a different MCA (256/1024/2048 channels
# are all common outside this lab). Removed.
#
# There is no reliable way to detect "this array was truncated from a
# wider one" from the array alone -- both a genuine reduced-range
# acquisition and a truncated slice are just N counts, indistinguishable
# on their face. So the defense moved to where the actual symptom shows
# up: fold()'s own chi-square-minimum robustness check, made BLOCKING
# (not just an informational label) in the caller -- see there.


def fold(counts: np.ndarray):
    """Mirror-chi2 folding point search.

    Returns (folded, F, robustness, Fs, resid). robustness is 'sharp' or
    'flat' depending on how peaked the chi2 minimum is -- B5: a flat
    minimum means the fold point is poorly determined and must not be
    silently accepted (see CalibrationDialog._do_fold, which blocks on
    this rather than just showing a note). Fs/resid are the raw
    candidate-fold-point-vs-residual scan, returned so the caller can
    plot the actual curve instead of just the 'sharp'/'flat' label.
    """
    n = len(counts)
    i = np.arange(n)

    def mirror(F):
        j = (F - i) % n
        j0 = np.floor(j).astype(int) % n
        fr = j - np.floor(j)
        return counts[j0] * (1 - fr) + counts[(j0 + 1) % n] * fr

    Fs = np.arange(n - 15, n + 15, 0.05)
    resid = np.array([np.sum((counts - mirror(F)) ** 2) for F in Fs])
    idx_min = int(np.argmin(resid))
    F = Fs[idx_min]

    # robustness: compare the curvature at the minimum to the overall
    # spread of resid -- a flat minimum has near-zero curvature relative
    # to the range.
    #
    # THE 0.02 THRESHOLD BELOW IS AN UNCALIBRATED ESTIMATE, DOCUMENTED AS
    # SUCH, NOT A MEASURED VALUE -- see the module-level B5 note above
    # this function for why channel-count truncation cannot be used to
    # calibrate it, and why the real defense is making 'flat' BLOCKING
    # in the caller rather than trying to detect truncation here.
    lo = max(0, idx_min - 10)
    hi = min(len(resid), idx_min + 11)
    local_curv = resid[hi - 1] + resid[lo] - 2 * resid[idx_min]
    overall_range = resid.max() - resid.min()
    robustness = 'flat' if (overall_range <= 0 or
                            local_curv / overall_range < 0.02) else 'sharp'

    nf = n // 2
    mir = mirror(F)
    folded = counts[:nf] + mir[:nf]
    return folded, float(F), robustness, Fs, resid


# ---------------------------------------------------------------------------
# Added for the Tango server (not in the upstream module).
# ---------------------------------------------------------------------------

def fold_at(counts, F):
    """Fold `counts` about a GIVEN fold point F -- no search.

    The mirror/interpolation is the same arithmetic as fold()'s internal
    mirror() plus its final `counts[:nf] + mir[:nf]`, so a spectrum folded
    here at F equals the one fold() returns when its search lands on F.
    FoldedSpectrum refolds through this on every read at the stored
    FoldPoint. Keep in step with fold().
    """
    counts = np.asarray(counts, dtype=float)
    n = len(counts)
    i = np.arange(n)
    j = (F - i) % n
    j0 = np.floor(j).astype(int) % n
    fr = j - np.floor(j)
    mir = counts[j0] * (1 - fr) + counts[(j0 + 1) % n] * fr
    nf = n // 2
    return counts[:nf] + mir[:nf]


def curvature_ratio(resid):
    """local_curv / overall_range for a resid scan from fold().

    This is exactly the quantity fold() thresholds at 0.02 to label the
    minimum 'flat'; pulled out so the server can expose the number itself.
    Returns 0.0 for a degenerate (flat or empty-range) scan.
    """
    idx_min = int(np.argmin(resid))
    lo = max(0, idx_min - 10)
    hi = min(len(resid), idx_min + 11)
    local_curv = resid[hi - 1] + resid[lo] - 2 * resid[idx_min]
    overall_range = resid.max() - resid.min()
    if overall_range <= 0:
        return 0.0
    return float(local_curv / overall_range)
