# Code First UX/UI

Run from the website root. The main session owns scope, sequential delegation, acceptance and user communication. Preserve unrelated files. Verify the five named roles and seven readable project skills below. If any are missing, use the README installation instructions and reopen Codex from the site root.

Pass agents exact input/output paths, acceptance criteria and applicable skill files. Resolve skill names to `.agents/skills/<name>/SKILL.md` and have agents read those copies. For a chat brief, save relevant user text and scope decisions to `docs/design/inputs/brief-source.md`. For a supplied brief, use its path and save clarifications alongside it in the site.

## Stage acceptance

Stage documents live in `docs/design/`. Review each result against these criteria before recording it.

| Role | Inputs | Accepted result | Project skills |
| --- | --- | --- | --- |
| `discovery-specialist` | Source brief and project materials | `brief.md` covers goal, audience, scope and success criteria. Confirmed requirements have stable IDs and sources or user decisions. Separate assumptions and open questions. Each blocker names the affected decision and stage. | — |
| `design-researcher` | `brief.md`, available sources | `research.md` separates audience evidence, competitor observations and hypotheses. Link each material finding to its source, limitations and the UX decision it informs. Where audience evidence is missing, propose a validation method. | `ux-research-discovery-testing` |
| `ux-designer` | `brief.md`, `research.md` | `ux-spec.md` describes architecture, scenarios and interactions. Map mandatory requirements to observable acceptance criteria. Cover applicable loading, empty, error and recovery states. Flag unresolved decisions and omissions. | `product-design-and-ux` |
| `ui-designer` | `ux-spec.md`, site source, brand materials, existing design system | `design-system.md` and a working responsive prototype meeting UX criteria. Return source and launch configuration paths, verified launch command and local URL, and limitations. | `ui-ux-pro-max`, `frontend-design` |
| `design-qa` | `brief.md`, `ux-spec.md`, `design-system.md`, accepted prototype handoff | `qa-report.md` meets the QA rules below. Run QA in a separate thread. | `evaluate`, `web-accessibility`, `web-design-guidelines` |

Resolve blockers before dependent stages and continue unaffected work. Use the site's existing or selected stack, components and tooling. Clarify unresolved stack choices before UI. Route proposed behavior changes through the main session, specification changes to UX, and confirmed requirement changes to the user.

## Design system

Use `docs/design/design-system.md` as the source of truth. Create it before implementation if absent. Base it on established site design and brand where available. Document:

- Semantic tokens with exact values or aliases and intended use for applicable colors, typography, spacing, radii and other shared values.
- Visual hierarchy, composition, content, imagery and accessibility requirements.
- Relevant breakpoints and adaptations for layouts, navigation and components.
- Components by stable functional name (e.g. Primary action), purpose, anatomy, variants, states, keyboard behavior and responsive rules as applicable. Keep contracts independent of filenames and code identifiers.

Apply the system in site tokens, styles and components. Update documentation and code together when changing it. Add a rule to the site root's active `AGENTS.md` or `AGENTS.override.md` to read and follow the design system before UI work. Preserve other guidance and create a minimal `AGENTS.md` if needed.

## Record and resume

From the site root, use the state utility to find the first `pending`, `stale` or `blocked` stage. `complete` means all checks are current. The accepted prototype handoff is available when QA is next.

```bash
state() { python3 .codex/ux-ui-framework/workflow-state.py "$@"; }
state status
state record discovery --input docs/design/inputs/brief-source.md
state record research
state record ux
state record ui --source src --source package.json --launch-command 'npm run dev' --url http://localhost:5173
state record qa --outcome passed
```

Use actual site paths, command and URL. Repeat `--input` for relevant local materials and clarifications. Stage document dependencies are automatic. Record remote evidence and links in `research.md`. Repeat `--source` for complete relevant source directories, launch files and lockfiles outside `docs/design/`. Omit caches and generated output.

For legacy projects, start at Discovery and reuse documents only after checking current inputs and criteria. Use the existing design system as UI input and record the accepted version. Review or revise the first stale stage and re-record it. Recheck dependent results before accepting them. Reverify stale UI source, launch and relevant criteria before QA. Keep prior documents and reports as working material.

## QA and corrections

Use the accepted source, launch command and URL. Prefer Codex Browser for live checks and Playwright for headless, cross-browser or repeatable checks. Review code with `.agents/skills/web-design-guidelines/SKILL.md`. Check interactions, keyboard/focus, responsiveness, requirement coverage and design-system drift as applicable. If launch fails, log the error and mark browser checks unverified. Route recoverable issues through the main session and retry with a verified handoff.

Report each mandatory scenario's criterion, evidence and result (`passed`, `failed`, `unverified`). Give findings stable IDs, severity, expected/actual behavior and reproduction steps or locations. A failed or unverified mandatory criterion or a defect preventing a core scenario blocks delivery.

Through the main session, route implementation defects to UI, specification gaps to UX and requirement conflicts to Discovery. Record updated stages in order. Have QA recheck affected scenarios and regressions in a separate thread. Reuse unaffected evidence while criteria and behavior still apply. Continue while blockers are being resolved. Stop with the concrete blocker if a decision is pending, verification is unavailable or recheck finds the same blockers without progress.

Record `qa --outcome blocked` for a reviewed report with an accepted UI snapshot. If initial UI acceptance failed, keep launch diagnostics in the report and resume at UI. Record `qa --outcome passed` only when all mandatory scenarios pass and blockers close. Return deliverable links or paths, launch instructions, QA disposition, unresolved blockers and unverified checks.
