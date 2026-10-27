# Free agent-loop skills

Nine MIT-licensed skills are available individually or as one free bundle. Start with the four standalone workflows; they use the context you provide and do not require a personal vault. There is no purchase, marketplace account, or subscription requirement.

| Skill | What it helps with | Setup |
|---|---|---|
| `handoff` | Give another agent the current state, checks, constraints, and next action | Task context and a project folder |
| `create-tickets` | Turn requirements into scoped tickets with observable acceptance criteria | Requirements; a tracker connection only for remote creation |
| `draft-prd` | Draft or review evidence-led product requirements | Problem context and available evidence |
| `draft-gtm` | Draft positioning, discovery guides, or demos for a named audience | Product, audience, and customer evidence |
| `check-follow-ups` | Find important unanswered sent-email threads | Authorized email tools; reporting is read-only |
| `organize` | File and index notes while preserving provenance | Configured knowledge vault with INDEX.md |
| `dream` | Review recent work and draft lessons for review | Vault, project root, agent homes, and authorized history access |
| `dream-review` | Review ready Dream drafts and place accepted lessons at the right scope | Existing Dream drafts and the configured knowledge system |
| `sync-meetings` | Save each new call's transcript and grounded summary as one vault note | Configured vault and an authenticated Granola or Fireflies connector |

The catalog includes a concrete example prompt and prerequisites for each skill. Skill format portability does not guarantee the same tools, filesystem access, or connectors in every agent. Agent-specific runtime behavior still needs validation in the intended environment.

## Use a skill

Install the chosen skill folder with your agent's supported skill installer or into its configured skills directory. Each installed folder must contain its own SKILL.md and any bundled references. Read the instructions before use. Do not replace an existing customized skill silently; compare the versions first.

Then ask for the task normally or explicitly name the skill if your agent supports that. For example:

- “Use handoff to prepare the next coding session, including the branch, changed files, checks, and next action.”
- “Use create-tickets to turn these requirements into engineering tickets. Draft locally and include Given/When/Then criteria.”
- “Use draft-prd to review this proposal. Separate observations, assumptions, missing metrics, and success criteria.”

The general workflows accept supplied project context. A configured vault can add relevant voice or audience guidance, but is optional for those workflows. Mail tools and knowledge-system paths are prerequisites for the skills that actually use them; the bundle does not create those connections.

## Build or inspect the archives

From an agent-loop checkout with Python 3.10+:

```sh
python3 tools/package_skills.py
```

The ignored `dist/skills/` directory contains nine individual ZIPs, `agent-loop-skills.zip`, a catalog with prompts/prerequisites and source hashes, this guide, and SHA256SUMS. Each individual ZIP extracts to a skill-named folder with SKILL.md, references when needed, and LICENSE. The combined ZIP contains `skills/<name>/` folders, a catalog, guide, and license.

The builder preserves source files, refuses symlinked resources and nonempty unmanaged output directories, and emits reproducible archives. ZIPs contain only skill resources and licensing/documentation; they exclude vaults, account credentials, transcripts, runtime state, and native optimizer evidence.

## What remains part of the harness

Installing Dream's instructions does not schedule nightly runs. The harness installer supplies shared configuration and optional scheduling; use the checkout's setup guide for that larger system. Native RTK/Headroom routing, launch services, and command hooks are separate integrations, not portable skill instructions.

You can share the free ZIPs directly or list them on a skill directory. Marketplace publication is optional and may have its own review, delivery, and licensing terms. The current bundle is prepared locally; no marketplace listing is created by the build command. Preserve the included MIT license when redistributing.
