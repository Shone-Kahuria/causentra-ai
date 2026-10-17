from app import demo, main
from app.evaluation import evaluate


def test_replay_numeric_outputs_are_reproducible(tmp_path):
    main.DB_PATH = tmp_path / "replay.db"
    first = demo.replay()
    second = demo.replay()
    assert first == second
    assert first["projected_shortage_units"] == 8
    assert first["scenarios"][2]["incremental_cost_cents"] == 6000


def test_evaluation_reports_measured_rules_baseline():
    report = evaluate()
    assert report["sample_size"] == 7
    assert report["confusion_matrix"] == {"tp": 3, "fp": 0, "fn": 1, "tn": 3}
    assert report["detection_recall"] == 3 / 4
    assert "No AMD or agent baseline measured" in report["limitations"]
