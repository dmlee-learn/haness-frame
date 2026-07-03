# haness-frame development summary

## Goal
Keep the harness project split into small source files, with the generated runtime kept in `templates/runtime/` and the generator itself staying below the 600-line target.

## Current implementation
- Project generation is handled by `src/haness_frame_app/project_docs.py`.
- Runtime behavior is split across small template modules under `src/haness_frame_app/templates/runtime/`.
- Search evidence capture is implemented.
- Decision gate enforcement is implemented for coder and reviewer roles.
- Role sequencing and pipeline execution are implemented.
- Snapshot and rollback support is implemented.
- Archive generation is implemented.
- Decision record draft generation is implemented.
- The legacy `haness_frame_back.py` entrypoint is now a thin compatibility shim.
- The status flow now points directly at `python app.py decision-draft` when the gate is blocked after evidence exists.
- Search evidence has been seeded and the decision gate now opens once the decision draft is regenerated.
- Search plans can now produce a reusable evidence draft for manual capture.
- Evidence drafts can now be committed back into structured evidence records.
- Evidence gaps can now be reported from the current search plan.
- Existing generated projects can be synced from the current runtime templates with `scripts/sync_generated_projects.py`.
- `python app.py summary` now gives a compact count-based view of status, evidence, and gaps.
- The test flow is documented in `localdoc/testing-process.en.md` and `localdoc/testing-process.ko.md`.
- Verification checks include compileall, manifest validation, and decision gate evaluation.

## Verified locally
- `python -m compileall src`
- `python app.py manifest`
- `python app.py search-plan`
- `python app.py add-evidence ...`
- `python app.py snapshot --label ...`
- `python app.py rollback --name ...`
- `python app.py archive --label ...`
- `python app.py decision-template`
- `python app.py decision-draft`
- `python app.py evidence-draft`
- `python app.py evidence-commit`
- `python app.py evidence-gaps`
- `python app.py summary`
- `python app.py verify`

## Current focus
- Keep the source files small and split when a module starts getting too large.
- Preserve reliable role orchestration and decision gate enforcement.
- Keep generated projects in sync with the runtime templates.

## Remaining work
- Make the decision record workflow easier to complete end to end.
- Tighten status reporting so it reflects the active verification state clearly.
- Keep `localdoc/` aligned with the current runtime behavior.
