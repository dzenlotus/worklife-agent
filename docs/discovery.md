# Finding and listing Worklife

Worklife is an MCP server for AI job search: vacancy research, resume and CV matching,
application tracking, salary analysis, interviews, offers, and shared employer knowledge.
Use the [README](../README.md) for setup and [client support](recruiter-agent.md) for adapter limits.

## Discovery surfaces

| Surface | What makes Worklife discoverable | Status on 2026-10-28 |
|---|---|---|
| GitHub | Repository description, topics, English README, project website | Description and 20 topics applied; English setup instructions and website metadata included in the repository |
| PyPI | Package summary, README, keyword tags, Trove classifiers, project links | Release 0.5.1 includes keyword tags, classifiers, project links and the MCP ownership marker |
| Official MCP Registry | Namespace, capability description, repository and setup URL in `server.json` | Manifest version: `io.github.dzenlotus/worklife-agent` 0.5.1; publication state is available from the public registry API |

The [public registry API](https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.dzenlotus%2Fworklife-agent)
reports published versions with their status and `isLatest` flag. Version 0.4.1 was first
verified active at `2026-10-28T05:54:38.461542Z`; the current manifest targets 0.5.1.
The 0.5.1 distributions include the new metadata. Registry publication does not establish
search ranking or visibility and installation support in every downstream client directory.

## GitHub description and topics

Applied repository description:

> MCP server for AI job search, resume matching, application tracking, and shared employer knowledge.

Applied topics (20, within GitHub's limit):

```text
mcp model-context-protocol mcp-server ai-agent job-search career-assistant
recruitment resume cv application-tracking salary-analysis employer-research
local-first python claude-code cursor codex opencode browser-automation career
```

GitHub topics are repository metadata, set in the repository's **About** settings.
Putting the same words in a file does not apply topics to GitHub.
The client topics refer to provided setup adapters; see the support limits above.

## Official MCP Registry

The root [server.json](../server.json) uses the documented **custom installation path**:
it links to setup instructions and intentionally declares neither an executable package
nor a public remote endpoint. This is a discovery entry, not a one-click installation recipe.
On 2026-10-28 it passed the official JSON schema and `mcp-publisher` v1.8.6's `validate`
command, then was published and verified through the public registry API.
The real career MCP command is:

```sh
uvx --python 3.12 --from worklife-agent==0.5.1 worklife-recruiter mcp
```

The package-named command `worklife-agent` is an installer. Advertising
`uvx worklife-agent mcp` as the server command would be incorrect.
Browser automation needs the browser extra and a Chromium installation; the README's
setup command prepares both in a persistent runtime.

For a later server version, update the version in `server.json`, verify the linked setup
documentation, and publish as the namespace owner:

```sh
brew install mcp-publisher
mcp-publisher validate
mcp-publisher login github
mcp-publisher publish
```

Run these commands from the repository root. GitHub authentication must prove control of
`dzenlotus` for the `io.github.dzenlotus/` namespace. Registry acceptance is established only
by a successful publish and a matching entry in the registry API. A valid JSON schema alone
does not prove acceptance by the live service or visibility in downstream client directories.
The official publisher also supports `MCP_GITHUB_TOKEN` for noninteractive GitHub
authentication; pass credentials through the environment without printing them.

Check the result without authentication:

```sh
curl --fail --get 'https://registry.modelcontextprotocol.io/v0.1/servers' \
  --data-urlencode 'search=io.github.dzenlotus/worklife-agent'
```

For a future **PyPI package entry**, use a published distribution whose description includes
the README marker `mcp-name: io.github.dzenlotus/worklife-agent`, as in version 0.5.1.
Use an exact published package version and verify the command
that a registry client generates actually starts `worklife-recruiter mcp` before adding
`packages` to the manifest. Do not infer the command from the package name. No PyPI upload
is needed solely for the current website-only manifest.

## Updating PyPI metadata

The source metadata lives in [pyproject.toml](../pyproject.toml). PyPI renders its keywords
as tags and its classifiers as linked categories. These changes reach PyPI only through a
new distribution; changing GitHub's README does not update an existing PyPI release.

After selecting the next release version and reviewing its contents:

```sh
uv build --no-sources
uvx twine check dist/*
```

The existing [package publishing workflow](../.github/workflows/publish.yml) builds the
committed revision and uses PyPI Trusted Publishing. Publish a new version through that
workflow, then verify the public summary, tags, classifiers, and ownership marker.
Keep `server.json`'s version aligned when publishing a new server version.

## Primary references

- [GitHub repository topics](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics)
- [PyPI project metadata and keyword tags](https://docs.pypi.org/project_metadata/)
- [Python project metadata specification](https://packaging.python.org/en/latest/specifications/pyproject-toml/)
- [MCP Registry custom installation path](https://github.com/modelcontextprotocol/registry/blob/main/docs/reference/server-json/generic-server-json.md#server-with-custom-installation-path)
- [Official registry requirements](https://github.com/modelcontextprotocol/registry/blob/main/docs/reference/server-json/official-registry-requirements.md)
- [MCP Registry publishing guide](https://modelcontextprotocol.io/registry/quickstart)
- [MCP Registry authentication](https://modelcontextprotocol.io/registry/authentication)
- [Official publisher GitHub token support](https://github.com/modelcontextprotocol/registry/blob/v1.8.6/cmd/publisher/auth/github-at.go#L132-L171)
- [PyPI ownership verification](https://modelcontextprotocol.io/registry/package-types#pypi-packages)
- [uv commands with different package names](https://docs.astral.sh/uv/guides/tools/#commands-with-different-package-names)
