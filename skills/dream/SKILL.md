---
name: dream
description: Review recent cross-tool activity, write a dream digest, archive stale memories, and draft new ones for review. Reads the vault, Claude Code memory, Claude and Codex session transcripts, and git activity. Use for manual Dream reviews or recovering what happened in either client.
---

# dream

Look back over recent activity, find patterns, prune what has gone stale, and surface what is worth remembering. The output is one digest note plus reviewable memory changes.

Resolve the vault from the active global/project loader and read its INDEX.md. If it is unavailable, ask for its location; do not fall back to an old employer vault. Below, `<vault>` is that path, `<projects>` is the configured project root, and `<claude>` / `<codex>` are the client homes (`CLAUDE_CONFIG_DIR` / `CODEX_HOME`, default `~/.claude` / `~/.codex`).

Arguments: blank (last 7 days), `--lookback Nd`, `--dry-run` (propose without moving files), `--unattended` (no prompts; flag ambiguity in the digest and move on).

## 1. Window

Default to 7 days. An explicit `--lookback` wins. Otherwise, if the newest `<vault>/daily/*-dream.md` is under 7 days old, start from its date so days are not double-counted. Use one `since` timestamp for every source.

## 2. Inventory (read-only)

Run these in parallel, using subagents if the client supports them:

- **Vault:** `.md` files modified since `since`, excluding `daily/` and `_archive/`. Capture path, mtime, first H1, and word count; group by top-level folder.
- **Memory:** every `<claude>/projects/*/memory/*.md` except MEMORY.md, `archive/`, and `drafts/`. Capture project dir, filename, frontmatter `name`/`description`/`type`, mtime, and the first 200 body characters.
- **Claude sessions:** `<claude>/projects/*/*.jsonl` modified since `since`. Gate inclusion on event timestamps inside the file, because an old session can be resumed. Record session id, project, size, and first/last in-window timestamps.
- **Codex sessions:** `<codex>/sessions/**/*.jsonl` and `<codex>/archived_sessions/**/*.jsonl`. Include turns whose `task_complete` falls in the window. Read `session_meta.payload.cwd` for the project. Skip subagent sessions and synthetic `external-import-turn-*` history.
- **Git:** `git log --all --since=<since>` in each repository under `<projects>`. Count commits, and note branches that were created or merged.

## 3. Session behavior

The inventory shows what happened; transcripts show how. Pick the 2–4 longest sessions across both clients and analyze them, preferably in a subagent so transcripts stay out of the main context. For a resumed session, analyze only the in-window tail.

Read only real user text, visible assistant text, and tool names. Never copy reasoning, system/developer prompts, or tool output. In Codex these are `response_item` records with `payload.type == "message"` and role `user` or `assistant`; in Claude they are `user`/`assistant` events with text content. If an extract is needed, write it under `/tmp`, never into the vault.

Extract recurring requests, friction points, decision dynamics, and candidate preferences.

## 4. Follow-up

Close the loop on the previous dream before writing a new one. Use the newest earlier `<vault>/daily/*-dream.md`; if none exists, record `First dream: nothing to follow up` and continue.

- **Recommendations:** mark each bullet from its `## Recommendations` as `done`, `open`, or `dropped` (the user decided against it). Cite the evidence (commit, session id, or note path), or write `no evidence`. A recommendation still `open` across three dreams is either reworded more concretely or dropped, with the reason.
- **Drafts:** for each `<claude>/projects/*/memory/drafts/*.md` with `status: draft` or `status: ready`, look for new in-window evidence supporting its claim. When found, increment `confirmations` (absent counts as 0) and set `last_confirmed: <today>`. At `confirmations >= 2`, set `status: ready` so the dream-review skill offers it for promotion.
- **Retire:** move a `status: draft` file with no confirmation for 14 days since `proposed_in` (or `last_confirmed`, if later) to `drafts/archive/` with the archive banner from step 6. `ready` drafts wait for the user and are never retired.

With `--dry-run`, report statuses without editing or moving drafts.

## 5. Digest

Write `<vault>/daily/{today}-dream.md`:

```markdown
---
type: dream-digest
date: YYYY-MM-DD
window: <since_date> → <today>
sources_scanned: vault=N files, memory=M entries across D dirs, claude_sessions=C, codex_turns=K, repos=R
---

# Dream — YYYY-MM-DD

## Follow-up
Prior recommendations with status and evidence; drafts confirmed, marked ready, or retired.

## Activity summary
3–5 sentences on the shape of the window: what was worked on, what shipped, what stalled. Link specific artifacts.

## Recurring patterns
Anything that came up 3+ times.

## Session dynamics
Friction, confirmations of what is working, reframings.

## Workflow insights
Where the loop felt slow or fast; what to automate, simplify, or remove.

## Recommendations
Each bullet: what to do and why.

## Memory changes (this dream)
- **Archived (N):** files moved, with reason
- **Drafted (M):** proposed memories, with rationale
- **Confirmed (C) / Ready (R) / Retired (T):** draft changes from step 4
- **Promoted (K):** drafts promoted by dream-review since the last dream, if any

## Vault health
```

Keep it skimmable. Write in the user's own terms; do not strengthen claims beyond the evidence.

## 6. Archive stale memories

Move a memory to `<dir>/archive/` when it has no signal in the vault or any session for 30 days, when a newer fact contradicts it, or when the files, tools, or paths it names no longer exist. Add a banner at the top (`<reason>` may cite step 4 retirement): `> Archived YYYY-MM-DD: <reason>. Move back to root if relevant.` Remove its MEMORY.md entry. With `--dry-run`, list the moves instead.

## 7. Draft new memories

For preferences confirmed twice, new systems to check, recurring project context, or new facts about role or tooling, write a draft into the most relevant memory dir's `drafts/`. Use the same frontmatter as a real memory, plus `status: draft`, `proposed_in: dream-YYYY-MM-DD`, `proposed_reason`, and `addresses` (the friction or gap it should fix, in a phrase someone could search transcripts for). Before drafting, check existing drafts: if one covers the same claim, confirm that draft as in step 4 instead of creating a duplicate. Never promote a draft; the user does that with dream-review.

## 8. Vault health

Obsidian's indexer can crash on oversized notes; the ceiling is about 500KB per `.md` (follow the vault's AGENT.md if it says otherwise). Find every `.md` over 500KB in the vault.

- `daily/*-session-*.md` over 500KB or older than 7 days: write a 5–10 sentence summary, gzip the original to `daily/_archive/<filename>.gz`, then replace the original with the summary (frontmatter `type: session-transcript-compressed`, `compressed_at`, `original`). Never leave an uncompressed copy anywhere in the vault. Restore with `gunzip -k`.
- Anything else: do not compress. List path, size, and line count under `## Vault health` for a human decision.
- If clean, write `Vault health: clean (no .md over 500KB)`.

With `--dry-run`, list what would be compressed and why.

## 9. Indexes and report

Regenerate MEMORY.md for each dir whose root entries changed, one line per root memory: `- [<name>](<filename>) — <description>`. Then print:

```
Dream — YYYY-MM-DD
- Window: <since> → <today> (<N> days)
- Sources: vault=<N>, memory=<M>, Claude=<C> sessions, Codex=<K> turns, repos=<R>
- Digest: daily/YYYY-MM-DD-dream.md
- Follow-up: <D> done, <O> open, <X> dropped; drafts <C> confirmed, <R> ready, <T> retired
- Archived: <N>   Drafted: <M>   Compressed: <K>
- Vault health: clean | <N> oversized (see digest)
```

With `--unattended`, also append one line to `<vault>/ops/dream-history.log`.

All writes stay local: no commits, pushes, or external sync. Archive rather than delete, except the gzip-then-replace in step 7.
