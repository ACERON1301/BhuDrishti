"""Public ML module for the backend vibration classifier.

The implementation is kept in ``backend.model`` for backwards-compatible imports;
this package is the stable extension point for replacing synthetic training data.
"""
try:
    from ..model import ARTIFACT, FEATURES, LABELS, MODEL_PATH, classify, extract_features, synthetic_training_data, train_model
except ImportError:
    from model import ARTIFACT, FEATURES, LABELS, MODEL_PATH, classify, extract_features, synthetic_training_data, train_model

__all__ = [
    "ARTIFACT",
    "FEATURES",
    "LABELS",
    "MODEL_PATH",
    "classify",
    "extract_features",
    "synthetic_training_data",
    "train_model",
]
