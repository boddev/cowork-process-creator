# Real public metadata is not native availability

The optional Microsoft Learn snapshot in this skill's assets illustrates
real connection metadata without depending on private business data or
adding any Creator service. It is not a required connection for the Creator.

The existing public endpoint is `https://learn.microsoft.com/api/mcp`.
Its developer-side protocol observation returned three real tools:
`microsoft_docs_search`, `microsoft_code_sample_search`, and
`microsoft_docs_fetch`. The service documents Streamable HTTP and no
authentication. No account credentials, tool calls, deployments or Cowork
connection changes were made in that metadata probe.

Read `assets/learn-mcp-provenance.json` for the observation method, date,
sources and exact boundaries, and `assets/learn-mcp-tools.json` for the
unchanged tool definitions. Their title fields, multiline descriptions,
optional query/language default annotations and nullable output types are
real metadata, not mistakes to "repair." Do not invent required fields or
enums from descriptive prose.

To use any such endpoint in an output, distinguish these independent facts:

- Its URL/tool schema exists and has a trusted provenance.
- The target Cowork environment actually exposes or supports the connection.
- Required setup/sign-in/scopes and native approvals are satisfied for the
  intended operation.

Until the latter facts are observed, record the connection as unverified or
needs-setup. A public endpoint's existence is not proof that it is connected
to this user's Cowork task. Do not perform a network lookup from the Creator
builder, deploy a server, silently add a client, or treat a tool annotation
as permission.

Existing-native mode reuses an exposed platform tool. Packaged-remote mode
needs the actual supported connector configuration and included tool
descriptor; use the build skill's canonical rules. The compatible-source
export does not promise lossless connector/auth conversion.

The service's own identity and legal terms are not approved publisher
metadata for this Creator or its generated plugins.
