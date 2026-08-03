# Platform Query And Praxis Roadmap - 2026-08-03

## Status

Point 9 is complete. Phases 10-13 were implemented on 2026-08-04; exact gate
status and external blockers are recorded in
`PHASES_10_13_REPORT_2026-08-04.md`.

The decision is to keep Praxis as a portable epistemic protocol and use model
platforms as replaceable execution substrates. Praxis will not grow its own
general agent runtime, conversational memory, sandbox, scheduler, browser,
tool registry or multiagent coordinator.

This is a point-in-time query. Model names, prices, beta status and hosted
features are operational facts to discover at runtime, not Praxis domain
constants.

## Official Platform Snapshot

### OpenAI

The current OpenAI model catalog lists the GPT-5.6 Sol, Terra and Luna tiers.
The Responses API supports structured outputs and hosted tools; current model
guidance adds programmatic tool calling, persisted reasoning and beta
multiagent execution. Native compaction and hosted computer environments
cover long-running context and workspace concerns. The Agents SDK adds
sessions, handoffs, guardrails, human-in-the-loop mechanisms and tracing.

Relevant primary sources:

- [OpenAI model catalog](https://developers.openai.com/api/docs/models)
- [GPT-5.6 model guidance](https://developers.openai.com/api/docs/guides/latest-model)
- [Responses API computer environment and compaction](https://openai.com/index/equip-responses-api-computer-environment/)
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
- [Agents SDK tracing](https://openai.github.io/openai-agents-python/tracing/)

The Assistants API is deprecated and scheduled for removal in August 2026, so
Praxis must not create a new integration against it.

### Anthropic

The current Anthropic catalog lists Claude Fable 5, Opus 5, Sonnet 5 and Haiku
4.5. Structured Outputs are generally available for current models. Managed
Agents provides long-running and asynchronous sessions, persistent files,
managed or self-hosted sandboxes, scheduled execution, permission policies,
skills, MCP and multiagent orchestration. Server-side compaction, context
editing and memory tools cover long-running conversation management.

Relevant primary sources:

- [Claude models overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Claude Managed Agents overview](https://platform.claude.com/docs/en/managed-agents/overview)
- [Managed Agent tools and permissions](https://platform.claude.com/docs/en/managed-agents/tools)
- [Multiagent orchestration](https://platform.claude.com/docs/en/managed-agents/multiagent-orchestration)
- [Context editing and compaction](https://platform.claude.com/docs/en/build-with-claude/context-editing)
- [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Programmatic tool calling](https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling)

Managed Agents remains beta. Praxis may test it as an adapter but cannot make
the core depend on its lifecycle or persistence semantics.

## Capability Boundary

| Concern | OpenAI | Anthropic | Praxis decision |
|---|---|---|---|
| Model execution | Responses API | Messages API | Delegate through adapters |
| Long-running work | Background execution, Agents SDK | Managed Agent sessions | Delegate |
| Context pressure | Native compaction, persisted reasoning | Compaction, context editing | Delegate conversational context |
| Workspace and tools | Hosted shell, skills, MCP, tool search | Sandbox tools, skills, MCP | Delegate |
| Multiagent | Responses beta, Agents SDK | Managed Agents multiagent | Do not reproduce in core |
| Structured output | JSON Schema | JSON Schema subset | Enforce at adapter and parser |
| Operational approval | SDK human-in-the-loop and guardrails | Permission policies and confirmations | Use host gate; Praxis records evidence |
| Runtime tracing | Agents SDK traces and evals | Session events and Console evals | Supplemental, never canonical evidence |
| Epistemic artifact | No Praxis-specific equivalent | No Praxis-specific equivalent | Praxis owns |
| Review/deflation rule | Application policy | Application policy | Praxis owns |
| Human DecisionMemo | Application policy | Application policy | Praxis owns |
| Negative memory semantics | Application policy | Application policy | Praxis owns |

Provider conversation state is not evidence lineage. A provider may compact,
summarize or discard its working context; the versioned Praxis artifact,
benchmark, hostile review, deflation and DecisionMemo remain explicit and
provider-neutral.

## Development Roadmap

### Phase 10 - Cross-provider calibration

Goal: prove that the fixed DARKROOM contract behaves acceptably on at least
two providers before adding execution infrastructure.

Work:

1. Restore an OpenAI API credential and query the account's Models API rather
   than assuming catalog availability.
2. Run the frozen eight-case suite on the lowest-cost current OpenAI tier that
   supports strict structured output, then on the next tier only if quality
   misses the gate.
3. Repeat the selected OpenAI configuration and Claude Sonnet 5 configuration
   three times each to measure recommendation variance.
4. Record exact model ID, reasoning/effort setting, prompt hash, token usage,
   latency and current price supplied at invocation.
5. Keep raw provider output ignored; commit only aggregate dated reports.

Exit gate:

- 100% first-pass contract validity,
- at least 95% acceptable recommendations across repeated runs,
- zero `REJECT` results on the explicitly repairable calibration cases,
- mean objection-concept recall at least 75%,
- no provider-specific field in a serialized `HypothesisRecord`.

If no configuration passes, revise the adapter or rubric. Do not add another
reviewer agent or lifecycle state.

### Phase 11 - Approval-safe local MCP adapter

Goal: expose Praxis to both provider ecosystems through one portable tool
boundary.

Work:

1. Add an optional local stdio MCP adapter outside the domain package.
2. Initially expose read operations and bounded protocol mutations only:
   inspect records, capture a seed, advance, preflight, attach benchmark,
   attach review and deflate.
3. Do not expose `confirmed_by_human: true` as a model-controlled boolean.
   A model may propose a decision; only a separate host approval callback can
   create the `ApprovalEvidence` used by `DecisionMemo`.
4. Classify tools as read-only, reversible mutation or consequential action.
   Require host confirmation for every consequential action.
5. Add conformance tests proving that a model tool call cannot self-approve,
   rewrite history or bypass the exact-version review binding.

Exit gate:

- the same MCP contract works with local OpenAI and Anthropic clients,
- denied or absent approval leaves no partial decision,
- the current 85-test suite remains green and new adversarial MCP tests pass,
- no network listener or authentication subsystem is added to Praxis.

Remote MCP is explicitly deferred until an actual remote deployment creates
an authentication requirement.

### Phase 12 - Two execution proofs, no new runtime

Goal: demonstrate that vendor runtimes can execute the same Praxis workflow
without owning its methodology.

Work:

1. Configure one OpenAI Responses/Agents SDK proof and one Claude Managed
   Agents proof against the same MCP tools.
2. Run three identical scenarios: bounded `TEST`, repairable `REVISE`, and
   terminal `REJECT`.
3. Keep author, reviewer and decider as separate invocations or isolated
   contexts. Vendor handoffs may transport work but cannot merge those roles.
4. Compare completion, evidence lineage, approval behavior, latency and cost.
5. Store vendor trace IDs in adapter-side run receipts, not domain records.

Exit gate:

- both platforms produce equivalent valid Praxis histories,
- a provider trace can disappear without damaging the Praxis evidence chain,
- no platform session ID is required to deserialize or resume a Praxis record.

### Phase 13 - Stability and release engineering

Goal: make the small protocol dependable before expanding its meaning.

Work:

1. Add CI for the deterministic conformance suite on supported Python
   versions.
2. Add mocked provider-contract tests to CI; keep paid live evals manual or
   explicitly scheduled with a hard cost ceiling.
3. Add an adapter-side `ExecutionReceipt` only if Phase 10 shows that prompt,
   model and cost provenance cannot be reconstructed reliably from reports.
4. Package a versioned pre-release and document migration of the SQLite
   schema.
5. Test abrupt process termination and database recovery, the largest current
   deterministic reliability gap.

Exit gate:

- reproducible installation from a clean environment,
- deterministic CI is green,
- storage recovery tests pass,
- optional provider packages do not enter core dependencies.

### Phase 14 - Evidence-gated product expansion

Goal: decide whether Praxis needs more than one artifact type or a dedicated
human interface.

Prerequisites:

- at least 20 real protocol runs,
- categorized failures and decision reversals,
- evidence that the existing `HypothesisRecord` cannot express a repeated
  case, or that approval ergonomics cause repeated operator errors.

Only then consider a second artifact type or a thin approval interface. Do not
add a room, autonomous subsystem, vector database, generic research memory or
desktop dashboard merely because provider APIs make it easy.

## Immediate Next Action

Do not expand the product surface. Complete the missing OpenAI live calibration
and execution proof when an API credential is available, then repeat the
hosted-runtime proof only when the account exposes the relevant stable or beta
API. Phase 14 remains evidence-gated by 20 real protocol runs.
