"""Alpha v1 eval set: ten examples, three layers, snapshot untouched."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "sample_scan.json"  # slim, made-up names, real stats


def test_alpha_v1_ten_examples_three_layers():
    manifest = json.loads(FIXTURE.read_text())["eval_alpha_v1"]
    assert manifest["dataset_id"] == "alpha_v1"
    assert manifest["snapshot_id"] == "snap_example_eval_001"
    assert [row["review_number"] for row in manifest["examples"]] == list(range(1, 11))

    decisions = manifest["decisions"]

    for row in manifest["examples"]:
        example = row
        n = row["review_number"]
        assert example["review_number"] == n
        assert set(example) >= {"evidence", "classifier_result", "human_decision"}
        # layers are siblings, not nested inside each other
        assert "classifier_result" not in example["evidence"]
        assert "human_decision" not in example["evidence"]
        assert "evidence" not in example["classifier_result"]
        assert "human_decision" not in example["classifier_result"]
        assert "label" in example["classifier_result"]
        assert example["human_decision"]["decision"] == "APPROVED_REMOVAL_CANDIDATE"
        assert example["human_decision"]["executed"] is False
        assert example["human_decision"]["decision"] == decisions[str(n)]["decision"]
        assert example["username"] == decisions[str(n)]["username"]
        assert example["alpha_test_label_only"] is True
