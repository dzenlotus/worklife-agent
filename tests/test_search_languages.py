from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from worklife.agency_tools import register_agency_tools
from worklife.config import Config
from worklife.connectors import Connectors
from worklife.market import Market
from worklife.server import create_server
from worklife.workspace import Workspace


def test_profile_keeps_search_and_interface_languages_independent_of_spoken_languages(tmp_path):
    workspace = Workspace(tmp_path)
    profile = workspace.save_profile(
        {
            "facts": [],
            "languages": ["English B2", "Русский — родной"],
            "search_languages": ["RU", "en", "ru", "pt-BR"],
            "interface_language": "EN",
        }
    )
    assert profile["search_languages"] == ["ru", "en", "pt-br"]
    assert profile["interface_language"] == "en"
    assert profile["languages"] == ["English B2", "Русский — родной"]
    assert workspace.get_profile() == profile
    legacy = {"facts": [], "languages": ["English B2"]}
    assert workspace.save_profile(legacy) == legacy


@pytest.mark.parametrize(
    "fields",
    [
        {"search_languages": "en,ru"},
        {"search_languages": ["English B2"]},
        {"search_languages": [None]},
        {"interface_language": 7},
    ],
)
def test_profile_rejects_invalid_language_settings_without_overwriting_profile(tmp_path, fields):
    workspace = Workspace(tmp_path)
    original = workspace.save_profile({"facts": [], "search_languages": ["ru", "en"]})
    with pytest.raises(ValueError, match="language"):
        workspace.save_profile({"facts": [], **fields})
    assert workspace.get_profile() == original


def test_connector_sends_actual_localized_queries_without_guessing_vacancy_language(tmp_path):
    workspace = Workspace(tmp_path)
    connector = Connectors({"hh": {"type": "hh"}}, workspace)
    connector._request = Mock(
        return_value={
            "items": [
                {
                    "id": "1",
                    "name": "Backend engineer / Разработчик",
                    "employer": {"name": "Example"},
                    "alternate_url": "https://example.org/job",
                }
            ]
        }
    )
    for query, language in (("разработчик", "RU"), ("backend engineer", "en")):
        result = connector.search("hh", query, language=language, area="1")
        assert connector._request.call_args.kwargs["params"] == {
            "text": query,
            "per_page": 50,
            "area": "1",
        }
        assert not {"language", "required_languages"} & result[0].keys()
    assert result[0]["search_languages"] == ["ru", "en"]
    assert len(workspace.store.list("job")) == 1
    assert len(workspace.store.list("job_observation")) == 2


def test_market_records_selected_languages_queries_and_incomplete_coverage(tmp_path):
    workspace = Workspace(tmp_path)
    workspace.save_profile({"facts": [], "languages": ["French"], "search_languages": ["ru", "en"]})
    connectors = SimpleNamespace(search=Mock(return_value=[]))
    server = SimpleNamespace(tool=lambda **kwargs: lambda function: function)
    register_agency_tools(server, workspace, connectors)
    result = server.worklife_market_collect(
        "Multilingual", [{"connector": "hh", "query": "разработчик", "language": "RU"}]
    )
    connectors.search.assert_called_once_with("hh", "разработчик", language="ru")
    assert result["snapshot"]["sources"][0]["language"] == "ru"
    assert result["snapshot"]["scope"]["search_languages"] == ["ru", "en"]
    assert result["language_coverage"] == {
        "requested": ["ru", "en"],
        "collected": ["ru"],
        "missing": ["en"],
    }
    assert result["report"]["language_coverage"] == result["language_coverage"]
    assert (
        Market(workspace).report(result["snapshot"]["id"])["language_coverage"] == result["language_coverage"]
    )
    assert result["status"] == "partial"


def test_market_preserves_explicit_scope_and_does_not_infer_search_languages(tmp_path):
    workspace = Workspace(tmp_path)
    workspace.save_profile({"facts": [], "languages": ["French"]})
    connectors = SimpleNamespace(search=Mock(return_value=[]))
    server = SimpleNamespace(tool=lambda **kwargs: lambda function: function)
    register_agency_tools(server, workspace, connectors)
    result = server.worklife_market_collect(
        "Legacy", [{"connector": "hh", "query": "analyst"}], {"role": "Analyst"}
    )
    connectors.search.assert_called_once_with("hh", "analyst")
    assert "search_languages" not in result["snapshot"]["scope"]
    assert result["language_coverage"] == {"requested": [], "collected": [], "missing": []}
    assert result["status"] == "completed"


def test_manual_market_snapshot_canonicalizes_language_metadata_before_storage(tmp_path):
    workspace = Workspace(tmp_path)
    market = Market(workspace)
    scope = {"search_languages": ["EN", "en", "pt-BR"]}
    sources = [{"language": "EN", "status": "collected"}, "legacy browser source"]
    snapshot = market.snapshot("Browser findings", [], scope, sources)
    assert snapshot["scope"]["search_languages"] == ["en", "pt-br"]
    assert snapshot["sources"][0]["language"] == "en"
    assert workspace.store.get("market_snapshot", snapshot["id"])["sources"] == snapshot["sources"]
    assert market.report(snapshot["id"])["language_coverage"] == {
        "requested": ["en", "pt-br"],
        "collected": ["en"],
        "missing": ["pt-br"],
    }
    assert scope == {"search_languages": ["EN", "en", "pt-BR"]}
    assert sources[0]["language"] == "EN"


def test_browser_snapshot_uses_profile_search_languages_unless_scope_explicitly_overrides(tmp_path):
    workspace = Workspace(tmp_path)
    workspace.save_profile({"facts": [], "search_languages": ["ru", "en"]})
    market = Market(workspace)
    sources = [{"language": "en", "status": "collected"}]
    snapshot = market.snapshot("Browser findings", [], sources=sources)
    assert snapshot["scope"]["search_languages"] == ["ru", "en"]
    assert market.report(snapshot["id"])["language_coverage"]["missing"] == ["ru"]
    unrestricted = market.snapshot("Unrestricted browser sample", [], {"search_languages": []}, sources)
    assert unrestricted["scope"]["search_languages"] == []
    assert market.report(unrestricted["id"])["language_coverage"]["missing"] == []


@pytest.mark.parametrize(
    "scope,sources",
    [
        ({"search_languages": "EN"}, []),
        ({"search_languages": ["English B2"]}, []),
        ({}, [{"language": 7, "status": "collected"}]),
        ({}, [{"language": "English B2", "status": "collected"}]),
    ],
)
def test_manual_market_snapshot_rejects_invalid_language_metadata_without_saving(tmp_path, scope, sources):
    workspace = Workspace(tmp_path)
    market = Market(workspace)
    with pytest.raises(ValueError, match="language"):
        market.snapshot("Invalid browser findings", [], scope, sources)
    assert market.snapshots() == []
    assert market.report()["status"] == "empty"


@pytest.mark.asyncio
async def test_mcp_and_scheduled_search_keep_explicit_language(tmp_path):
    server = create_server(Config(tmp_path), profile="recruiter")
    try:
        search = server.worklife_connectors.search = Mock(return_value=[])
        arguments = {"connector": "hh", "query": "analyst", "language": "en", "parameters": {"area": "1"}}
        await server.call_tool("jobs_search", arguments)
        search.assert_called_once_with("hh", "analyst", area="1", language="en")
        search.reset_mock()
        schedule = server.worklife_operations.schedule_save("English search", "jobs_search", arguments)
        run = server.worklife_operations.schedule_run(schedule["id"])
        assert run["status"] == "success"
        search.assert_called_once_with("hh", "analyst", area="1", language="en")
    finally:
        server.worklife_runtime.close()
        server.worklife_browser.close()
