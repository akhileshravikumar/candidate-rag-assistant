import json
from copy import deepcopy

from app.service import Service
from app.models import Query
from evaluation.run import CASES, score, summarize, validate_labels
from test_core import CHUNKS, FakeGateway, FakeStore


def test_gold_labels_resolve_to_real_evidence():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    validate_labels(cases, CHUNKS)
    assert len(cases) == 15
    assert {c["split"] for c in cases} == {"dev", "test"}


def test_metrics_perfect_and_missing_evidence():
    case = json.loads(CASES.read_text(encoding="utf-8"))[0]
    result = Service(FakeStore(), FakeGateway()).ask(Query(
        question=case["question"], candidate_ids=case["candidate_ids"]
    ))
    metrics = score(case, result)
    assert metrics["retrieval_recall"] == metrics["retrieval_hit"] == 1
    assert metrics["evidence_point_recall"] == 1
    assert metrics["citation_valid"] == metrics["citation_total"] == 1
    result = deepcopy(result)
    result.update(status="abstained", findings=[], evidence=[])
    missing = score(case, result)
    assert missing["retrieval_recall"] == missing["retrieval_hit"] == 0
    assert missing["evidence_point_recall"] == 0
    assert missing["citation_total"] == 0


def test_errors_are_not_hidden_as_passes_or_safety_success():
    rows = [{"id": "broken", "expected_status": "answered", "answerable": True, "error_type": "Timeout"}]
    summary = summarize(rows)
    assert summary["errors"] == 1 and summary["completed"] == 0
    assert summary["status_accuracy"] == 0
    assert summary["citation_validity"] is None
    assert summary["evidence_point_recall_proxy"] is None