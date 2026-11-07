"""
Acceptance test of the classifier integration (slow: real model, 721 leaves).

Runs the backend's real preprocessing and the full decision rule on the
test split of the training project's crops, with the true crop of each leaf
as the chosen crop, and compares with the figures measured on this exact
.tflite file (±0.5 point):
    without threshold:   94.6 % accuracy (every leaf answered)
    threshold 0.70:      92.1 % of leaves answered, 97.1 % accuracy among them
A larger gap means the preprocessing differs from training (BGR instead of
RGB, normalization, another resize, a center crop).

    pytest -m slow tests/test_model_acceptance.py -s
Manifest: GREEN_ACCEPTANCE_MANIFEST, default below (columns crop_path,
relative to the manifest folder, split, class_id).
"""

import csv
import os

import numpy as np
import pytest

import inference

MANIFEST = os.environ.get(
    "GREEN_ACCEPTANCE_MANIFEST",
    r"C:\Users\user\Documents\Innovation\GREEN\ForKigali\FieldPlant_9classes\crops_v1\manifest.csv",
)
THRESHOLD = 0.70        # the figures below were measured at 0.70, whatever the configured value
TOLERANCE = 0.5         # percentage points
EXPECTED = {"accuracy_no_threshold": 94.6, "answered": 92.1, "accuracy_answered": 97.1}


@pytest.mark.slow
def test_acceptance_on_the_test_split():
    if not os.path.exists(MANIFEST):
        pytest.skip(f"manifest not found: {MANIFEST}")
    root = os.path.dirname(MANIFEST)
    with open(MANIFEST, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["split"] == "test"]
    assert len(rows) == 721

    correct = answered = answered_correct = 0
    statuses = {"ok": 0, "unknown": 0, "wrong_crop": 0}
    for r in rows:
        true = int(r["class_id"])
        with open(os.path.join(root, r["crop_path"]), "rb") as img:
            probs = inference.forward(inference.preprocess(img.read()))
        assert abs(float(probs.sum()) - 1.0) < 1e-3
        chosen_crop = inference.crop_of(inference.LABELS[true])

        status, best, _ = inference.decide(probs, chosen_crop, THRESHOLD)
        statuses[status] += 1
        correct += int(np.argmax(probs)) == true
        if status == "ok":
            answered += 1
            answered_correct += best == true

    n = len(rows)
    got = {
        "accuracy_no_threshold": 100 * correct / n,
        "answered": 100 * answered / n,
        "accuracy_answered": 100 * answered_correct / answered,
    }
    print(f"\n{n} test leaves, threshold {THRESHOLD}: statuses {statuses}")
    for k, v in got.items():
        print(f"  {k:24s} {v:6.2f} %   (expected {EXPECTED[k]} ± {TOLERANCE})")
    for k, v in got.items():
        assert abs(v - EXPECTED[k]) <= TOLERANCE, f"{k}: {v:.2f} % vs {EXPECTED[k]} %"
