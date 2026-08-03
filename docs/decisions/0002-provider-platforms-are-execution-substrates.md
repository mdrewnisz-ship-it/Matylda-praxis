# ADR 0002: Provider Platforms Are Execution Substrates

Status: accepted

## Context

As of 2026-08-03, OpenAI and Anthropic both provide long-running agent
execution, context compaction, hosted or managed tools, sandboxes, skills,
MCP, approval mechanisms and multiagent coordination. Reimplementing these
layers would recreate the platform burden removed during the Lab-to-Praxis
extraction.

## Decision

Praxis remains a provider-neutral epistemic protocol. Provider runtimes may
execute work and carry transient context, but they do not own artifact state,
evidence lineage, hostile-review semantics, deflation or human decisions.

New platform integrations use existing ports or a shared MCP adapter. The core
package takes no dependency on an agent SDK. Provider sessions, traces,
reasoning state and tool-call metadata remain adapter-side and optional.

Provider-native approval gates protect operational actions. A Praxis
`DecisionMemo` still requires separate, explicit human approval evidence; a
model-controlled boolean is not sufficient at an agent-tool boundary.

## Consequences

- OpenAI and Anthropic can be replaced without migrating Praxis records.
- Improvements in hosted runtimes benefit Praxis without changing its domain.
- Vendor traces supplement but cannot replace versioned evidence.
- MCP becomes the preferred shared integration boundary after cross-provider
  calibration.
- A dedicated agent runtime, generic memory and multiagent layer remain out of
  scope.
- Beta provider features may be evaluated without becoming core contracts.
