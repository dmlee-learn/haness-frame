# haness-frame

Local multi-model coding harness scaffold.

## Goal

Use separate local models for separate responsibilities:

```text
Planner / Reviewer:
  vLLM NVIDIA-Nemotron-Nano-9B-v2

Coder / Patch Generator:
  vLLM Qwen2.5-Coder-14B-Instruct-AWQ

Fallback / Tool-call:
  vLLM Qwen3-8B-AWQ

Escalation:
  Gemini or another cloud model
```

The key rule is strict role separation. The planner summarizes, decomposes,
and reviews. The coder generates concrete patches.

## Files

```text
config/harness.yaml        Model endpoints and role policy
config/roles.yaml          Role definitions for design discussion
config/design_loop.yaml    Structured research/debate/decision stages
docs/architecture.md       Harness design and loop
docs/design-discussion-framework.md  Design discussion workflow
docs/roadmap.md           Implementation priorities and phases
docs/ko-test-project-manual.md       Korean test project manual
docs/prompts.md            Prompt contracts per role
scripts/check-services.ps1 Windows/WSL service check
scripts/start-vllm-*.ps1   Start planner/coder/fallback vLLM profiles
src/haness_frame.py        Thin CLI entrypoint
src/haness_frame_app/      Role-based implementation modules
```

## Quick Check

From this directory:

```powershell
python .\src\haness_frame.py check
python .\src\haness_frame.py show-config
python .\src\haness_frame.py roles
python .\src\haness_frame.py design-loop
python .\src\haness_frame.py init-db
python .\src\haness_frame.py services
```

Check local services:

```powershell
.\scripts\check-services.ps1
```

Start the 14B coder profile:

```powershell
.\scripts\start-vllm-coder-14b.ps1
```

Start the Nemotron planner profile:

```powershell
.\scripts\start-vllm-planner-nemotron.ps1
```

Restore the Qwen3-8B fallback profile:

```powershell
.\scripts\start-vllm-fallback-qwen3-8b.ps1
```

## Required Services

vLLM planner/coder/fallback endpoint:

```text
http://127.0.0.1:8000/v1
```

Optional Ollama backup planner endpoint:

```text
http://127.0.0.1:11434
```

## Recommended Runtime

Planner context:

```text
8192 or 12288 tokens to start
```

Coder context:

```text
8192 or 12288 tokens to start
```

Keep patches small. Do not ask one model to plan, edit, test, and judge in a
single pass.

## Design Discussion Workflow

Start the local UTF-8 web form:

```powershell
python .\src\haness_frame.py serve
```

Then open:

```text
http://127.0.0.1:8765/
```

Use this web form when the original request contains Korean or other non-ASCII
text. The generated harness files still use the English working description.

Configure AI services in the same local web server:

```text
http://127.0.0.1:8765/settings
```

The AI services page supports:

```text
- service company
- provider type
- model
- base URL
- API key environment variable name
- enabled/disabled state
- multiple roles per service
- edit/update/delete
```

Supported role examples:

```text
project_scout, context_curator, researcher, planner, designer, architect,
critic, debugger, decision_maker, coder, reviewer, escalation
```

Configure UI language:

```text
http://127.0.0.1:8765/preferences
```

Language packs live under:

```text
lang/
```

The user-selected language is stored in a browser cookie. The server default
language is stored in SQLite.

Manage generated projects:

```text
http://127.0.0.1:8765/projects
```

Each project detail page includes a ZIP download link. Download URLs use this
form:

```text
http://127.0.0.1:8765/download?name=<project-slug>
```

Project detail pages also let you assign AI services to roles for that project:

```text
http://127.0.0.1:8765/project?name=<project-slug>
```

Saved role routing lives in:

```text
projects/<project-slug>/project-settings.json
projects/<project-slug>/docs/04-agent-routing.md
projects/<project-slug>/docs/05-project-settings.md
```

Settings are stored in SQLite:

```text
data/haness.db
```

Default service rows include local vLLM, Ollama, Codex, and Claude placeholders.
API keys should be stored in environment variables and referenced by name in the
`api_key_env` field.

Create a full project harness workspace:

```powershell
python .\src\haness_frame.py create-project --project "internal-business-system" "Build an internal business system for approvals, tasks, documents, and reporting"
```

Recommended rule: keep generated harness files in English. If the original
request is not English, pass an English working description:

```powershell
python .\src\haness_frame.py create-project --project "internal-business-system" --english-description "Build an internal business system for approvals, task requests, document management, messaging, leave requests, and organization management" "Build an internal business system"
```

The original request is stored only in:

```text
context/original-request.md
```

This creates:

```text
projects/internal-business-system/
  README.md
  AGENTS.md
  CLAUDE.md
  context/original-request.md
  docs/00-workflow.md
  docs/00-runtime-map.md
  context/business-context.md
  context/source-materials.md
  research/search-backlog.md
  docs/01-project-discovery.md
  docs/02-role-discussion.md
  docs/03-decision-record.md
  docs/04-agent-routing.md
  docs/05-project-settings.md
  docs/06-system-runtime.md
  docs/07-roadmap.md
  prompts/role-briefs.md
  implementation/README.md
  workspace/state.json
  workspace/services.json
  workspace/manifest.json
  workspace/scorecard.json
  src/harness_app/
```

Create a design session file:

```powershell
python .\src\haness_frame.py design-template --write --project "pycapture-tool-pro" "Add role-based internet research and debate"
```

Create a shorter discussion skeleton:

```powershell
python .\src\haness_frame.py discuss --write --project "pycapture-tool-pro" "Design a local coding harness workflow"
```

Generated harness documents are written under:

```text
projects/<project-slug>/docs/
```

If `--project` is omitted, the project folder name is derived from the task.

The intended loop is:

```text
Project Scout -> Researcher -> Planner -> Designer -> Architect -> Critic -> Planner -> Decision Maker -> Coder
```

All roles may use internet search. Use Google when alternatives, current docs,
exact errors, known limitations, or ecosystem comparisons are needed. The
researcher coordinates evidence, but search is available to planner, designer,
architect, critic, debugger, coder, and decision maker. The coder should receive
only the accepted implementation brief.

For a new project request, the harness starts with Google project discovery.
It should look for related projects, existing products, open source repositories,
alternatives, architecture examples, and common failure modes before planning.
