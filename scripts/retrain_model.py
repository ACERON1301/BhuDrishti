"""Regenerate the deterministic model artifact used by the API."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.ml.classifier import MODEL_PATH, train_model  # noqa: E402


if __name__ == "__main__":
    artifact = train_model()
    MODEL_PATH.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(f"Wrote {MODEL_PATH} ({artifact['training_samples']} synthetic samples)")
