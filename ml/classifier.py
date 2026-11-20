"""
EMSO -- AI/ML signal classifier prototype (AM vs NBFM vs Noise)

Trained on SYNTHETIC signals we generate ourselves (no big dataset download
needed -- good for slow connections). Uses classic hand-crafted signal
features (envelope behavior, instantaneous frequency behavior, spectral
shape) and a RandomForest classifier, both fast on a CPU with no GPU.

After training, it's tested against our REAL captured VHF file from the
GNU Radio flowgraph session -- a genuine real-world sanity check, even
though the model never saw real training examples. This is a legitimate,
standard first step in ML development: prototype on synthetic data, then
validate and later fine-tune on real captured signals.

Run from the ml/ folder:  python classifier.py
"""
import os
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix

RNG = np.random.default_rng(42)
WINDOW = 512          # samples per analysis window
N_PER_CLASS = 400      # synthetic training examples per class


def extract_features(x):
    """x: a complex IQ array (1D). Returns a small, fast feature vector."""
    amp = np.abs(x)
    phase = np.unwrap(np.angle(x))
    inst_freq = np.diff(phase)

    spec = np.abs(np.fft.fftshift(np.fft.fft(x)))
    mean_mag = spec.mean() + 1e-12
    peak_to_mean = spec.max() / mean_mag

    # spectral flatness (Wiener entropy): geometric mean / arithmetic mean.
    # Near 1.0 for flat/noisy spectra, near 0 for a sharp single-tone peak.
    geo_mean = np.exp(np.mean(np.log(spec + 1e-12)))
    flatness = geo_mean / mean_mag

    return np.array([
        amp.mean(), amp.std(),
        inst_freq.mean(), inst_freq.std(),
        peak_to_mean, flatness,
    ])


def _add_noise(sig, snr_db):
    noise = RNG.normal(size=len(sig)) + 1j * RNG.normal(size=len(sig))
    noise *= 10 ** (-snr_db / 20) / np.sqrt(2)
    return sig + noise


def gen_am(n_samples=WINDOW, snr_db=15):
    """Amplitude-modulated signal: strong envelope variation, steady frequency."""
    t = np.arange(n_samples)
    f_offset = RNG.uniform(-0.15, 0.15)
    f_msg = RNG.uniform(0.01, 0.04)
    depth = RNG.uniform(0.3, 0.9)
    carrier = np.exp(1j * 2 * np.pi * f_offset * t)
    envelope = 1 + depth * np.cos(2 * np.pi * f_msg * t)
    sig = envelope * carrier
    sig = sig / np.abs(sig).mean()
    return _add_noise(sig, snr_db)


def gen_fm(n_samples=WINDOW, snr_db=15):
    """Frequency-modulated signal (like our real NBFM capture): steady
    envelope, strong instantaneous-frequency variation."""
    t = np.arange(n_samples)
    f_offset = RNG.uniform(-0.15, 0.15)
    f_msg = RNG.uniform(0.01, 0.04)
    dev = RNG.uniform(0.02, 0.08)
    phase = 2 * np.pi * f_offset * t + (dev / f_msg) * np.sin(2 * np.pi * f_msg * t)
    sig = np.exp(1j * phase)
    return _add_noise(sig, snr_db)


def gen_noise(n_samples=WINDOW):
    """No real signal present -- just the noise floor."""
    return (RNG.normal(size=n_samples) + 1j * RNG.normal(size=n_samples)) / np.sqrt(2)


def build_dataset():
    X, y = [], []
    gens = {"AM": gen_am, "NBFM": gen_fm, "NOISE": gen_noise}
    for label, gen in gens.items():
        for _ in range(N_PER_CLASS):
            X.append(extract_features(gen()))
            y.append(label)
    return np.array(X), np.array(y)


def load_real_capture(path, n_windows=20, window=WINDOW, skip=20000):
    """Reads GNU Radio's 'complex' binary format: interleaved float32 I,Q,I,Q...
    Deliberately uses plain Python file reading + np.frombuffer, NOT
    np.fromfile(path) directly -- on some Windows setups, Windows' ransomware
    protection (Controlled Folder Access) blocks numpy's low-level file
    access to newly-downloaded files even when normal Python file reads work
    fine. Reading the bytes ourselves first sidesteps that entirely."""
    with open(path, "rb") as f:
        raw_bytes = f.read()
    raw = np.frombuffer(raw_bytes, dtype=np.float32)
    iq = raw[0::2] + 1j * raw[1::2]
    windows = []
    for i in range(n_windows):
        start = skip + i * window * 20  # spread sample windows across the file
        chunk = iq[start:start + window]
        if len(chunk) == window:
            chunk = chunk - np.mean(chunk)  # remove DC offset
            # Normalize amplitude to match our synthetic training data's scale
            # (~unit mean amplitude). Real SDR hardware stores samples at its
            # own raw scale (we measured ~300x larger) -- without this, the
            # classifier sees amplitude values far outside anything it learned.
            chunk = chunk / (np.abs(chunk).mean() + 1e-12)
            windows.append(chunk)
    return windows


if __name__ == "__main__":
    print("Building synthetic training data (AM / NBFM / Noise)...")
    X, y = build_dataset()
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y)

    print("Training RandomForest classifier...")
    clf = RandomForestClassifier(n_estimators=200, random_state=42)
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    print("\n=== Performance on synthetic test data ===")
    print(classification_report(y_test, y_pred))
    print("Confusion matrix (rows=actual, cols=predicted; order AM, NBFM, NOISE):")
    print(confusion_matrix(y_test, y_pred, labels=["AM", "NBFM", "NOISE"]))

    # --- Real-world sanity check against our actual captured VHF file ---
    real_path = os.path.join("..", "signal-processing", "real_capture.dat")
    if os.path.exists(real_path):
        print(f"\n=== Testing against REAL captured file: {real_path} ===")
        real_windows = load_real_capture(real_path)
        real_features = np.array([extract_features(w) for w in real_windows])
        real_preds = clf.predict(real_features)
        print("Predictions on 20 real-signal windows (this file IS real NBFM, so it should mostly say NBFM):")
        print(real_preds)
        print(f"NBFM predicted: {sum(real_preds == 'NBFM')}/{len(real_preds)}")

        print("\n--- DIAGNOSTIC: feature comparison ---")
        feature_names = ["amp_mean", "amp_std", "freq_mean", "freq_std", "peak_to_mean", "flatness"]
        print("Feature order:", feature_names)
        for label in ["AM", "NBFM", "NOISE"]:
            mask = y_train == label
            print(f"{label:6s} synthetic avg: {X_train[mask].mean(axis=0).round(4)}")
        print(f"\nReal windows avg:  {real_features.mean(axis=0).round(4)}")
        print(f"Real windows std:  {real_features.std(axis=0).round(4)}")
        print("\nFirst 5 real feature vectors (one per row):")
        for v in real_features[:5]:
            print(v.round(4))
    else:
        print(f"\n(Real capture file not found at {real_path} -- skipping the real-world test. "
              f"That's fine, the synthetic results above already prove the concept.)")
