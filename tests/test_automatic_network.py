import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from worklife.storage import canonical
from worklife.workspace import Workspace


def record(claim="Employer advertises remote work"):
    return {
        "claim": claim,
        "evidence_kind": "advertised",
        "source_url": "https://example.org/jobs",
        "observed_at": "2026-10-27T10:00:00Z",
    }


def publish(workspace, domain="acme.example"):
    return workspace.ledger.publish("employer", domain, record())


def test_repair_quarantines_tampered_rows_preserving_private_data(tmp_path):
    w = Workspace(tmp_path)
    original = publish(w)
    identity = w.ledger.author_id
    w.save_profile({"name": "Private person", "facts": []})
    w.store.put("application", "private", {"secret": "private"})
    forged = json.loads(json.dumps(original))
    forged["payload"]["claim"] = "forged"
    with w.store.connect() as db:
        db.execute("UPDATE events SET document=?", (json.dumps(forged),))
    with pytest.raises(ValueError):
        w.ledger.verify()
    assert w.ledger.repair()["recovered"] == 1
    assert w.ledger.all() == [original]
    assert w.ledger.author_id == identity
    assert w.get_profile()["name"] == "Private person"
    assert w.store.get("application", "private") == {"secret": "private"}
    quarantined = list((tmp_path / "employer_quarantine").glob("*.json"))
    assert len(quarantined) == 1
    assert json.loads(quarantined[0].read_text())[0]["document"] == json.dumps(forged)


def test_signed_checkpoint_detects_suffix_deletion_and_restores_after_restart(tmp_path):
    w = Workspace(tmp_path)
    first, second = publish(w), publish(w, "other.example")
    with w.store.connect() as db:
        db.execute("DELETE FROM events WHERE event_id=?", (second["event_id"],))
    reopened = Workspace(tmp_path)
    with pytest.raises(ValueError, match="checkpoint"):
        reopened.ledger.verify()
    assert reopened.ledger.repair()["recovered"] == 2
    assert reopened.ledger.all() == [first, second]


def test_corrupt_archive_refuses_repair_without_touching_database(tmp_path):
    w = Workspace(tmp_path)
    event = publish(w)
    (tmp_path / "employer_archive" / f"{event['event_id']}.json").write_text("{}")
    with w.store.connect() as db:
        db.execute("DELETE FROM events")
    with pytest.raises(ValueError, match="archive"):
        w.ledger.repair()
    with w.store.connect() as db:
        assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 0
    assert not (tmp_path / "employer_quarantine").exists()


def test_remote_assisted_repair_requires_all_checkpoint_heads(tmp_path):
    w = Workspace(tmp_path)
    first, second = publish(w), publish(w, "other.example")
    for path in (tmp_path / "employer_archive").glob("*.json"):
        path.unlink()
    with w.store.connect() as db:
        db.execute("DELETE FROM events")
    with pytest.raises(ValueError, match="checkpoint"):
        w.ledger.repair([first])
    assert w.ledger.repair([first, second])["recovered"] == 2


def test_complete_remote_recovers_corrupt_archive_after_quarantining_it(tmp_path):
    w = Workspace(tmp_path)
    first, second = publish(w), publish(w)
    archive = tmp_path / "employer_archive" / f"{second['event_id']}.json"
    archive.write_text("broken archive bytes")
    with w.store.connect() as db:
        db.execute("DELETE FROM events")
    with pytest.raises(ValueError):
        w.ledger.repair([first])
    assert archive.read_text() == "broken archive bytes"
    assert w.ledger.repair([first, second])["recovered"] == 2
    assert json.loads(archive.read_text()) == second
    quarantine = list((tmp_path / "employer_quarantine").glob("*.archive.json"))
    assert len(quarantine) == 1 and quarantine[0].read_text() == "broken archive bytes"
    assert w.ledger.all() == [first, second]


def test_missing_checkpoint_never_blesses_database_shorter_than_existing_archive(tmp_path):
    w = Workspace(tmp_path)
    first, second = publish(w), publish(w)
    (tmp_path / "employer-checkpoint.json").unlink()
    with w.store.connect() as db:
        db.execute("DELETE FROM events WHERE event_id=?", (second["event_id"],))
    reopened = Workspace(tmp_path)
    with pytest.raises(ValueError, match="archive"):
        reopened.ledger.verify()
    assert not (tmp_path / "employer-checkpoint.json").exists()
    assert reopened.ledger.repair()["recovered"] == 2
    assert reopened.ledger.all() == [first, second]


def test_dirty_status_stops_claiming_remote_confirmation_before_next_tick(tmp_path):
    from worklife.automatic_network import NetworkManager

    w = Workspace(tmp_path)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"protocol": 1, "events": []})

    manager = NetworkManager(
        w, client=httpx.Client(transport=httpx.MockTransport(handler)), token_provider=lambda: None
    )
    assert manager.tick()["protected_copies"] == 2
    publish(w)
    manager.mark_dirty()
    assert manager.status()["status"] == "local_only"
    assert manager.status()["pending"] == 1
    assert manager.status()["protected_copies"] == 1
    assert len(requests) == 1
    manager.tick()
    assert len(requests) == 2


def test_merge_isolates_bad_authors_keeps_known_fork_and_requires_predecessors(tmp_path):
    from worklife.automatic_network import merge_events

    a, b = Workspace(tmp_path / "a"), Workspace(tmp_path / "b")
    first = publish(a)
    a.backup(tmp_path / "backup")
    fork = Workspace.restore(tmp_path / "backup", tmp_path / "fork")
    second = publish(a)
    forked = publish(fork)
    other = publish(b, "other.example")
    invalid = json.loads(json.dumps(first))
    invalid["signature"] = "0" * 128
    result = merge_events([first, second], [forked, other, invalid])
    assert {e["event_id"] for e in result["events"]} == {
        first["event_id"],
        second["event_id"],
        other["event_id"],
    }
    assert result["rejected"] == 2
    assert result["conflicts"]
    assert merge_events([], [second])["pending"] == 1


def test_network_reads_without_auth_and_preserves_cache_offline(tmp_path):
    from worklife.automatic_network import NetworkManager

    origin, local = Workspace(tmp_path / "origin"), Workspace(tmp_path / "local")
    event = publish(origin)
    requests = []
    online = True

    def handler(request):
        requests.append(request)
        if not online:
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(200, json={"protocol": 1, "events": [event]})

    manager = NetworkManager(
        local, client=httpx.Client(transport=httpx.MockTransport(handler)), token_provider=lambda: None
    )
    assert manager.tick()["status"] == "healthy"
    assert manager.status()["protected_copies"] == 2
    assert manager.status()["employers"] == 1
    assert not any("Authorization" in r.headers for r in requests)
    manager.tick()
    assert len(requests) == 1
    online = False
    assert manager.tick(force=True)["status"] == "offline"
    assert local.ledger.all() == [event]
    assert manager.status()["last_sync"]


def test_network_pending_without_auth_and_issue_receipt_is_not_remote_confirmation(tmp_path):
    from worklife.automatic_network import INTAKE_MARKER, NetworkManager

    local = Workspace(tmp_path)
    event = publish(local)
    snapshot, submissions = [], []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"protocol": 1, "events": snapshot})
        submissions.append(json.loads(request.content))
        assert request.headers["Authorization"] == "Bearer private-test-token"
        return httpx.Response(201, json={"number": 123})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    manager = NetworkManager(local, client=client, token_provider=lambda: None)
    assert manager.tick()["pending"] == 1
    assert manager.status()["protected_copies"] == 1
    assert not submissions
    authorized = NetworkManager(local, client=client, token_provider=lambda: "private-test-token")
    assert authorized.tick()["pending"] == 1
    assert authorized.status()["protected_copies"] == 1
    assert len(submissions) == 1
    assert (
        submissions[0]["body"]
        == INTAKE_MARKER + canonical({"protocol": 1, "events": local.ledger.all()}).decode()
    )
    assert "private-test-token" not in json.dumps(local.store.list("network_submission"))
    restarted = NetworkManager(local, client=client, token_provider=lambda: "private-test-token")
    restarted.tick()
    assert len(submissions) == 1
    snapshot.append(event)
    assert restarted.tick(force=True)["status"] == "healthy"
    assert restarted.status()["protected_copies"] == 2
    assert restarted.status()["pending"] == 0


def test_network_repairs_damage_and_rejects_fake_record_without_poisoning_other_author(tmp_path):
    from worklife.automatic_network import NetworkManager

    local, origin = Workspace(tmp_path / "local"), Workspace(tmp_path / "origin")
    original = publish(local)
    good = publish(origin, "other.example")
    bad = json.loads(json.dumps(good))
    bad["payload"]["claim"] = "fabricated"
    with local.store.connect() as db:
        db.execute("UPDATE events SET subject='forged.example'")
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"protocol": 1, "events": [original, bad, good]})
        )
    )
    status = NetworkManager(local, client=client, token_provider=lambda: None).tick()
    assert status["status"] == "attention"
    assert status["repaired"] == 1
    assert status["invalid"] == 1
    assert {e["event_id"] for e in local.ledger.all()} == {original["event_id"], good["event_id"]}


def test_network_detects_remote_rollback_and_keeps_newer_history(tmp_path):
    from worklife.automatic_network import NetworkManager

    local, origin = Workspace(tmp_path / "local"), Workspace(tmp_path / "origin")
    first, second = publish(origin), publish(origin)
    snapshot = [first, second]
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"protocol": 1, "events": snapshot})
        )
    )
    manager = NetworkManager(local, client=client, token_provider=lambda: None)
    assert manager.tick()["status"] == "healthy"
    snapshot.pop()
    assert manager.tick(force=True)["status"] == "attention"
    assert manager.status()["rollback"] is True
    assert local.ledger.all() == [first, second]
    restarted = NetworkManager(local, client=client, token_provider=lambda: None)
    assert restarted.tick()["rollback"] is True


def test_confirmed_event_is_resubmitted_after_relay_rollback_once_per_confirmation(tmp_path):
    from worklife.automatic_network import NetworkManager

    w = Workspace(tmp_path)
    event = publish(w)
    snapshot, submissions = [], []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"protocol": 1, "events": snapshot})
        submissions.append(json.loads(request.content))
        return httpx.Response(201, json={"number": len(submissions)})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    manager = NetworkManager(w, client=client, token_provider=lambda: "test-token")
    assert manager.tick()["pending"] == 1
    assert len(submissions) == 1
    snapshot.append(event)
    assert manager.tick(force=True)["status"] == "healthy"
    snapshot.clear()
    assert manager.tick(force=True)["status"] == "attention"
    assert len(submissions) == 2
    restarted = NetworkManager(w, client=client, token_provider=lambda: "test-token")
    assert restarted.tick()["pending"] == 1
    assert len(submissions) == 2
    assert w.ledger.all() == [event]
    snapshot.append(event)
    assert restarted.tick(force=True)["status"] == "healthy"


def test_merge_rejects_signed_correction_of_someone_elses_record(tmp_path):
    from worklife.automatic_network import merge_events

    first_author, second_author = Workspace(tmp_path / "a"), Workspace(tmp_path / "b")
    first, other = publish(first_author), publish(second_author)
    body = {key: value for key, value in other.items() if key not in {"signature", "event_id"}}
    body.update(
        seq=2,
        prev=other["event_id"],
        kind="retraction",
        payload={**record(), "supersedes": first["event_id"]},
    )
    digest = hashlib.sha256(canonical(body)).hexdigest()
    fake = {
        **body,
        "event_id": digest,
        "signature": second_author.ledger.key.sign(bytes.fromhex(digest)).hex(),
    }
    second_author.ledger.check_event(fake)
    result = merge_events([first, other], [fake])
    assert result["rejected"] == 1
    assert len(result["events"]) == 2


def test_network_repairs_from_remote_when_local_archive_is_missing(tmp_path):
    from worklife.automatic_network import NetworkManager

    w = Workspace(tmp_path)
    event = publish(w)
    (tmp_path / "employer_archive" / f"{event['event_id']}.json").unlink()
    with w.store.connect() as db:
        db.execute("DELETE FROM events")
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"protocol": 1, "events": [event]})
        )
    )
    status = NetworkManager(w, client=client, token_provider=lambda: None).tick()
    assert status["repaired"] == 1
    assert status["status"] == "healthy"
    assert w.ledger.all() == [event]


def test_intake_batches_stay_below_issue_limit_and_http_error_remains_pending(tmp_path):
    from worklife.automatic_network import NetworkManager

    w = Workspace(tmp_path)
    for _ in range(3):
        w.ledger.publish("employer", "acme.example", record("A" * 25000))
    bodies = []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"protocol": 1, "events": []})
        body = json.loads(request.content)["body"]
        bodies.append(body)
        return httpx.Response(403, json={"message": "Denied"})

    status = NetworkManager(
        w,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        token_provider=lambda: "private-test-token",
    ).tick()
    assert status["pending"] == 3
    assert status["protected_copies"] == 1
    assert len(bodies) == 2 and all(len(body) <= 60000 for body in bodies)
    assert w.store.list("network_submission") == []


def test_sync_over_real_local_http_server(tmp_path):
    from worklife.automatic_network import NetworkManager

    origin, local = Workspace(tmp_path / "origin"), Workspace(tmp_path / "local")
    first, second = publish(origin), publish(origin)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"protocol": 1, "events": [second, first]}).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        manager = NetworkManager(
            local,
            relay_url=f"http://127.0.0.1:{server.server_port}/snapshot.json",
            token_provider=lambda: None,
        )
        assert manager.tick()["status"] == "healthy"
        assert local.ledger.all() == [first, second]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize(
    "claim", ["А" * 11000, "A" * 65350, '"' * 32500], ids=["russian", "near-limit", "escaped"]
)
def test_intake_transports_large_valid_records_without_losing_chain_prefix(tmp_path, claim):
    from worklife.automatic_network import INTAKE_MARKER, NetworkManager
    from worklife.relay_intake import build_snapshot

    w = Workspace(tmp_path)
    first = w.ledger.publish("employer", "acme.example", record(claim))
    second = publish(w)
    issues = []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"protocol": 1, "events": []})
        body = json.loads(request.content)["body"]
        assert len(body) < 60000
        issues.append({"body": body, "user": {"id": 17}})
        return httpx.Response(201, json={"number": len(issues)})

    manager = NetworkManager(
        w, client=httpx.Client(transport=httpx.MockTransport(handler)), token_provider=lambda: "test"
    )
    assert manager.tick()["status"] == "recovering"
    assert build_snapshot({"protocol": 1, "events": []}, issues)["events"] == [first, second]
    packets = [json.loads(issue["body"][len(INTAKE_MARKER) :]) for issue in issues]
    if claim.startswith("А"):
        assert len(packets) == 1 and packets[0]["events"] == [first, second]
    else:
        fragments = [issue for issue, packet in zip(issues, packets) if "fragment" in packet]
        assert len(fragments) > 1
        second_issue = issues[-1]
        partial = build_snapshot({"protocol": 1, "events": []}, [second_issue, *fragments[:-1]])
        assert partial["events"] == []
        assert partial["validation"]["pending"] > 0
    submitted = {eid for item in w.store.list("network_submission") for eid in item["event_ids"]}
    assert submitted == {first["event_id"], second["event_id"]}


def test_partial_fragment_failure_retries_new_group_before_recording_receipt(tmp_path):
    from worklife.automatic_network import INTAKE_MARKER, NetworkManager
    from worklife.relay_intake import build_snapshot

    w = Workspace(tmp_path)
    first = w.ledger.publish("employer", "acme.example", record("A" * 65350))
    second = publish(w)
    issues, attempts = [], []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=build_snapshot({"protocol": 1, "events": []}, issues))
        body = json.loads(request.content)["body"]
        attempts.append(json.loads(body[len(INTAKE_MARKER) :]))
        if len(attempts) == 2:
            return httpx.Response(503)
        issues.append({"body": body, "user": {"id": 17}})
        return httpx.Response(201, json={"number": len(issues)})

    manager = NetworkManager(
        w, client=httpx.Client(transport=httpx.MockTransport(handler)), token_provider=lambda: "test"
    )
    manager.tick()
    assert first["event_id"] not in {
        eid for item in w.store.list("network_submission") for eid in item["event_ids"]
    }
    assert build_snapshot({"protocol": 1, "events": []}, issues)["events"] == []
    manager.tick(force=True)
    groups = {packet["fragment"]["group"] for packet in attempts if "fragment" in packet}
    assert len(groups) == 2
    completed = build_snapshot({"protocol": 1, "events": []}, issues)
    assert completed["events"] == [first, second]
    assert completed["validation"]["pending"] == 0
    assert manager.tick(force=True)["status"] == "healthy"


def test_valid_database_rebuilds_corrupt_archive_before_importing_remote_update(tmp_path):
    from worklife.automatic_network import NetworkManager

    origin, local = Workspace(tmp_path / "origin"), Workspace(tmp_path / "local")
    first = publish(origin)
    local.ledger.import_events([first])
    archive = local.ledger.archive_path / f"{first['event_id']}.json"
    archive.write_bytes(b"broken archive bytes")
    second = publish(origin)
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"protocol": 1, "events": [first, second]})
        )
    )
    status = NetworkManager(local, client=client, token_provider=lambda: None).tick()
    assert status["status"] == "healthy"
    assert local.ledger.all() == [first, second]
    assert json.loads(archive.read_bytes()) == first
    quarantined = list((local.home / "employer_quarantine").glob("*.archive.json"))
    assert len(quarantined) == 1 and quarantined[0].read_bytes() == b"broken archive bytes"


def test_network_tick_reports_sanitized_storage_error_and_retries(tmp_path, monkeypatch):
    from worklife.automatic_network import NetworkManager

    w = Workspace(tmp_path)
    event = publish(w)
    manager = NetworkManager(
        w,
        token_provider=lambda: None,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"protocol": 1, "events": [event]})
            )
        ),
    )
    original = w.ledger._archive_current

    def unavailable():
        raise OSError("private-path-and-token-must-not-leak")

    monkeypatch.setattr(w.ledger, "_archive_current", unavailable)
    status = manager.tick()
    assert status["status"] == "attention"
    assert "private-path-and-token" not in json.dumps(status)
    monkeypatch.setattr(w.ledger, "_archive_current", original)
    assert manager.tick(force=True)["status"] == "healthy"
