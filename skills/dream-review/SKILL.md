---
name: dream-review
description: Walk through Dream drafts marked ready and promote each accepted lesson to the scope where both Codex and Claude will use it. Use weekly, or when a dream digest reports ready drafts.
---

# dream-review

Turn confirmed Dream drafts into durable instructions. The user decides every promotion; this skill proposes and applies.

Resolve the vault from the active global/project loader. If it is unavailable, ask for its location; do not fall back to an old employer vault. `<claude>` is the Claude home (`CLAUDE_CONFIG_DIR`, default `~/.claude`); `<harness>` is the agent-loop checkout under the project root.

## 1. Collect

Find every `<claude>/projects/*/memory/drafts/*.md` with `status: ready`. If there are none, say so, mention how many plain drafts are still gathering confirmations, and stop without changes.

## 2. Review one at a time

For each ready draft, show its claim, `addresses`, `confirmations`, the evidence cited by the dreams that confirmed it, and a proposed target from the table below. Ask the user to accept, edit, reject, or defer. Edit means revise the wording, then ask again.

| Lesson scope | Target |
| --- | --- |
| A fact about one project | That project's memory root (`<claude>/projects/<project>/memory/`) |
| A personal preference or fact about the user | The vault's `me/` notes; both clients read the vault |
| A working rule for every project | `templates/core.md` or a skill in `<harness>`, which installs it for both clients |

Prefer the narrowest scope that covers the evidence. Lessons drawn from Codex sessions should not land in a Claude-only project memory unless the fact really is project-specific.

## 3. Apply the decision

- **Accept, project:** move the file to the memory root, drop `status`, `confirmations`, and `last_confirmed`, add `promoted_from: <proposed_in>` while keeping `addresses`, and add its MEMORY.md line: `- [<name>](<filename>) — <description>`.
- **Accept, personal:** add the lesson to the most relevant `me/` note (create one only if none fits, and update the vault index), followed by `<!-- promoted_from: <proposed_in>; addresses: <addresses> -->`. Then archive the draft as promoted.
- **Accept, every project:** in `<harness>`, create a branch, add the rule followed by the same `promoted_from` comment, run the repository tests, and show the diff. Commit, push, or open a PR only with explicit approval. Archive the draft as promoted once the user approves the change.
- **Reject:** move it to `drafts/archive/` with `> Archived YYYY-MM-DD: rejected in dream-review — <reason>.`
- **Defer:** leave it unchanged.

Archive as promoted means move to `drafts/archive/` with `> Archived YYYY-MM-DD: promoted to <target>.`

## 4. Report

List each draft with its decision and target. The `promoted_from` and `addresses` markers let the next dream check whether each lesson is holding.
