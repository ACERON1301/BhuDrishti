"""Explainable vibration classifier for the GLOF prototype."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

FEATURES = ["peak_amplitude", "rms", "zero_crossing_rate", "dominant_frequency_hz", "decay_envelope"]
LABELS = ["normal", "event"]
SAMPLE_RATE_HZ = 100.0
MODEL_PATH = Path(__file__).with_name("model_artifact.json")


def extract_features(window: list[float], sample_rate_hz: float = SAMPLE_RATE_HZ) -> dict[str, float]:
    """Extract transparent time/frequency features from one sensor window."""
    signal = np.asarray(window, dtype=float)
    if signal.size < 8 or not np.isfinite(signal).all():
        raise ValueError("sensor window must contain at least 8 finite numeric samples")
    centered = signal - signal.mean()
    spectrum = np.abs(np.fft.rfft(centered))
    frequencies = np.fft.rfftfreq(signal.size, d=1 / sample_rate_hz)
    dominant_index = int(np.argmax(spectrum[1:]) + 1) if spectrum.size > 1 else 0
    split = max(1, signal.size // 10)
    early = float(np.mean(np.abs(centered[:split])))
    late = float(np.mean(np.abs(centered[-split:])))
    return {
        "peak_amplitude": round(float(np.max(np.abs(centered))), 6),
        "rms": round(float(np.sqrt(np.mean(centered**2))), 6),
        "zero_crossing_rate": round(float(np.mean(np.diff(np.signbit(centered)) != 0)), 6),
        "dominant_frequency_hz": round(float(frequencies[dominant_index]), 6),
        "decay_envelope": round(float(max(0.0, 1 - late / max(early, 1e-9))), 6),
        "duration_seconds": round(float(signal.size / sample_rate_hz), 6),
    }


def synthetic_training_data(seed: int = 42, samples: int = 10000, window_size: int = 200) -> tuple[np.ndarray, np.ndarray]:
    """Generate ambient noise and impulsive collapse signatures.

    Replace this function with a loader for labelled sensor/USGS windows when field data
    becomes available; the feature extraction and classifier contract remains unchanged.
    """
    rng = np.random.default_rng(seed)
    rows: list[list[float]] = []
    labels: list[int] = []
    t = np.arange(window_size) / SAMPLE_RATE_HZ
    for label in (0, 1):
        for _ in range(samples // 2):
            if label == 0:
                noise_scale = rng.uniform(0.015, 0.14)
                baseline = rng.uniform(-0.04, 0.04)
                slow_drift = rng.uniform(0, 0.05) * np.sin(2 * np.pi * rng.uniform(0.2, 2) * t)
                signal = baseline + slow_drift + rng.normal(0, noise_scale, window_size)
            else:
                attack = rng.uniform(0.35, 2.0)
                onset = rng.uniform(0.02, 0.25)
                frequency = rng.uniform(5, 35)
                carrier = np.sin(2 * np.pi * frequency * t + rng.uniform(0, 2 * np.pi))
                envelope = np.exp(-rng.uniform(2.0, 7.0) * np.maximum(t - onset, 0))
                secondary = rng.uniform(0, 0.3) * np.sin(2 * np.pi * rng.uniform(1, 6) * t)
                signal = attack * carrier * envelope + secondary + rng.normal(0, rng.uniform(0.03, 0.16), window_size)
            rows.append([extract_features(signal.tolist())[name] for name in FEATURES])
            labels.append(label)
    return np.asarray(rows), np.asarray(labels)


def train_model() -> dict[str, Any]:
    x, y = synthetic_training_data()
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.2, random_state=42, stratify=y
    )
    scaler = StandardScaler().fit(x_train)
    classifier = LogisticRegression(
        max_iter=1000, class_weight="balanced", random_state=42
    ).fit(scaler.transform(x_train), y_train)
    return {
        "features": FEATURES,
        "labels": LABELS,
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
        "coefficients": classifier.coef_.tolist(),
        "intercepts": classifier.intercept_.tolist(),
        "training_samples": len(y_train),
        "validation_samples": len(y_test),
        "validation_accuracy": round(float(accuracy_score(y_test, classifier.predict(scaler.transform(x_test)))), 4),
        "validation_balanced_accuracy": round(float(balanced_accuracy_score(y_test, classifier.predict(scaler.transform(x_test)))), 4),
    }


def _load_artifact() -> dict[str, Any]:
    if MODEL_PATH.exists():
        try:
            return json.loads(MODEL_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError):
            pass
    artifact = train_model()
    MODEL_PATH.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return artifact


ARTIFACT = _load_artifact()


def classify(window: list[float]) -> dict[str, Any]:
    features = extract_features(window)
    vector = np.asarray([features[name] for name in FEATURES], dtype=float)
    standardized = (vector - np.asarray(ARTIFACT["mean"])) / np.asarray(ARTIFACT["scale"])
    logit = float(np.asarray(ARTIFACT["coefficients"])[0] @ standardized + ARTIFACT["intercepts"][0])
    event_probability = float(1 / (1 + np.exp(-logit)))
    label = "event" if event_probability >= 0.5 else "normal"
    return {
        "classification": label,
        "confidence": round(event_probability if label == "event" else 1 - event_probability, 4),
        "features": features,
    }
