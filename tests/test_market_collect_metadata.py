import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from worklife.agency_tools import register_agency_tools
from worklife.connectors import Connectors
from worklife.workspace import Workspace


def collector(tmp_path):
    workspace = Workspace(tmp_path)
    connectors = SimpleNamespace(search=Mock(return_value=[]))
    server = SimpleNamespace(tool=lambda **kwargs: lambda function: function)
    register_agency_tools(server, workspace, connectors)
    return workspace, connectors, server.worklife_market_collect


def test_collect_metadata_preserves_actual_salary_date_text_and_scope_filters(tmp_path):
    workspace, connectors, collect = collector(tmp_path)
    parameters = {
        "salary": 100000,
        "currency": "RUR",
        "only_with_salary": True,
        "date_from": "2026-10-01",
        "date_to": "2026-10-27",
        "text": "Python backend",
        "scope": {"regions": ["Berlin", "Paris"], "experience": {"minimum_years": 3}},
        "custom_filter": {"include": ["full_time"], "exclude": []},
    }
    scope = {
        "role": "Backend",
        "level": "Senior",
        "region": "Europe",
        "work_format": "remote",
        "collection": {"requested_pages": [1, 2]},
    }
    result = collect("Market", [{"connector": "hh", "query": "Python", "parameters": parameters}], scope)
    source = result["snapshot"]["sources"][0]
    assert source["parameters"] == parameters
    assert result["snapshot"]["scope"] == scope
    connectors.search.assert_called_once_with("hh", "Python", **parameters)
    assert source["parameters_redacted"] is False
    assert workspace.store.get("market_snapshot", result["snapshot"]["id"])["sources"][0] == source


def test_collect_redacts_nested_credentials_only_in_metadata_without_changing_request(tmp_path):
    workspace, connectors, collect = collector(tmp_path)
    parameters = {
        "salary": 100000,
        "token": "top-secret-value",
        "nested": {"Authorization": "Bearer private-value", "date_from": "2026-10-01"},
        "filters": [
            {"api_key": "api-private-value", "skill": "Python"},
            {"client_secret": "nested-private-value"},
        ],
        "credentials": {"username": "private-name", "password": "private-password"},
    }
    original = deepcopy(parameters)
    result = collect("Market", [{"connector": "local", "query": "Python", "parameters": parameters}])
    source = result["snapshot"]["sources"][0]
    assert source["parameters_redacted"] is True
    assert source["parameters"]["salary"] == 100000
    assert source["parameters"]["nested"]["date_from"] == "2026-10-01"
    assert source["parameters"]["filters"][0]["skill"] == "Python"
    assert all(
        secret not in json.dumps(result)
        for secret in (
            "top-secret-value",
            "Bearer private-value",
            "api-private-value",
            "nested-private-value",
            "private-name",
            "private-password",
        )
    )
    assert parameters == original
    connectors.search.assert_called_once_with("local", "Python", **original)
    assert "top-secret-value" not in json.dumps(workspace.store.list("market_snapshot"))


def test_collect_retains_useful_sanitized_failure_message_and_snapshot(tmp_path):
    workspace, connectors, collect = collector(tmp_path)
    connectors.search.side_effect = ValueError("Provider HTTP 429; retry_after=60")
    result = collect("Unavailable", [{"connector": "hh", "parameters": {"only_with_salary": True}}])
    source = result["snapshot"]["sources"][0]
    assert result["status"] == "partial" and source["status"] == "unavailable"
    assert "429" in source["message"] and "60" in source["message"]
    assert result["errors"][0]["message"] == source["message"]
    assert source["parameters"]["only_with_salary"] is True
    assert workspace.store.get("market_snapshot", result["snapshot"]["id"])


@pytest.mark.parametrize("malformed", [{}, {"jobs": [{"id": 2}]}, {"jobs": "unexpected"}])
def test_malformed_source_does_not_abort_other_sources_or_the_sample(tmp_path, malformed):
    workspace = Workspace(tmp_path)
    connectors = Connectors(
        {name: {"type": "greenhouse", "board": name} for name in ("first", "broken", "last")}, workspace
    )
    valid = {"jobs": [{"id": 1, "title": "Analyst", "absolute_url": "https://example.org/job"}]}
    connectors._request = Mock(side_effect=[valid, malformed, valid])
    server = SimpleNamespace(tool=lambda **kwargs: lambda function: function)
    register_agency_tools(server, workspace, connectors)
    result = server.worklife_market_collect(
        "Three sources", [{"connector": name} for name in ("first", "broken", "last")]
    )
    assert result["status"] == "partial"
    assert [source["status"] for source in result["snapshot"]["sources"]] == [
        "collected",
        "unavailable",
        "collected",
    ]
    assert connectors._request.call_count == 3
    assert len(result["snapshot"]["job_ids"]) == 2
    assert result["errors"][0]["connector"] == "broken"
    assert "структур" in result["errors"][0]["message"]
    assert workspace.store.get("market_snapshot", result["snapshot"]["id"])
