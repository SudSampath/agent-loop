---
name: handoff
description: Create a compact handoff between coding agents or work sessions with verified state, constraints, and an exact next action.
license: MIT
---

# Handoff

Read the current task state and relevant artifacts. Record the goal, scope, repository/branch, changed files, decisions, verification, blockers, authorization scope, and exact next action. Distinguish completed work from assumptions and pending checks.

Use the user's requested destination or the project's existing handoff. If handoffs live in a configured knowledge vault, resolve that path from the active instructions and read its INDEX.md before writing to ops/handoffs. Otherwise save a project-local HANDOFF.md. A vault is optional.

Keep the handoff concise and sufficient for the receiving agent to act without the raw conversation. Do not export raw transcripts, credentials, or private records into a shared repository, or promote provisional observations to durable preferences.
