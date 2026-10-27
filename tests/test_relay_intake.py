import json

from worklife.workspace import Workspace


def record(w):
    return w.ledger.publish(
        "employer",
        "company.example",
        {
            "claim": "Employer publishes its hiring process",
            "source_url": "https://company.example/jobs",
            "observed_at": "2026-10-27T10:00:00Z",
            "evidence_kind": "advertised",
        },
    )


def test_relay_intake_accepts_signed_employer_data_and_ignores_general_issues(tmp_path):
    from worklife.relay_intake import MARKER, build_snapshot

    event = record(Workspace(tmp_path))
    snapshot = build_snapshot(
        {"protocol": 1, "events": []},
        [
            {"body": "Please add a feature"},
            {"body": MARKER + json.dumps({"protocol": 1, "events": [event]})},
        ],
    )
    assert snapshot["events"] == [event]
    assert snapshot["protocol"] == 1


def test_relay_intake_keeps_original_after_tampering_and_is_idempotent(tmp_path):
    from worklife.relay_intake import MARKER, build_snapshot

    event = record(Workspace(tmp_path))
    old = {"protocol": 1, "events": [event]}
    forged = json.loads(json.dumps(event))
    forged["payload"]["claim"] = "Forged"
    issue = {"body": MARKER + json.dumps({"protocol": 1, "events": [forged]})}
    result = build_snapshot(old, [issue])
    assert result["events"] == [event]
    assert result["validation"]["rejected"] == 1
    assert build_snapshot(result, [issue]) == result


def fragments(event, user=17, group="a" * 32):
    from worklife.relay_intake import MARKER
    from worklife.storage import canonical

    encoded = canonical(event).decode()
    parts = [encoded[: len(encoded) // 2], encoded[len(encoded) // 2 :]]
    return [
        {
            "user": {"id": user},
            "body": MARKER
            + json.dumps(
                {
                    "protocol": 1,
                    "fragment": {
                        "event_id": event["event_id"],
                        "group": group,
                        "index": index,
                        "total": len(parts),
                        "data": part,
                    },
                }
            ),
        }
        for index, part in enumerate(parts)
    ]


def test_fragment_intake_requires_complete_same_submitter_group(tmp_path):
    from worklife.relay_intake import build_snapshot

    event = record(Workspace(tmp_path))
    parts = fragments(event)
    empty = {"protocol": 1, "events": []}
    assert build_snapshot(empty, parts[:1])["events"] == []
    cross_user = [parts[0], {**parts[1], "user": {"id": 18}}]
    assert build_snapshot(empty, cross_user)["events"] == []
    result = build_snapshot(empty, [parts[1], parts[0], parts[0]])
    assert result["events"] == [event]
    assert result["validation"]["rejected"] == 0


def test_fragment_intake_rejects_conflicting_chunks_event_ids_and_bad_signatures(tmp_path):
    from worklife.relay_intake import MARKER, build_snapshot

    event = record(Workspace(tmp_path))
    parts = fragments(event)
    packet = json.loads(parts[0]["body"][len(MARKER) :])
    packet["fragment"]["data"] += "conflict"
    conflict = {"user": {"id": 17}, "body": MARKER + json.dumps(packet)}
    result = build_snapshot({"protocol": 1, "events": []}, [*parts, conflict])
    assert result["events"] == [] and result["validation"]["rejected"] > 0

    for field in ("event_id", "signature"):
        modified = {**event, field: "0" * len(event[field])}
        issues = fragments(modified)
        if field == "event_id":
            # A complete, correctly signed event cannot be advertised under another event ID.
            issues = fragments(event)
            for issue in issues:
                packet = json.loads(issue["body"][len(MARKER) :])
                packet["fragment"]["event_id"] = "0" * 64
                issue["body"] = MARKER + json.dumps(packet)
        result = build_snapshot({"protocol": 1, "events": []}, issues)
        assert result["events"] == [] and result["validation"]["rejected"] > 0


def test_fragment_intake_never_reassembles_without_github_submitter_identity(tmp_path):
    from worklife.relay_intake import build_snapshot

    event = record(Workspace(tmp_path))
    result = build_snapshot(
        {"protocol": 1, "events": []}, [{"body": issue["body"]} for issue in fragments(event)]
    )
    assert result["events"] == []
    assert result["validation"]["rejected"] == 2
