"""Trains the bubble-fill classifier and saves the model artifact to disk.

TRAINING DATA (see app/ml/README.md for the full writeup): entirely
synthetic, programmatically-rendered bubble crops - there is no real
scanned-exam data available yet. This is a deliberate placeholder,
documented as a known limitation, to be replaced by real-scan data once
some has been collected.

Run standalone: `python -m app.ml.bubble_classifier.train`
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

from app.ml.bubble_classifier.features import extract_features
from app.ml.bubble_classifier.synthetic_data import generate_labeled_dataset

MODEL_PATH = Path(__file__).resolve().parent / "model.joblib"
RANDOM_SEED = 20260723
TEST_SIZE = 0.3


def build_feature_matrix(crops: list[np.ndarray]) -> np.ndarray:
    return np.stack([extract_features(crop) for crop in crops])


def train(n_per_class: int = 400, random_seed: int = RANDOM_SEED) -> dict:
    """Fit the classifier on a fresh synthetic dataset and save it to
    MODEL_PATH. Returns held-out evaluation stats (not persisted - a
    separate DoD test re-derives and asserts on this same number)."""
    rng = np.random.default_rng(random_seed)
    crops, labels = generate_labeled_dataset(rng, n_per_class=n_per_class)

    features = build_feature_matrix(crops)
    targets = np.array(labels)

    x_train, x_test, y_train, y_test = train_test_split(
        features, targets, test_size=TEST_SIZE, random_state=random_seed, stratify=targets
    )

    model = LogisticRegression(max_iter=1000)
    model.fit(x_train, y_train)
    held_out_accuracy = float(model.score(x_test, y_test))

    joblib.dump(model, MODEL_PATH)

    return {
        "held_out_accuracy": held_out_accuracy,
        "n_train": len(x_train),
        "n_test": len(x_test),
        "model_path": str(MODEL_PATH),
    }


if __name__ == "__main__":
    stats = train()
    print(f"held-out accuracy: {stats['held_out_accuracy']:.4f}")
    print(f"train/test split: {stats['n_train']}/{stats['n_test']}")
    print(f"model saved to: {stats['model_path']}")
