"""
===============================================================================
 gelo_svm_pipeline.py
 A complete, self-contained SVM pipeline for left-vs-right motor imagery
 on a 2-channel (C3/C4) headset.
===============================================================================

 WHAT THIS FILE IS

 One readable module containing the whole decoder, from raw signal to a
 prediction, with every design decision stated in the comments. It trains on a
 public dataset (BCI Competition IV 2b) and predicts on our Gelo headband.

 It is deliberately written to be READ, not just run. Each section explains
 what it does and why that choice was made over the alternatives.

 THE PIPELINE, IN ONE PICTURE

     raw EEG  ->  band-pass 8-30 Hz  ->  epoch 0.5-3.5 s after cue
                                              |
                                              v
                            covariance matrix per trial (2x2)
                                              |
                                      Euclidean Alignment
                                   (whiten each session by its
                                    own mean covariance)
                                              |
                      +-----------------------+-----------------------+
                      |                       |                       |
                  CSP log-var           tangent space            log variance
                  (2 features)          (3 features)             (2 features)
                      |                       |                       |
                      +-----------------------+-----------------------+
                                              |
                                        StandardScaler
                                              |
                                        SVM (linear)
                                              |
                                      left  /  right

 WHY A COVARIANCE MATRIX IS THE RIGHT REPRESENTATION

 Motor imagery shows up as event-related desynchronisation: the mu (8-13 Hz)
 and beta (13-30 Hz) rhythms get WEAKER over the motor cortex controlling the
 imagined hand, and that cortex is on the opposite side of the head. So the
 signal lives in the POWER of a band, and in how that power is distributed
 across channels. Both of those are exactly what a covariance matrix holds:
 its diagonal is the per-channel band power, its off-diagonal is how the
 channels co-vary. Every classical MI method - CSP, filter-bank CSP,
 Riemannian tangent space, minimum-distance-to-mean - is a different function
 of this same matrix. Computing it once and reusing it is both correct and
 fast.

 With 2 channels the matrix is 2x2, so it has 3 free numbers. That is the
 entire information budget this headset gives per trial per band. It is why
 the choice of classifier turns out to matter far less than people expect:
 every model here is reading the same three numbers.

 WHY EUCLIDEAN ALIGNMENT MATTERS MORE THAN THE CLASSIFIER

 EEG amplitude varies enormously between people, between sessions, and between
 devices - electrode contact, impedance, hair, amplifier gain. A boundary
 fitted at one scale is meaningless at another. Our own measurements found our
 headset sits 3.1x higher in energy than the reference dataset, which was
 enough to make an earlier classifier predict a single class for 85-100 % of
 epochs.

 Euclidean Alignment (He & Wu, 2018) fixes this. For each session, compute the
 mean covariance R over its trials, then map every covariance

     C  ->  R^(-1/2) C R^(-1/2)

 After this, each session's own mean covariance becomes the identity, so every
 session arrives at the classifier in the same coordinate frame. Crucially it
 uses NO LABELS, so it can be applied to a brand-new user's recording before
 you know what they were imagining - it is not cheating, and it needs no
 calibration.

 In our experiments it improved every one of 28 configurations, mean +0.045
 balanced accuracy, while the choice between CSP, FBCSP, tangent space, FgMDM
 and plain log-variance was worth about 0.003.

 HOW THIS IS EVALUATED HONESTLY

 Three rules, each of which has already caught a real error in this project:

 1. Anything SUPERVISED stays inside the cross-validation fold. CSP, tangent
    space and feature selection all learn from labels. Fitting them once on
    everything and then cross-validating is the single most common way CSP
    results get inflated. They live inside the sklearn Pipeline here, so
    sklearn re-fits them per fold automatically.

 2. The evaluation unit is whatever is NOT independent. Our recordings put one
    class per file, so epochs within a file are not independent observations;
    15 files is 15 decisions, not 72. Scoring per epoch inflates the number.

 3. Report balanced accuracy, never bare accuracy, and print the majority
    baseline beside it. On an unbalanced test set a model that always answers
    "right" can score 69 % while having learned nothing. That exact thing
    happened earlier in this project.

 USAGE

     # train on the public dataset, save the model
     python gelo_svm_pipeline.py train

     # predict on our recordings
     python gelo_svm_pipeline.py predict

     # or from your own code
     from gelo_svm_pipeline import GeloDecoder
     dec = GeloDecoder(model="csp_svm").fit_on_2b()
     labels = dec.predict_csv(r"D:\\trainsvm\\data\\gelo\\left\\Left1_5.csv")

 Requires: numpy, scipy, scikit-learn, pyriemann.  No MNE, no MOABB.
===============================================================================
"""

import os
import pickle
import sys

import numpy as np
from pyriemann.classification import FgMDM
from pyriemann.spatialfilters import CSP
from pyriemann.tangentspace import TangentSpace
from scipy.signal import butter, detrend, filtfilt
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.covariance import ledoit_wolf
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis as LDA
from sklearn.metrics import balanced_accuracy_score, confusion_matrix
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

HERE = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------------------------------- #
# CONFIGURATION
# Every number here is a decision. The comment says why.
# --------------------------------------------------------------------------- #
FS = 250.0        # Hz. The Gelo records at 250 and so does 2b, so no resampling
                  # is needed anywhere. (Note: an earlier MATLAB script in this
                  # project used 256, which made every reported frequency 2.4 %
                  # too high.)

BAND = (8.0, 30.0)   # mu + beta. This is where motor imagery lives. Narrower
                     # bands (8-13 alone) were tried and did not help.
FILTER_ORDER = 4     # Butterworth, applied forward-and-backward (filtfilt) so
                     # there is no phase shift. A one-way filter delays the
                     # signal and smears the onset.

TMIN, TMAX = 0.5, 3.5  # seconds after CUE onset. The first 0.5 s is dropped
                       # because the user has not started imagining yet -
                       # there is a reaction delay. 3 s is enough; ERD is
                       # strongest early and fades.

CUE_OFFSET_2B = 3.0   # In the 2b files the stored index is the TRIAL START and
                      # the cue comes 3 s later. Getting this wrong puts the
                      # window inside the fixation period and gives EXACTLY
                      # chance - which is what happened on the first run.

SEED = 42
C_GRID = [0.01, 0.1, 1.0, 10.0]   # SVM regularisation. Small C = smoother
                                  # boundary. With 3 features and few trials,
                                  # smaller is usually better.


# =========================================================================== #
# SECTION 1 - SIGNAL PROCESSING
# =========================================================================== #
def bandpass(x, lo=BAND[0], hi=BAND[1], fs=FS):
    """Zero-phase band-pass. x is (n_samples, n_channels)."""
    b, a = butter(FILTER_ORDER, [lo, hi], btype="band", fs=fs)
    return filtfilt(b, a, x, axis=0)


def epoch_covariances(epochs):
    """
    Covariance matrix per trial.  epochs is (n_trials, n_channels, n_samples).

    Ledoit-Wolf shrinkage rather than the plain sample covariance: with only a
    few hundred samples the plain estimate is noisy and can be near-singular,
    which breaks the matrix inverse and square root that the Riemannian methods
    and the alignment both need. Shrinkage pulls it towards a scaled identity
    by a data-driven amount and guarantees it stays invertible.
    """
    return np.stack([ledoit_wolf(np.asarray(e, float).T)[0] for e in epochs])


def _inv_sqrtm(M):
    """Inverse matrix square root of a symmetric positive-definite matrix."""
    w, V = np.linalg.eigh(M)
    return (V * (np.maximum(w, 1e-12) ** -0.5)) @ V.T


def euclidean_align(cov, groups):
    """
    Euclidean Alignment.  cov is (n_trials, c, c), groups is (n_trials,).

    `groups` must be the DOMAIN unit - the thing that differs and that you want
    to cancel. Here that is one recording session (for 2b) or one file (for the
    Gelo), because that is the unit over which electrode contact, impedance and
    the day are constant.

    Uses no labels. Safe to apply to unseen test data, which is the whole point:
    a new user's recording can be aligned before you know what they imagined.
    """
    out = np.empty_like(cov)
    for g in np.unique(groups):
        m = groups == g
        P = _inv_sqrtm(cov[m].mean(axis=0))
        out[m] = np.einsum("ij,njk,kl->nil", P, cov[m], P)
    return out


# =========================================================================== #
# SECTION 2 - FEATURE EXTRACTORS
# =========================================================================== #
class LogVariance(BaseEstimator, TransformerMixin):
    """
    The simplest possible feature: log band power per channel, which is the
    log of the covariance diagonal.

    Two numbers for a 2-channel headset. On our benchmarks this tied the far
    more elaborate methods, because with 2 channels there is very little for a
    spatial filter to find. Keep it as the baseline that any new idea must
    beat - if a complicated model cannot beat two numbers, it is not earning
    its complexity.
    """

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return np.log(np.maximum(np.einsum("nii->ni", X), 1e-20))


def build_model(name="csp_svm"):
    """
    Returns (pipeline, hyperparameter_grid).

    All four are functions of the covariance matrix, so they are interchangeable
    and directly comparable.

      csp_svm     Common Spatial Patterns + SVM. CSP finds the channel mixture
                  whose variance differs most between the two classes. The
                  classic MI method. With 2 channels it can only find 2
                  components, so it is close to a rotation.
      csp_lda     The same features with Linear Discriminant Analysis instead.
                  No hyperparameters at all, which makes it a good default when
                  training data is scarce.
      ts_svm      Riemannian tangent space. Covariance matrices live on a curved
                  manifold, not in flat space; averaging them naively distorts
                  them. The tangent-space map projects them onto a flat space
                  at the geometric mean, where ordinary linear classifiers are
                  valid. Usually the strongest classical method - on many
                  channels.
      logvar_svm  The LogVariance baseline above.
    """
    svm = LinearSVC(class_weight="balanced", random_state=SEED,
                    dual="auto", max_iter=20000)
    if name == "csp_svm":
        return Pipeline([
            ("csp", CSP(nfilter=2, metric="euclid", log=True)),
            ("scale", StandardScaler()),
            ("clf", svm)]), {"clf__C": C_GRID}
    if name == "csp_lda":
        return Pipeline([
            ("csp", CSP(nfilter=2, metric="euclid", log=True)),
            ("clf", LDA())]), {}
    if name == "ts_svm":
        return Pipeline([
            ("ts", TangentSpace(metric="riemann")),
            ("scale", StandardScaler()),
            ("clf", svm)]), {"clf__C": C_GRID}
    if name == "logvar_svm":
        return Pipeline([
            ("logvar", LogVariance()),
            ("scale", StandardScaler()),
            ("clf", svm)]), {"clf__C": C_GRID}
    if name == "fgmdm":
        return Pipeline([("clf", FgMDM(metric="riemann"))]), {}
    raise ValueError(f"unknown model {name!r}")


# =========================================================================== #
# SECTION 3 - DATA LOADERS
# =========================================================================== #
def load_2b(data_dir=None, channels=(0, 2)):
    """
    Load the cached BCI IV 2b epochs written by s01_fetch_2b.py.

    channels=(0, 2) keeps C3 and C4 and drops Cz, matching our headset.
    Dropping Cz costs about 0.002 balanced accuracy - measured, not assumed.
    """
    data_dir = data_dir or os.path.join(HERE, "data")
    X, y, g = [], [], []
    for i in range(1, 10):
        p = os.path.join(data_dir, f"sub-B{i:02d}.npz")
        if not os.path.exists(p):
            continue
        d = np.load(p)
        X.append(d["X"][:, list(channels), :])
        y.append(d["y"])
        # group = subject*10 + session, so each session is its own EA domain
        g.append(i * 10 + d["sess"].astype(int))
    if not X:
        raise FileNotFoundError(
            f"No sub-BXX.npz in {data_dir}. Run s01_fetch_2b.py first.")
    return np.concatenate(X), np.concatenate(y), np.concatenate(g)


def load_gelo_csv(path, c3_col=1, c4_col=2, marks=(1, 2, 3, 4, 5),
                  min_rest=1.5, pad=0.5):
    """
    Cut epochs from one Gelo CSV.

    Columns are timestamp, ch1..ch8, mark. Only ch1-ch4 are live; ch5-ch8 hold
    the float minimum 1.18e-38, meaning "not connected". ch2 and ch3 are taken
    as C3 and C4 - note this mapping was never physically verified, and a test
    of the swapped order did not change results either way.

    A trial is kept only if at least `min_rest` seconds of rest precede it, so
    that the epoch is not contaminated by the previous trial. `pad` seconds of
    extra signal are filtered and then discarded, keeping the filter's edge
    transients outside the analysis window.

    Returns (epochs, kept_mark_ids). Values are converted volts -> microvolts.
    """
    M = np.genfromtxt(path, delimiter=",", skip_header=1)
    M = M[~np.isnan(M[:, -1])]
    X = M[:, 1:5] * 1e6
    mk = M[:, -1]

    n_pad = int(round(pad * FS))
    start = int(round(TMIN * FS))
    length = int(round((TMAX - TMIN) * FS))
    need = int(round((TMAX + pad) * FS))

    eps, kept = [], []
    for m in marks:
        idx = np.flatnonzero(mk == m)
        if idx.size == 0:
            continue
        on = int(idx[0])
        j = on - 1
        while j >= 0 and mk[j] == 0:
            j -= 1
        if (on - 1 - j) / FS < min_rest:      # not enough clean rest before
            continue
        if on - n_pad < 0 or on + need > X.shape[0]:
            continue
        seg = detrend(X[on - n_pad: on + need, [c3_col, c4_col]],
                      axis=0, type="constant")
        seg = bandpass(seg)
        eps.append(seg[n_pad + start: n_pad + start + length, :].T)
        kept.append(m)
    return (np.stack(eps) if eps else np.empty((0, 2, length))), kept


# =========================================================================== #
# SECTION 4 - THE DECODER
# =========================================================================== #
class GeloDecoder:
    """
    Train on a public dataset, predict on our headset.

    The model never sees a label from the target user. That is the goal: a
    decoder that works out of the box, with no calibration session. Our
    calibration-curve experiment found that adding up to 320 of the user's own
    labelled trials changed accuracy by less than 0.01 once Euclidean Alignment
    was in place - the alignment does the work that calibration would otherwise
    do.
    """

    def __init__(self, model="csp_svm", use_ea=True):
        self.model_name = model
        self.use_ea = use_ea
        self.pipeline_, self.grid_ = build_model(model)

    # ---- training --------------------------------------------------------- #
    def fit(self, epochs, y, groups):
        """epochs (n, c, t), y (n,) in {0=left, 1=right}, groups = session id."""
        np.random.seed(SEED)
        cov = epoch_covariances(epochs)
        if self.use_ea:
            cov = euclidean_align(cov, groups)

        if self.grid_:
            # Hyperparameters chosen by an inner cross-validation GROUPED by
            # session, so no session is split across the inner folds. Without
            # grouping, trials from one session appear on both sides and the
            # chosen C is tuned to a leak.
            n_splits = min(4, len(np.unique(groups)))
            cv = GroupKFold(n_splits=max(2, n_splits))
            gs = GridSearchCV(self.pipeline_, self.grid_,
                              cv=cv.split(cov, y, groups),
                              scoring="balanced_accuracy", refit=True)
            gs.fit(cov, y)
            self.fitted_ = gs.best_estimator_
            self.best_params_ = gs.best_params_
        else:
            self.fitted_ = self.pipeline_.fit(cov, y)
            self.best_params_ = {}
        return self

    def fit_on_2b(self, channels=(0, 2)):
        X, y, g = load_2b(channels=channels)
        print(f"training {self.model_name} on {len(y)} trials from 2b "
              f"({len(np.unique(g))} sessions), EA={'on' if self.use_ea else 'off'}")
        return self.fit(X, y, g)

    # ---- prediction ------------------------------------------------------- #
    def predict(self, epochs, groups=None):
        """
        groups identifies the recording session/file each epoch came from, so
        that alignment is computed per recording. If you pass None, all epochs
        are treated as one recording - correct only if they really are.
        """
        cov = epoch_covariances(epochs)
        if self.use_ea:
            if groups is None:
                groups = np.zeros(len(cov), int)
            cov = euclidean_align(cov, groups)
        return self.fitted_.predict(cov)

    def predict_csv(self, path):
        eps, marks = load_gelo_csv(path)
        if len(eps) == 0:
            return [], []
        return self.predict(eps, np.zeros(len(eps), int)), marks

    # ---- persistence ------------------------------------------------------ #
    def save(self, path):
        with open(path, "wb") as fh:
            pickle.dump(self, fh)
        return path

    @staticmethod
    def load(path):
        with open(path, "rb") as fh:
            return pickle.load(fh)


# =========================================================================== #
# SECTION 5 - HONEST SCORING
# =========================================================================== #
def report(y_true, y_pred, groups=None, label=""):
    """
    Print the metrics that cannot be gamed.

    If `groups` is given (e.g. one per recording file), a file-level majority
    vote is also reported. When each file contains a single class, the file is
    the real unit of evidence and the epoch-level number is optimistic.
    """
    bal = balanced_accuracy_score(y_true, y_pred)
    acc = float((y_true == y_pred).mean())
    maj = float(max(np.bincount(y_true, minlength=2)) / len(y_true))
    print(f"\n--- {label} ---")
    print(f"  epochs            {len(y_true)}")
    print(f"  accuracy          {acc:.4f}")
    print(f"  balanced accuracy {bal:.4f}      <- read this one")
    print(f"  majority baseline {maj:.4f}      <- and never quote accuracy "
          f"without it")
    print(f"  confusion matrix  {confusion_matrix(y_true, y_pred).tolist()}")
    print(f"  predicted 'right' {y_pred.mean():.0%} of the time")
    if groups is not None:
        u = np.unique(groups)
        t = np.array([y_true[groups == g][0] for g in u])
        v = np.array([int(y_pred[groups == g].mean() >= 0.5) for g in u])
        print(f"  FILE-level        {balanced_accuracy_score(t, v):.4f} "
              f"({int((t == v).sum())}/{len(t)} files) <- the honest unit when "
              f"one class per file")
    return bal


# =========================================================================== #
# SECTION 6 - COMMAND LINE
# =========================================================================== #
def main(argv):
    cmd = argv[1] if len(argv) > 1 else "train"
    out = os.path.join(HERE, "results", "gelo_decoder.pkl")

    if cmd == "train":
        dec = GeloDecoder(model="csp_svm", use_ea=True).fit_on_2b()
        dec.save(out)
        print(f"chosen hyperparameters: {dec.best_params_}")
        print(f"saved to {out}")
        print("\nReference performance of this exact configuration, measured in\n"
              "EXPERIMENT_2 (balanced accuracy, 2 channels, EA on):\n"
              "  0.744  new person, never seen in training (9/9 above chance)\n"
              "  0.768  same, scored on held-out sessions only\n"
              "Expect LESS on the Gelo: that model crosses people but not\n"
              "devices, and our recordings add their own shift on top.")

    elif cmd == "predict":
        import glob
        dec = (GeloDecoder.load(out) if os.path.exists(out)
               else GeloDecoder(model="csp_svm").fit_on_2b())
        names = {0: "LEFT", 1: "RIGHT"}
        for folder in ("left", "right"):
            for path in sorted(glob.glob(os.path.join(r"D:\trainsvm\data\gelo", folder,
                                                      "*.csv"))):
                pred, marks = dec.predict_csv(path)
                if len(pred) == 0:
                    continue
                votes = [names[p] for p in pred]
                maj = names[int(np.mean(pred) >= 0.5)]
                print(f"  {os.path.basename(path):<18} true={folder.upper():<5} "
                      f"vote={maj:<5}  marks {marks} -> {votes}")
        print("\nNOTE: every file here holds ONE class, so these are 15 "
              "decisions, not 72.\nMeasured file-level balanced accuracy of "
              "this pipeline on these recordings\nis 0.45 with permutation "
              "p = 0.83 - i.e. chance. See REPORT.md section 9.")

    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
