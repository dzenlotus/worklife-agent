"""Read-only provider messages become private records without guessed associations."""

import copy
import importlib.util

import pytest

from worklife.storage import now
from worklife.workspace import Workspace, uid


class FakeConnectors:
    def __init__(self, kind, result, **config):
        self.value = result
        self.settings = {"type": kind, **config}
        self.calls = []

    def config(self, name):
        return self.settings

    def read(self, name, operation, parameters):
        self.calls.append((name, operation, copy.deepcopy(parameters)))
        if isinstance(self.value, Exception):
            raise self.value
        return copy.deepcopy(self.value)


class RecordingAgency:
    def __init__(self, workspace):
        self.workspace = workspace

    def conversation_record(self, **fields):
        record = {"id": uid(), "created_at": now(), **fields}
        return self.workspace.store.put("message", record["id"], record)


def setup(tmp_path, kind, result, **config):
    assert importlib.util.find_spec("worklife.inbox"), "Inbox bridge is not implemented"
    from worklife.inbox import InboxBridge

    w = Workspace(tmp_path)
    connector = FakeConnectors(kind, result, **config)
    return w, connector, InboxBridge(w, connector, RecordingAgency(w))


def job(w, name="one"):
    return w.save_job(
        {
            "id": name,
            "platform": "manual",
            "title": "Engineer",
            "employer": "Acme",
            "url": f"https://acme.example/{name}",
        }
    )["id"]


def email(identifier="<in@example.org>", **changes):
    return {
        "uid": "10",
        "message_id": identifier,
        "from": "HR <hr@example.org>",
        "to": "alex@example.org",
        "subject": "Regarding your application",
        "date": "Tue, 27 Oct 2026 13:00:00 +0300",
        "body": "Can we arrange a call?",
        "attachments": [],
        **changes,
    }


def test_email_first_and_repeated_sync_are_private_and_idempotent(tmp_path):
    w, connectors, bridge = setup(tmp_path, "email", {"folder": "INBOX", "messages": [email()]})
    result = bridge.sync("mail")
    assert result["status"] == "ready"
    assert (result["imported"], result["duplicates"], result["unassigned"]) == (1, 0, 1)
    message = result["messages"][0]
    assert message["direction"] == "inbound" and message["job_id"] is None
    assert message["occurred_at"] == "2026-10-27T10:00:00Z"
    assert message["source"]["timestamp_basis"] == "provider"
    assert message["source"]["sender"] == "HR <hr@example.org>"
    assert bridge.sync("mail")["duplicates"] == 1
    assert len(w.store.list("message")) == 1
    assert w.ledger.export() == []
    assert all(call[1] == "inbox" for call in connectors.calls)


def test_exact_email_reply_links_to_sent_action_receipt_not_subject(tmp_path):
    w, _, bridge = setup(
        tmp_path, "email", {"folder": "INBOX", "messages": [email(in_reply_to="<out@example.org>")]}
    )
    job_id = job(w)
    draft = w.draft_action("mail", "send", {"_job_id": job_id, "body": "Hello"}, "out")
    w.approve_action(draft["id"])
    w.execute_action(
        draft["id"],
        lambda *args: {
            "message_id": "<out@example.org>",
            "delivery": "accepted_by_smtp_not_proof_of_receipt",
        },
    )
    result = bridge.sync("mail")
    assert result["messages"][0]["job_id"] == job_id
    assert result["messages"][0]["source"]["link_basis"] == "exact_reply"
    assert result["unassigned"] == 0


def test_known_message_reply_links_but_ambiguous_links_remain_unassigned(tmp_path):
    w, connector, bridge = setup(
        tmp_path,
        "http",
        {"messages": [{"id": "reply", "text": "Reply", "in_reply_to": "sent", "direction": "inbound"}]},
    )
    agency = RecordingAgency(w)
    first = job(w)
    agency.conversation_record(
        job_id=first, direction="outbound", channel="chat", text="Hello", external_id="sent"
    )
    assert bridge.sync("chat")["messages"][0]["job_id"] == first
    agency.conversation_record(
        job_id=job(w, "other"), direction="outbound", channel="chat", text="Hello", external_id="sent"
    )
    connector.value["messages"][0]["id"] = "ambiguous"
    result = bridge.sync("chat")
    assert result["messages"][0]["job_id"] is None
    assert result["messages"][0]["source"]["link_basis"] == "ambiguous_reply"


def test_subject_and_empty_success_receipt_do_not_link_jobs(tmp_path):
    w, _, bridge = setup(tmp_path, "email", {"folder": "INBOX", "messages": [email(in_reply_to="unproven")]})
    draft = w.draft_action(
        "mail",
        "send",
        {"_job_id": job(w), "subject": "Regarding your application", "body": "Hello"},
        "no-receipt",
    )
    w.approve_action(draft["id"])
    w.execute_action(draft["id"], lambda *args: {})
    result = bridge.sync("mail")
    assert result["messages"][0]["job_id"] is None
    assert w.store.list("application") == []


def test_hh_legacy_shape_keeps_unknown_direction_without_account_role(tmp_path):
    data = {
        "items": [
            {
                "id": "123",
                "created_at": "2013-10-07T18:30:57+0400",
                "text": "Invitation",
                "author": {"participant_type": "employer"},
            }
        ],
        "page": 0,
        "pages": 2,
        "per_page": 20,
    }
    w, _, bridge = setup(tmp_path, "hh", data)
    j = job(w)
    result = bridge.sync("hh", "messages", {"negotiation_id": "n1"}, job_id=j)
    message = result["messages"][0]
    assert message["direction"] == "unknown"
    assert message["job_id"] == j
    assert message["occurred_at"] == "2013-10-07T14:30:57Z"
    assert result["next_parameters"]["page"] == 1
    assert result["next_parameters"]["negotiation_id"] == "n1"
    assert w.store.list("application") == []


def test_telegram_adapter_result_scopes_message_ids_to_chat_and_preserves_reply(tmp_path):
    updates = [
        {
            "update_id": 20,
            "message": {
                "message_id": 7,
                "chat": {"id": 100},
                "from": {"id": 12},
                "date": 1793100000,
                "text": "Response",
                "reply_to_message": {"message_id": 6},
            },
        },
        {
            "update_id": 21,
            "message": {"message_id": 7, "chat": {"id": 200}, "date": 1793100000, "text": "Other chat"},
        },
    ]
    w, _, bridge = setup(tmp_path, "telegram", updates)
    j = job(w)
    draft = w.draft_action("tg", "send", {"_job_id": j, "chat_id": 100, "text": "Hello"}, "telegram-out")
    w.approve_action(draft["id"])
    w.execute_action(draft["id"], lambda *args: {"message_id": 6, "chat": {"id": 100}, "text": "Hello"})
    result = bridge.sync("tg", "updates")
    assert result["imported"] == 2
    one, two = result["messages"]
    assert one["external_id"] != two["external_id"]
    assert one["job_id"] == j and two["job_id"] is None
    assert one["direction"] == "unknown"
    assert result["next_parameters"]["offset"] == 22
    assert bridge.sync("tg", "updates")["duplicates"] == 2


def test_duplicate_messages_do_not_consume_import_limit_or_skip_new_messages(tmp_path):
    data = {"messages": [{"id": "old", "text": "Old"}]}
    w, connector, bridge = setup(tmp_path, "http", data)
    bridge.sync("api", limit=1)
    connector.value["messages"] += [{"id": "new", "text": "New"}, {"id": "later", "text": "Later"}]
    connector.value["next_cursor"] = "next-page"
    result = bridge.sync("api", parameters={"cursor": "current"}, limit=1)
    assert result["imported"] == 1 and result["duplicates"] == 1
    assert result["messages"][0]["text"] == "New"
    assert result["next_parameters"].get("cursor") == "current"
    result = bridge.sync("api", parameters={"cursor": "current"}, limit=1)
    assert result["imported"] == 1 and result["duplicates"] == 2
    assert result["messages"][0]["text"] == "Later"
    assert result["next_parameters"]["cursor"] == "next-page"
    assert len(w.store.list("message")) == 3


def test_invalid_date_is_observed_time_and_bad_elements_return_safe_codes(tmp_path):
    data = {
        "messages": [
            {"id": "a", "text": "Hello", "occurred_at": "not-a-date"},
            {"id": "bad", "token": "provider-secret"},
        ],
        "next_cursor": "after-page",
    }
    w, _, bridge = setup(tmp_path, "http", data)
    result = bridge.sync("api")
    assert result["imported"] == 1
    message = result["messages"][0]
    assert message["source"]["timestamp_basis"] == "observed"
    assert message["source"]["provider_timestamp"] == "not-a-date"
    assert result["errors"] and "provider-secret" not in str(result["errors"])
    assert not result["next_parameters"].get("cursor")
    assert len(w.store.list("message")) == 1


@pytest.mark.parametrize("data", [{"access_token": "secret", "status": "ok"}, [42], {"messages": "hello"}])
def test_unsupported_response_does_not_fabricate_messages(tmp_path, data):
    w, _, bridge = setup(tmp_path, "http", data)
    result = bridge.sync("api")
    assert result["status"] == "unsupported_data"
    assert result["imported"] == 0 and result["errors"]
    assert w.store.list("message") == []
    assert "secret" not in str(result)


def test_read_failure_has_clear_nonsecret_error_and_writes_nothing(tmp_path):
    w, _, bridge = setup(tmp_path, "http", ConnectionError("https://user:secret@host/path"))
    with pytest.raises(ValueError, match="read failed") as caught:
        bridge.sync("api")
    assert "secret" not in str(caught.value)
    assert w.store.list("message") == []


def test_invalid_telegram_update_id_is_a_safe_element_error(tmp_path):
    updates = [
        {"update_id": "not-an-offset", "message": {"message_id": 1, "chat": {"id": 100}, "text": "Hello"}}
    ]
    w, _, bridge = setup(tmp_path, "telegram", updates)
    result = bridge.sync("tg", "updates")
    assert result["status"] == "unsupported_data"
    assert result["errors"] == [{"index": 0, "code": "invalid_update_id"}]
    assert w.store.list("message") == []


def test_telegram_nontext_events_advance_cursor_and_do_not_block_later_messages(tmp_path):
    from worklife.operations import Operations

    updates = [
        {"update_id": 10, "my_chat_member": {"chat": {"id": 100}}},
        {"update_id": 11, "callback_query": {"id": "callback"}},
        {"update_id": 12, "message": {"message_id": 1, "chat": {"id": 100}, "photo": [{"file_id": "p"}]}},
        {"update_id": 13, "message": {"message_id": 2, "chat": {"id": 100}, "new_chat_members": [{"id": 5}]}},
    ]
    w, connector, bridge = setup(tmp_path, "telegram", updates)
    operations = Operations(w, lambda tool, arguments: bridge.sync(**arguments))
    schedule = operations.schedule_save(
        "Inbox", "inbox_sync", {"connector": "tg", "operation": "updates", "parameters": {"offset": 10}}
    )
    run = operations.schedule_run(schedule["id"])
    result = run["result"]
    assert result["status"] == "ready" and result["errors"] == []
    assert result["skipped"] == 4 and len(result["skipped_events"]) == 4
    assert result["imported"] == 0 and not run["changed"]
    assert w.store.list("message") == []
    saved = w.store.get("schedule", schedule["id"])
    assert saved["arguments"]["parameters"]["offset"] == 14
    connector.value = [
        {"update_id": 14, "message": {"message_id": 3, "chat": {"id": 100}, "text": "Invitation"}}
    ]
    later = operations.schedule_run(schedule["id"])
    assert later["result"]["imported"] == 1 and later["changed"]
    assert connector.calls[-1][2]["offset"] == 14


@pytest.mark.parametrize(
    "payload",
    [
        {"message": {"message_id": 1, "chat": {"id": 100}, "text": 12}},
        {"message": {"message_id": 1, "chat": {"id": 100}, "text": "", "photo": [{"file_id": "p"}]}},
        {"message": {"message_id": 1, "chat": {"id": 100}, "photo": [{"file_id": "p"}], "caption": 12}},
        {"message": {"message_id": 1, "chat": {"id": 100}}},
        {"not_a_known_update": {}},
    ],
)
def test_malformed_telegram_text_or_unknown_event_still_blocks_cursor(tmp_path, payload):
    w, _, bridge = setup(tmp_path, "telegram", [{"update_id": 10, **payload}])
    result = bridge.sync("tg", "updates", {"offset": 10})
    assert result["errors"] and result["next_parameters"]["offset"] == 10
    assert result["skipped"] == 0
    assert w.store.list("message") == []


def test_nonfinite_provider_date_uses_observation_time_without_invalid_json(tmp_path):
    w, _, bridge = setup(tmp_path, "http", [{"id": "one", "text": "Hello", "date": float("inf")}])
    result = bridge.sync("api")
    assert result["imported"] == 1
    assert result["messages"][0]["source"]["timestamp_basis"] == "observed"
    assert result["messages"][0]["source"]["timestamp_issue"] == "invalid_timestamp"
    assert len(w.store.list("message")) == 1


def test_non_inbox_mail_folder_does_not_assert_inbound_direction(tmp_path):
    _, _, bridge = setup(tmp_path, "email", {"folder": "Sent", "messages": [email()]})
    assert bridge.sync("mail", parameters={"folder": "Sent"})["messages"][0]["direction"] == "unknown"


def test_real_agency_unknown_direction_keeps_pipeline_then_exact_inbound_advances_once(tmp_path):
    from worklife.agency import Agency
    from worklife.inbox import InboxBridge

    w = Workspace(tmp_path)
    agency = Agency(w)
    job_id = job(w)
    application = agency.pipeline_update(job_id, "applied")
    connector = FakeConnectors("http", [{"id": "unknown", "text": "Unknown direction"}])
    bridge = InboxBridge(w, connector, agency)
    unknown = bridge.sync("api", job_id=job_id)
    assert unknown["messages"][0]["direction"] == "unknown"
    assert w.store.get("application", application["id"])["stage"] == "applied"
    connector.value = [
        {"id": "reply", "text": "Real response", "direction": "inbound", "in_reply_to": "unknown"}
    ]
    bridge.sync("api")
    assert w.store.get("application", application["id"])["stage"] == "reply"
    before = w.store.get("application", application["id"])
    assert bridge.sync("api")["duplicates"] == 1
    assert w.store.get("application", application["id"]) == before
    assert w.ledger.export() == []


class Mailbox:
    """IMAP transport double; MIME decoding still runs through the real connector."""

    def __init__(self, count=1, uidvalidity="100"):
        self.raw = {i: self.mime(i) for i in range(1, count + 1)}
        self.uidvalidity = uidvalidity
        self.failed_uids = set()
        self.commands = []
        self.selections = []

    @staticmethod
    def mime(identifier, message_id=True, reply=None, text=None):
        from email.message import EmailMessage

        message = EmailMessage()
        message["From"] = "HR <hr@example.org>"
        message["To"] = "alex@example.org"
        message["Subject"] = "Application"
        message["Date"] = "Tue, 27 Oct 2026 13:00:00 +0300"
        if message_id:
            message["Message-ID"] = f"<mail-{identifier}@example.org>"
        if reply:
            message["In-Reply-To"] = reply
            message["References"] = reply
        message.set_content(text or f"Message {identifier}")
        return message.as_bytes()

    def connect(self, *args, **kwargs):
        mailbox = self

        class Session:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def login(self, *args):
                pass

            def select(self, folder, readonly=False):
                mailbox.selections.append((folder, readonly))
                return "OK", []

            def uid(self, command, *args):
                mailbox.commands.append((command, args))
                if command == "search":
                    # Returning all IDs also checks local filtering of IMAP reversed UID ranges.
                    return "OK", [b" ".join(str(i).encode() for i in sorted(mailbox.raw))]
                assert command == "fetch" and args[1] == "(BODY.PEEK[])"
                identifier = int(args[0])
                if identifier in mailbox.failed_uids:
                    return "NO", []
                return "OK", [(str(identifier).encode(), mailbox.raw[identifier])]

        if self.uidvalidity is not None:
            Session.response = lambda self, name: (name, [mailbox.uidvalidity.encode()])
        return Session()


def real_mailbox(tmp_path, monkeypatch, mailbox):
    from worklife.agency import Agency
    from worklife.connectors import Connectors
    from worklife.inbox import InboxBridge

    monkeypatch.setattr("imaplib.IMAP4_SSL", mailbox.connect)
    monkeypatch.setenv("TEST_INBOX_USER", "fixture")
    monkeypatch.setenv("TEST_INBOX_PASS", "fixture")
    w = Workspace(tmp_path)
    connectors = Connectors(
        {
            "mail": {
                "type": "email",
                "imap_host": "fixture",
                "username_env": "TEST_INBOX_USER",
                "password_env": "TEST_INBOX_PASS",
            }
        },
        w,
    )
    return w, connectors, InboxBridge(w, connectors, Agency(w))


def test_real_mime_headers_are_plain_strings_and_reply_links(tmp_path, monkeypatch):
    mailbox = Mailbox()
    mailbox.raw[1] = mailbox.mime(1, reply="<out@example.org>")
    w, connectors, bridge = real_mailbox(tmp_path, monkeypatch, mailbox)
    row = connectors.read("mail", "inbox", {})["messages"][0]
    assert all(type(row[key]) is str for key in ("message_id", "in_reply_to", "references", "date"))
    j = job(w)
    action = w.draft_action("mail", "send", {"_job_id": j, "body": "Hello"}, "outgoing")
    w.approve_action(action["id"])
    w.execute_action(action["id"], lambda *args: {"message_id": "<out@example.org>"})
    result = bridge.sync("mail")
    assert result["imported"] == 1
    assert result["messages"][0]["job_id"] == j
    assert result["messages"][0]["source"]["provider_timestamp"] == row["date"]
    assert w.ledger.export() == []


def test_imap_cursor_reads_all_pages_then_only_new_uids(tmp_path, monkeypatch):
    mailbox = Mailbox(21)
    w, _, bridge = real_mailbox(tmp_path, monkeypatch, mailbox)
    first = bridge.sync("mail", limit=20)
    assert first["imported"] == 20
    assert [m["source"]["uid"] for m in first["messages"]] == [str(i) for i in range(1, 21)]
    assert first["next_parameters"] == {"limit": 20, "after_uid": 20, "uidvalidity": "100"}
    second = bridge.sync("mail", parameters=first["next_parameters"], limit=20)
    assert second["imported"] == 1 and second["duplicates"] == 0
    assert second["next_parameters"]["after_uid"] == 21
    empty = bridge.sync("mail", parameters=second["next_parameters"], limit=20)
    assert empty["status"] == "empty" and empty["duplicates"] == 0
    mailbox.raw[22] = mailbox.mime(22)
    new = bridge.sync("mail", parameters=empty["next_parameters"], limit=20)
    assert new["imported"] == 1 and new["messages"][0]["source"]["uid"] == "22"
    assert len(w.store.list("message")) == 22
    assert all(readonly for _, readonly in mailbox.selections)
    assert set(command for command, _ in mailbox.commands) == {"search", "fetch"}


def test_imap_bridge_forwards_effective_limit_without_changing_caller_parameters(tmp_path, monkeypatch):
    mailbox = Mailbox(21)
    _, _, bridge = real_mailbox(tmp_path, monkeypatch, mailbox)
    parameters = {"after_uid": 0, "limit": 15, "criteria": "UNSEEN"}
    result = bridge.sync("mail", parameters=parameters, limit=10)
    assert result["imported"] == 10
    assert len([command for command, _ in mailbox.commands if command == "fetch"]) == 10
    assert result["next_parameters"]["limit"] == 10
    assert parameters == {"after_uid": 0, "limit": 15, "criteria": "UNSEEN"}


def test_imap_fetch_failure_does_not_advance_cursor_or_lose_message(tmp_path, monkeypatch):
    mailbox = Mailbox(3)
    mailbox.failed_uids.add(2)
    w, _, bridge = real_mailbox(tmp_path, monkeypatch, mailbox)
    failed = bridge.sync("mail", parameters={"after_uid": 0}, limit=3)
    assert failed["status"] == "partial" and failed["imported"] == 2
    assert failed["errors"] == [{"uid": "2", "code": "imap_fetch_failed"}]
    assert failed["next_parameters"]["after_uid"] == 0
    mailbox.failed_uids.clear()
    recovered = bridge.sync("mail", parameters=failed["next_parameters"], limit=3)
    assert recovered["imported"] == 1 and recovered["duplicates"] == 2
    assert recovered["next_parameters"]["after_uid"] == 3
    assert len(w.store.list("message")) == 3


def test_imap_uidvalidity_change_resets_cursor_and_namespaces_uid_fallback(tmp_path, monkeypatch):
    mailbox = Mailbox()
    mailbox.raw[1] = mailbox.mime(1, message_id=False)
    w, _, bridge = real_mailbox(tmp_path, monkeypatch, mailbox)
    first = bridge.sync("mail")
    mailbox.uidvalidity = "200"
    mailbox.raw[1] = mailbox.mime(1, message_id=False, text="New mailbox identity")
    reset = bridge.sync("mail", parameters=first["next_parameters"])
    assert reset["cursor_reset"] is True
    assert reset["imported"] == 1
    assert reset["next_parameters"]["uidvalidity"] == "200"
    assert reset["next_parameters"]["after_uid"] == 1
    assert reset["messages"][0]["external_id"] != first["messages"][0]["external_id"]
    assert reset["messages"][0]["source"]["uidvalidity"] == "200"
    assert len(w.store.list("message")) == 2


def test_imap_cursor_works_when_transport_has_no_uidvalidity_response(tmp_path, monkeypatch):
    mailbox = Mailbox(uidvalidity=None)
    _, _, bridge = real_mailbox(tmp_path, monkeypatch, mailbox)
    result = bridge.sync("mail")
    assert result["imported"] == 1
    assert result["next_parameters"]["after_uid"] == 1
    assert "uidvalidity" not in result["next_parameters"]


def test_legacy_imap_read_without_cursor_keeps_latest_selection_and_nullable_headers(tmp_path, monkeypatch):
    mailbox = Mailbox(21)
    _, connectors, _ = real_mailbox(tmp_path, monkeypatch, mailbox)
    response = connectors.read("mail", "inbox", {"limit": 2})
    assert [row["uid"] for row in response["messages"]] == ["20", "21"]
    assert all(row["in_reply_to"] is None and row["references"] is None for row in response["messages"])


@pytest.mark.parametrize("failure", ["empty_text", "unknown_charset"])
def test_imap_parse_failure_keeps_cursor_until_repaired(tmp_path, monkeypatch, failure):
    mailbox = Mailbox(3)
    valid = mailbox.raw[2]
    mailbox.raw[2] = (
        valid.replace(b"Message 2", b"")
        if failure == "empty_text"
        else valid.replace(b'charset="utf-8"', b'charset="not-a-real-charset"')
    )
    w, _, bridge = real_mailbox(tmp_path, monkeypatch, mailbox)
    partial = bridge.sync("mail", parameters={"after_uid": 0}, limit=3)
    assert partial["status"] == "partial" and partial["imported"] == 2
    assert partial["errors"]
    assert partial["next_parameters"]["after_uid"] == 0
    mailbox.raw[2] = valid
    fixed = bridge.sync("mail", parameters=partial["next_parameters"], limit=3)
    assert fixed["imported"] == 1 and fixed["duplicates"] == 2
    assert fixed["next_parameters"]["after_uid"] == 3
    assert len(w.store.list("message")) == 3


def test_imap_uidvalidity_reset_on_empty_mailbox_returns_reset_cursor(tmp_path, monkeypatch):
    mailbox = Mailbox(0, uidvalidity="200")
    _, _, bridge = real_mailbox(tmp_path, monkeypatch, mailbox)
    result = bridge.sync("mail", parameters={"after_uid": 50, "uidvalidity": "100"})
    assert result["status"] == "empty" and result["cursor_reset"] is True
    assert result["next_parameters"]["after_uid"] == 0
    assert result["next_parameters"]["uidvalidity"] == "200"
