"""Read-only inbox ingestion into private conversations; no inferred employer matches."""

import math
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from .storage import now
from .workspace import timestamp

# Known Bot API events without conversation text. Unknown shapes still require review.
TELEGRAM_NONMESSAGE_UPDATES = set(
    "inline_query chosen_inline_result callback_query shipping_query pre_checkout_query purchased_paid_media "
    "poll poll_answer my_chat_member chat_member chat_join_request message_reaction message_reaction_count "
    "chat_boost removed_chat_boost business_connection deleted_business_messages subscription "
    "stopped_message_generation".split()
)
TELEGRAM_NONTEXT_CONTENT = set(
    "animation audio document photo sticker video video_note voice contact dice game poll venue location "
    "new_chat_members left_chat_member new_chat_title new_chat_photo delete_chat_photo group_chat_created "
    "supergroup_chat_created channel_chat_created message_auto_delete_timer_changed migrate_to_chat_id "
    "migrate_from_chat_id pinned_message forum_topic_created forum_topic_edited forum_topic_closed "
    "forum_topic_reopened general_forum_topic_hidden general_forum_topic_unhidden video_chat_scheduled "
    "video_chat_started video_chat_ended video_chat_participants_invited".split()
)


def _identifier(value):
    if type(value) not in (str, int) or not str(value).strip():
        raise ValueError("missing_provider_id")
    return str(value).strip()


def _sender(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return {
            k: value[k]
            for k in ("id", "name", "first_name", "last_name", "username", "participant_type", "is_bot")
            if k in value
        }
    return None


def _time(value, kind, observed):
    try:
        if kind == "telegram" and type(value) in (int, float):
            instant = datetime.fromtimestamp(value, UTC)
        elif kind == "email" and isinstance(value, str):
            instant = parsedate_to_datetime(value)
            if instant.tzinfo is None:
                raise ValueError
        else:
            instant = timestamp(value)
        return instant.astimezone(UTC).isoformat().replace("+00:00", "Z"), "provider"
    except (ValueError, TypeError, AttributeError, OverflowError, OSError):
        return observed, "observed"


def _direction(value):
    # Normalized HTTP may use either spelling; the private Agency vocabulary is inbound/outbound.
    aliases = {
        "incoming": "inbound",
        "outgoing": "outbound",
        "inbound": "inbound",
        "outbound": "outbound",
        "unknown": "unknown",
    }
    if value not in aliases:
        raise ValueError("invalid_direction")
    return aliases[value]


class InboxBridge:
    def __init__(self, workspace, connectors, agency):
        self.workspace, self.connectors, self.agency = workspace, connectors, agency
        self.store = workspace.store

    def _rows(self, kind, data):
        if kind == "telegram":
            return data if isinstance(data, list) else None
        if not isinstance(data, dict):
            return data if kind == "http" and isinstance(data, list) else None
        key = "items" if kind == "hh" else "messages"
        if key in data:
            return data[key] if isinstance(data[key], list) else None
        if kind == "http" and "id" in data and "text" in data:
            return [data]
        return None

    def _normalize(self, kind, row, config, parameters, data, observed):
        if not isinstance(row, dict):
            raise ValueError("unsupported_message_shape")
        source = {"provider": kind, "observed_at": observed}
        reply, direction = "", "unknown"
        if kind == "email":
            provider_id = row.get("message_id")
            folder = data.get("folder", parameters.get("folder", "INBOX"))
            uidvalidity = data.get("uidvalidity")
            uid_scope = f"{folder}:{uidvalidity}" if uidvalidity is not None else folder
            external_id = (
                _identifier(provider_id) if provider_id else f"imap:{uid_scope}:{_identifier(row.get('uid'))}"
            )
            text, date = row.get("body"), row.get("date")
            reply = row.get("in_reply_to") or ""
            direction = "inbound" if str(folder).casefold() == "inbox" else "unknown"
            source.update(
                sender=_sender(row.get("from")),
                folder=folder,
                uid=row.get("uid"),
                uidvalidity=uidvalidity,
                subject=row.get("subject"),
                recipient=row.get("to"),
                references=row.get("references"),
            )
            if not provider_id:
                source["identity_basis"] = (
                    "mailbox_uid" if uidvalidity is not None else "mailbox_uid_without_uidvalidity"
                )
        elif kind == "hh":
            provider_id = _identifier(row.get("id"))
            thread = _identifier(parameters.get("negotiation_id"))
            external_id = f"hh:{thread}:{provider_id}"
            text, date = row.get("text"), row.get("created_at")
            if row.get("in_reply_to"):
                reply = f"hh:{thread}:{_identifier(row['in_reply_to'])}"
            author = row.get("author") if isinstance(row.get("author"), dict) else {}
            own_role, role = config.get("participant_type"), author.get("participant_type")
            if own_role in {"applicant", "employer"} and role in {"applicant", "employer"}:
                direction = "outbound" if own_role == role else "inbound"
            source.update(sender=_sender(author), thread_id=thread)
        elif kind == "telegram":
            if type(row.get("update_id")) is not int or row["update_id"] < 0:
                raise ValueError("invalid_update_id")
            message_key = next(
                (
                    key
                    for key in ("message", "edited_message", "channel_post", "edited_channel_post")
                    if key in row
                ),
                None,
            )
            if message_key is None and TELEGRAM_NONMESSAGE_UPDATES.intersection(row):
                return {"skip_reason": "telegram_nonmessage_update"}
            message = row.get(message_key)
            if not isinstance(message, dict):
                raise ValueError("unsupported_telegram_update")
            provider_id = _identifier(message.get("message_id"))
            chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
            chat_id = _identifier(chat.get("id"))
            if (
                "text" not in message
                and "caption" not in message
                and TELEGRAM_NONTEXT_CONTENT.intersection(message)
            ):
                return {"skip_reason": "telegram_nontext_message"}
            external_id = f"telegram:{chat_id}:{provider_id}"
            parent = message.get("reply_to_message")
            if isinstance(parent, dict) and parent.get("message_id") is not None:
                reply = f"telegram:{chat_id}:{_identifier(parent['message_id'])}"
            sender = message.get("from") if isinstance(message.get("from"), dict) else {}
            own_id = config.get("self_id", config.get("bot_id"))
            if own_id is not None and sender.get("id") is not None:
                direction = "outbound" if str(own_id) == str(sender["id"]) else "inbound"
            text, date = message.get("text", message.get("caption")), message.get("date")
            source.update(sender=_sender(sender), chat_id=chat_id, update_id=row["update_id"])
        else:
            provider_id = _identifier(row.get("id"))
            external_id = provider_id
            text = row.get("text")
            date = row.get("occurred_at", row.get("created_at", row.get("date")))
            reply = row.get("in_reply_to") or ""
            direction = _direction(row.get("direction", "unknown"))
            source.update(sender=_sender(row.get("from")))
        if not isinstance(text, str) or not text.strip():
            raise ValueError("missing_message_text")
        if len(text) > 100000:
            raise ValueError("message_text_too_long")
        if not isinstance(reply, str):
            raise ValueError("invalid_reply_reference")
        occurred_at, basis = _time(date, kind, observed)
        source.update(
            provider_id=provider_id,
            provider_timestamp=date
            if type(date) in (str, int) or type(date) is float and math.isfinite(date)
            else None,
            timestamp_basis=basis,
        )
        if basis == "observed":
            source["timestamp_issue"] = "missing_timestamp" if date is None else "invalid_timestamp"
        return {
            "external_id": external_id,
            "text": text,
            "in_reply_to": reply.strip(),
            "direction": direction,
            "occurred_at": occurred_at,
            "source": source,
        }

    def _receipt_id(self, kind, action):
        result, payload = action.get("result"), action.get("payload", {})
        if not isinstance(result, dict):
            return None
        if kind == "telegram":
            chat = result.get("chat") if isinstance(result.get("chat"), dict) else {}
            chat_id, message_id = chat.get("id", payload.get("chat_id")), result.get("message_id")
            return (
                f"telegram:{chat_id}:{message_id}" if chat_id is not None and message_id is not None else None
            )
        if kind == "hh":
            if (
                action.get("operation") != "reply"
                or not result.get("id")
                or not payload.get("negotiation_id")
            ):
                return None
            return f"hh:{payload['negotiation_id']}:{result['id']}"
        value = result.get("message_id") if kind == "email" else result.get("message_id", result.get("id"))
        return str(value).strip() if type(value) in (str, int) and str(value).strip() else None

    def _link(self, connector, kind, reply, job_id):
        if job_id:
            return job_id, "explicit_job"
        if not reply:
            return None, "unassigned"
        jobs = {
            m.get("job_id")
            for m in self.store.list("message")
            if m.get("channel", "").lower() == connector.lower()
            and m.get("external_id") == reply
            and m.get("job_id")
        }
        for action in self.workspace.actions():
            if (
                action.get("status") == "sent"
                and action.get("connector", "").lower() == connector.lower()
                and self._receipt_id(kind, action) == reply
                and action.get("payload", {}).get("_job_id")
            ):
                jobs.add(action["payload"]["_job_id"])
        if len(jobs) == 1:
            resolved = next(iter(jobs))
            try:
                self.store.get("job", resolved)
            except ValueError:
                return None, "missing_linked_job"
            return resolved, "exact_reply"
        return None, "ambiguous_reply" if jobs else "unassigned"

    def sync(self, connector, operation="inbox", parameters=None, job_id=None, limit=50):
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        if not isinstance(connector, str) or not connector.strip():
            raise ValueError("A configured connector name is required")
        if parameters is not None and not isinstance(parameters, dict):
            raise ValueError("parameters must be an object")
        parameters = dict(parameters or {})
        if job_id:
            self.store.get("job", job_id)
        config = self.connectors.config(connector)
        kind = config.get("type")
        operations = {"email": {"inbox", "message"}, "hh": {"messages"}, "telegram": {"updates"}}
        if kind != "http" and operation not in operations.get(kind, set()):
            raise ValueError(
                "Inbox supports email inbox/message, HH messages, Telegram updates, and normalized HTTP read operations"
            )
        if kind == "email" and operation == "inbox":
            provider_limit = parameters.get("limit", limit)
            if type(provider_limit) is not int or provider_limit < 1:
                raise ValueError("Mail limit must be a positive integer")
            parameters["limit"] = min(limit, provider_limit, 100)
            parameters.setdefault("after_uid", 0)
        try:
            data = self.connectors.read(connector, operation, parameters)
        except Exception as exc:
            raise ValueError(
                f"Inbox read failed ({type(exc).__name__}); check the connector configuration and provider access"
            ) from None
        result = {
            "status": "empty",
            "imported": 0,
            "duplicates": 0,
            "skipped": 0,
            "skipped_events": [],
            "unassigned": 0,
            "messages": [],
            "errors": [],
            "next_parameters": dict(parameters),
        }
        rows = self._rows(kind, data)
        if rows is None:
            return {
                **result,
                "status": "unsupported_data",
                "errors": [{"code": "unsupported_response_shape"}],
            }
        if kind == "email":
            result["errors"].extend(data.get("errors") or [])
            result["cursor_reset"] = data.get("cursor_reset", False)
        observed = now()
        known = {(m.get("channel", "").lower(), m.get("external_id")) for m in self.store.list("message")}
        complete = not result["errors"]
        for index, row in enumerate(rows):
            try:
                normalized = self._normalize(kind, row, config, parameters, data, observed)
            except (ValueError, TypeError, AttributeError) as exc:
                code = str(exc) if isinstance(exc, ValueError) else "unsupported_message_shape"
                result["errors"].append({"index": index, "code": code})
                complete = False
                continue
            if "skip_reason" in normalized:
                result["skipped"] += 1
                result["skipped_events"].append(
                    {"index": index, "update_id": row["update_id"], "code": normalized["skip_reason"]}
                )
                continue
            key = connector.lower(), normalized["external_id"]
            if key in known:
                result["duplicates"] += 1
                continue
            if result["imported"] >= limit:
                complete = False
                break
            linked_job, basis = self._link(connector, kind, normalized["in_reply_to"], job_id)
            source = {
                **normalized.pop("source"),
                "connector": connector,
                "operation": operation,
                "link_basis": basis,
            }
            reply = normalized["in_reply_to"]
            # An unresolved/ambiguous reply must not trigger the Agency's automatic parent association.
            normalized["in_reply_to"] = reply if linked_job else ""
            try:
                record = self.agency.conversation_record(
                    job_id=linked_job, channel=connector, status="observed", **normalized
                )
            except ValueError:
                result["errors"].append({"index": index, "code": "message_record_rejected"})
                complete = False
                continue
            record = {**record, "in_reply_to": reply, "source": source}
            self.store.put("message", record["id"], record)
            result["messages"].append(record)
            result["imported"] += 1
            result["unassigned"] += int(record.get("job_id") is None)
            known.add(key)
        if complete:
            if kind == "email" and operation == "inbox":
                result["next_parameters"]["after_uid"] = data.get(
                    "next_after_uid",
                    max(
                        (int(row["uid"]) for row in rows if str(row.get("uid", "")).isdigit()),
                        default=parameters["after_uid"],
                    ),
                )
                if data.get("uidvalidity") is not None:
                    result["next_parameters"]["uidvalidity"] = data["uidvalidity"]
            elif kind == "telegram" and rows:
                result["next_parameters"]["offset"] = max(int(row["update_id"]) for row in rows) + 1
            elif (
                kind == "hh"
                and type(data.get("page")) is int
                and type(data.get("pages")) is int
                and data["page"] + 1 < data["pages"]
            ):
                result["next_parameters"]["page"] = data["page"] + 1
            elif kind == "http" and isinstance(data, dict) and data.get("next_cursor") is not None:
                result["next_parameters"]["cursor"] = data["next_cursor"]
        if result["errors"]:
            result["status"] = "partial" if result["imported"] or result["duplicates"] else "unsupported_data"
        elif rows:
            result["status"] = "ready"
        return result
