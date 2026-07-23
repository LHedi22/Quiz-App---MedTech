"""Subtask 5.3 DoD checks: bubble fill classifier."""

from __future__ import annotations

import ast
import inspect
from collections import Counter

import numpy as np
import pytest

from app.ml.bubble_classifier import train as train_module
from app.ml.bubble_classifier.synthetic_data import (
    generate_ambiguous_dataset,
    generate_labeled_dataset,
)
from app.ml.omr import classify as classify_module
from app.ml.omr.classify import CONFIDENCE_THRESHOLD, classify_bubble

HELD_OUT_ACCURACY_TARGET = 0.95
AMBIGUOUS_ROUTING_TARGET = 0.90


@pytest.fixture(scope="module", autouse=True)
def trained_model():
    """(Re)train before this module's tests so they exercise the real
    train -> saved artifact -> inference path end to end, not a stale
    artifact left over from a previous run."""
    stats = train_module.train()
    classify_module._load_model.cache_clear()
    return stats


def test_held_out_accuracy_meets_target(trained_model):
    assert trained_model["held_out_accuracy"] >= HELD_OUT_ACCURACY_TARGET, (
        f"held-out accuracy {trained_model['held_out_accuracy']:.4f} below "
        f"target {HELD_OUT_ACCURACY_TARGET}"
    )


def test_unambiguous_filled_and_empty_examples_are_never_misclassified():
    """A second, independently-seeded unambiguous set (not the train/test
    split itself) should still classify correctly whenever the model does
    commit to a label - it may abstain (ambiguous) but must never be
    confidently wrong."""
    rng = np.random.default_rng(20260724)
    crops, labels = generate_labeled_dataset(rng, n_per_class=150)

    wrong = 0
    for crop, true_label in zip(crops, labels):
        predicted, _confidence = classify_bubble(crop)
        if predicted == "ambiguous":
            continue
        if (predicted == "filled") != bool(true_label):
            wrong += 1

    assert wrong == 0


@pytest.mark.parametrize("kind", ["mid_fill", "light_mark", "partial_erasure"])
def test_genuinely_ambiguous_cases_are_routed_to_low_confidence(kind):
    """Mid-range fills, faint/light marks, and heavily partially-erased
    bubbles should overwhelmingly be routed to "ambiguous" rather than
    confidently (and possibly wrongly) called filled/empty."""
    rng = np.random.default_rng(hash(kind) % (2**32))
    crops, kinds = generate_ambiguous_dataset(rng, n=300)

    matching = [crop for crop, k in zip(crops, kinds) if k == kind]
    assert len(matching) > 30, "sanity: enough samples of this kind were generated"

    routed_ambiguous = sum(1 for crop in matching if classify_bubble(crop)[0] == "ambiguous")
    rate = routed_ambiguous / len(matching)
    assert rate >= AMBIGUOUS_ROUTING_TARGET, (
        f"only {rate:.2%} of '{kind}' cases routed to ambiguous "
        f"(target {AMBIGUOUS_ROUTING_TARGET:.0%})"
    )


def test_stray_mark_near_an_empty_bubble_is_never_confidently_called_filled():
    """An empty bubble with an incidental stray mark nearby (but not on it)
    is correctly "empty" - the risk this guards against is a false-positive
    fill, not under-confidence, so the bar here is "never wrongly filled",
    not "must be ambiguous"."""
    rng = np.random.default_rng(555)
    crops, kinds = generate_ambiguous_dataset(rng, n=300)
    matching = [crop for crop, k in zip(crops, kinds) if k == "stray_only"]
    assert len(matching) > 30

    for crop in matching:
        label, _confidence = classify_bubble(crop)
        assert label != "filled"


def test_ambiguous_label_always_reflects_a_below_threshold_confidence():
    rng = np.random.default_rng(7)
    crops, _kinds = generate_ambiguous_dataset(rng, n=100)
    for crop in crops:
        label, confidence = classify_bubble(crop)
        if label == "ambiguous":
            assert confidence < CONFIDENCE_THRESHOLD
        else:
            assert confidence >= CONFIDENCE_THRESHOLD


def test_model_artifact_exists_on_disk_after_training(trained_model):
    from app.ml.bubble_classifier.train import MODEL_PATH

    assert MODEL_PATH.exists()
    assert MODEL_PATH.stat().st_size > 0


def test_inference_module_does_not_import_training_code():
    """Proves train/inference are properly decoupled: a deployment only
    needs classify.py + features.py + the saved model.joblib artifact. Walks
    the actual import statements (not a substring search - the module's own
    docstring legitimately mentions "trained"/"training") to confirm nothing
    pulls in the training module or scikit-learn's training APIs."""
    tree = ast.parse(inspect.getsource(classify_module))
    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.add(node.module)

    assert not any("bubble_classifier.train" in name for name in imported_names)
    assert not any(name.startswith("sklearn") for name in imported_names)
    assert not hasattr(classify_module, "generate_labeled_dataset")
    assert not hasattr(classify_module, "LogisticRegression")


def test_classify_bubble_loads_the_saved_artifact_and_runs_standalone(trained_model):
    """Clears the inference module's cached model and confirms it reloads
    straight from disk (the artifact train.py just saved) and produces a
    sane result - simulating a fresh process that only ever imports
    classify.py, never train.py."""
    classify_module._load_model.cache_clear()

    rng = np.random.default_rng(1)
    crops, labels = generate_labeled_dataset(rng, n_per_class=5)
    label, confidence = classify_bubble(crops[0])

    assert label in {"filled", "empty", "ambiguous"}
    assert 0.0 <= confidence <= 1.0


def test_all_ambiguous_and_unambiguous_label_kinds_seen_at_least_once():
    """Sanity check on the synthetic generator itself - if a kind stopped
    being produced the routing-rate tests above could pass vacuously."""
    rng = np.random.default_rng(3)
    _crops, kinds = generate_ambiguous_dataset(rng, n=400)
    counts = Counter(kinds)
    for expected_kind in ("mid_fill", "partial_erasure", "light_mark", "stray_only"):
        assert counts[expected_kind] > 0
