import hashlib
import json

import pytest

from worklife.storage import canonical
from worklife.workspace import Workspace


def employer_claim(**extra):
    return {
        "claim": "Employer advertises two interview stages and remote work",
        "source_url": "https://acme.example/jobs",
        "observed_at": "2026-10-27T10:00:00Z",
        "evidence_kind": "advertised",
        **extra,
    }


@pytest.mark.parametrize(
    "kind,subject",
    [
        ("lesson", "cv"),
        ("experience", "acme.example"),
        ("employer", "candidate-123"),
        ("employer", "cv"),
    ],
)
def test_shared_database_rejects_non_employer_topics(tmp_path, kind, subject):
    w = Workspace(tmp_path)
    with pytest.raises(ValueError):
        w.ledger.publish(kind, subject, employer_claim())
    assert w.ledger.verify()["events"] == 0


def test_shared_metrics_and_tags_are_employer_specific(tmp_path):
    w = Workspace(tmp_path)
    with pytest.raises(ValueError, match="metrics"):
        w.ledger.publish("employer", "acme.example", employer_claim(metrics={"candidate_score": 90}))
    with pytest.raises(ValueError, match="tags"):
        w.ledger.publish("employer", "acme.example", employer_claim(tags=["cv_strategy"]))
    event = w.ledger.publish(
        "employer",
        "acme.example",
        employer_claim(metrics={"response_days": 2, "hiring_stages": 2}, tags=["hiring_process", "remote"]),
    )
    assert event["subject"] == "acme.example"


def test_valid_signature_does_not_allow_worker_topics_from_a_peer(tmp_path):
    a, b = Workspace(tmp_path / "a"), Workspace(tmp_path / "b")
    event = a.ledger.publish("employer", "acme.example", employer_claim())
    event["subject"] = "candidate-123"
    body = {k: v for k, v in event.items() if k not in {"event_id", "signature"}}
    event["event_id"] = hashlib.sha256(canonical(body)).hexdigest()
    event["signature"] = a.ledger.key.sign(bytes.fromhex(event["event_id"])).hex()
    with pytest.raises(ValueError, match="domain"):
        b.ledger.import_events([event])
    assert b.ledger.verify()["events"] == 0


def test_personal_cv_experiments_never_enter_employer_replication(tmp_path):
    w = Workspace(tmp_path)
    w.save_profile(
        {
            "name": "PRIVATE_WORKER",
            "facts": [{"id": "private", "text": "PRIVATE_ACHIEVEMENT", "source": "private document"}],
        }
    )
    variants = [w.create_cv(str(i), ["private"], "PRIVATE_CV")["id"] for i in range(2)]
    w.create_experiment("PRIVATE_CV_HYPOTHESIS", variants)
    w.ledger.publish("employer", "acme.example", employer_claim())
    exported = w.ledger.export()
    assert {e["kind"] for e in exported} == {"employer"}
    assert {e["subject"] for e in exported} == {"acme.example"}
    assert "PRIVATE_" not in json.dumps(exported)
