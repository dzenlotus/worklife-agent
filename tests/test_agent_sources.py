import json

from worklife.workspace import Workspace


def test_agent_discovers_and_updates_sources_without_manual_records(tmp_path):
    w = Workspace(tmp_path)
    first = w.record_source("Career site", "https://user:secret@jobs.example/search?q=private", "browser")
    again = w.record_source("Career site updated", "https://jobs.example/other", "api")
    assert first["id"] == again["id"]
    assert len(w.store.list("platform")) == len(w.store.list("resource")) == 1
    assert set(again["capabilities"]) == {"browser", "api"}
    assert again["url"] == "https://jobs.example"
    assert "secret" not in json.dumps(w.store.list("platform"))
    assert "private" not in json.dumps(w.store.list("resource"))
    assert w.ledger.export() == []


def test_local_file_inspection_is_not_a_public_platform(tmp_path):
    w = Workspace(tmp_path)
    assert w.record_source("Local CV", "file:///private/cv.html", "browser") is None
    assert w.store.list("platform") == []
