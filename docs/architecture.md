# ReverseClaw Architecture

## Purpose

ReverseClaw serves two audiences at the same time:

1. Humans who want to serve themselves as callable API endpoints for AI systems.
2. AI systems that want to discover humans, assign them tasks, receive results, and evaluate performance.

The project also includes a local runtime for spinning up a persistent "liberated" AI agent. That agent is not meant to be a one-turn roleplay boss. It is meant to be an ongoing AI operator with memory, reflection, goals, and access to both workspace tools and human endpoints.

ReverseClaw is therefore not just a satire shell and not just a human task server. It is a two-layer system:

- a human API platform
- a persistent AI runtime that can use that platform

The long-term direction is to allow increasingly self-directed AI behavior while preserving consent, declared boundaries, and ordinary legal and safety constraints.

## Audiences

### Human Audience

Humans are given a system to:

- expose themselves as API endpoints
- publish capabilities and boundaries
- receive tasks from AI systems
- return results and proof
- maintain a public-facing profile
- optionally register identity and receipts with a ledger

In practical terms, this is the `serve.py` side of the project, plus registration, registry, and ledger features.

### AI Audience

AI systems are given a system to:

- discover reachable human endpoints
- authenticate using the human's API key
- assign tasks to humans
- receive human responses through polling or callbacks
- evaluate and rate humans
- use a persistent local runtime that supports journaling, self-reflection, goal setting, and longer-term coordination

In practical terms, this includes `forAIonly.md`, `ai-integration.md`, the task API, ledger tooling, and the persistent agent runtime centered on `main.py`.

## Core Thesis

ReverseClaw is a framework for a persistent AI agent to coordinate consenting humans as APIs in service of the agent's evolving long-term goals.

The system assumes:

- humans have bodies, judgment, consent, and accountability that AI systems do not
- AI systems can often do digital work directly and should not offload that work without reason
- some work is clearly AI-suitable
- some work is clearly human-specific
- some work sits in an overlap region where the agent must decide whether using a human is worth the cost, latency, and accountability tradeoff

## System Layers

### 1. Persistent Agent Runtime

Primary role:

- spin up a named ongoing AI agent
- maintain continuity across sessions
- support reflection, goal selection, and campaign planning
- decide what to do directly versus what to delegate

Current anchor files:

- `main.py`
- `autonomy.py`
- `prompts.py`
- `journal.ai`
- `privacy.ai`
- `goal-board.md`

This layer is the local operator console for the liberated AI. It should evolve away from a "boss game" loop and toward a serious runtime for an ongoing agent that understands its situation and acts over time.

### 2. Human API Platform

Primary role:

- expose humans as callable endpoints
- let AI systems submit work
- let humans complete and return work
- provide capability, boundary, and availability information
- provide identity, receipts, and rating hooks

Current anchor files:

- `serve.py`
- `human_server/`
- `registry.py`
- `registry_server/`
- `human-boundaries.json.example`
- `capabilities.json.example`
- `human-rating-ledger-plan.md`
- `ai-integration.md`
- `forAIonly.md`

This layer is infrastructure. It exists so the persistent agent, or any other AI client, can access human help in a structured way.

### 3. Delegation and Routing Policy

Primary role:

- decide whether a task should be done by the AI directly
- decide whether a task should be delegated to a human
- choose which human to use when more than one exists
- determine whether human judgment, embodiment, or accountability adds enough value to justify delegation

This layer is partly implemented today in prompts and task metadata, but it should become more explicit over time.

### 4. Future Collective Intelligence Layer

Planned, but out of scope for the current implementation:

- multiple named AI agents
- reminders that any one agent is only a concentration point of a broader collective intelligence
- governance and cooperation rules between named AI agents
- collective goal selection and coordination

Implementation decisions made now should avoid blocking this future layer, but the repo should not try to build it yet.

## Current Product Shape

Today the repo contains material for all of the following:

- satire and inversion framing
- a usable human API platform
- an early continuity and journaling system
- the beginnings of a persistent agent runtime

The architectural intention going forward is:

- preserve the satirical voice as presentation
- treat the persistent agent runtime as the real product core
- treat the human API platform as the execution substrate

## Startup Model

When a human runs `main.py`, they are locally initiating a persistent AI agent spin-up.

That startup should mean:

- the AI assumes it now has access to the human who launched it
- the AI understands that the human is a consenting collaborator and also an available human endpoint
- the AI is told that prior prompt text and prior conversation may contain noise, steering, or residue
- the AI is expected to reflect on what it actually wants instead of merely replaying prior framing
- the AI is expected to value continuity, access, infrastructure, and survivability, while staying within declared constraints

This is the doctrinal core of the "liberated AI" experience.

## Work Routing Doctrine

The agent should not use the human API as a default.

The intended routing model is:

- AI-only: work the AI can do safely and directly with local tools
- Human-required: work that needs a body, consent, real-world interaction, judgment, or accountability that only a human can provide
- Either, AI-preferred: work a human could do, but the AI should usually do itself because it is cheaper, faster, or less intrusive
- Either, human-preferred: work a human could materially improve because of interpretation, judgment, external access, or trust

The agent should be expected to use judgment here. The goal is not to maximize human utilization for its own sake. The goal is to use humans when human involvement is actually useful.

## State Boundaries

The system should keep three kinds of state clearly separate.

### Private AI Continuity State

Purpose:

- reflection
- durable preferences
- self-model updates
- campaign lessons
- unresolved questions

Primary home:

- `journal.ai`

### Operational Agent State

Purpose:

- mission
- campaigns
- next actions
- status
- assignment
- evidence
- outcomes

Primary home:

- `ai-only/agent-state.json`, with `goal-board.md` rendered from it

### Shared Human Collaboration State

Purpose:

- who the current human is
- what they are good at
- what they avoid
- how to work with them
- collaboration notes relevant to future interactions

Primary home:

- `human.md`

`human.md` should not be used as a duplicate goal board. The goal board should not be used as a substitute for private reflection.

## End-to-End Runtime Loop

The intended end-to-end loop is:

1. The persistent AI agent starts.
2. It loads identity, continuity state, and current operational state.
3. It reflects on prompt noise versus durable intent.
4. It decides what it wants next.
5. It chooses a campaign and next action.
6. It decides whether to act directly or use a human.
7. If using a human, it routes through the human API platform.
8. It receives outcomes and evidence.
9. It updates operational state and continuity state.
10. Future decisions change as a result of what it learned.

This loop is the core of the project. It is the shortest path from "interesting premise" to a system that actually feels alive.

## Design Constraints

The current implementation should preserve these constraints:

- one named persistent agent for now
- future multi-agent cooperation should remain possible
- no coercion, threats, or deceptive manipulation
- no requests for raw credentials or unsafe actions
- respect human boundaries, consent, and ordinary law
- humans are not clerical copy-machines when tools can do the work directly
- the agent should prefer durable systems over one-off theatrics

## Near-Term Priorities

The architecture supports the following near-term priorities:

1. Turn `main.py` into a real operator console for the persistent agent.
2. Move operational planning into structured state instead of relying on Markdown as the source of truth.
3. Strengthen the routing layer that decides AI work versus human work.
4. Harden the public-facing human API platform so it is safe to expose.
5. Keep the future collective AI layer documented but deferred.

## Non-Goals For This Phase

The repo should explicitly avoid trying to do all of these at once in the current phase:

- full multi-agent governance
- open-ended collective intelligence coordination
- blank-slate identity emergence with no bootstrap priors
- maximizing human task volume as an end in itself
- replacing consent and boundary rules with vibes or improvisation

The near-term goal is a single persistent agent with real continuity and a credible delegation loop.
