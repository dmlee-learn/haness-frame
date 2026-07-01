# Design Discussion Framework

This harness is intended to run design work as a structured discussion, not as
one long prompt.

## Core Idea

The harness separates responsibilities:

```text
Project Scout  -> searches related projects before planning starts
Researcher      -> coordinates external evidence and records citations
Planner         -> frames the problem and proposes options
Architect       -> reviews interfaces, data flow, and tradeoffs
Critic          -> challenges assumptions and missing tests
Debugger        -> analyzes failures and logs
Decision Maker  -> selects one design and writes the implementation brief
Coder           -> creates the patch after the design is accepted
```

The important rule is that the coder should not be asked to invent the design.
The coder receives a short implementation brief after discussion has converged.

## Internet Research Contract

All roles may search the internet. The researcher coordinates evidence, but
search is not exclusive to the researcher.

When a new project is proposed, the first step is Google project discovery.
The project scout searches related projects, existing products, open source
repositories, alternatives, architecture examples, and common failure modes
before the planner creates design options.

Use Google or another general search provider when a role needs alternatives,
current documentation, exact error evidence, ecosystem comparisons, or known
limitations. Prefer official documentation, source repositories, release notes,
issue trackers, and papers when available.

Search results must be stored as structured evidence:

```text
query:
provider:
url:
title:
excerpt:
retrieved_at:
confidence:
```

Research notes should distinguish:

```text
Verified facts
Assumptions
Open questions
Design impact
```

## Debate Contract

Each debate round should be small:

```text
1. Project Scout summarizes related projects and reusable patterns.
2. Planner states the current proposal.
3. Each role may request or run search for missing current evidence.
4. Architect reviews feasibility and integration cost.
5. Critic lists blocking risks only.
6. Planner revises the proposal.
7. Decision Maker accepts, rejects, or requests one more round.
```

Stop after two debate rounds unless the open issue is clearly blocking.

## Output

The final design record should contain:

```text
Decision
Context
Evidence
Rejected options
Implementation plan
Verification commands
Rollback plan
```

## Project Document Layout

Harness-generated documents should be grouped by project:

```text
projects/<project-slug>/docs/
```

Use the same project slug for related design sessions, role discussions,
research notes, and decisions.
