# The daily agent loop

1. **Orient.** Open the intended checkout. Read instructions, README, git status, and the latest handoff. Search the selected vault only for relevant prior decisions. Verify the account before using an external connector.
2. **Define completion.** State the outcome, constraints, authorized actions, and observable acceptance criteria. For behavior work use Given/When/Then. Resolve only questions that block useful work.
3. **Implement a small working path.** Use the existing stack and repository conventions. Let either Codex or Claude own a bounded task. If both work concurrently on overlapping code, create separate branches/worktrees and record ownership.
4. **Verify the behavior.** Run relevant tests and exercise the core pipeline. Record results and uncertainty. Expand testing when failures or new changes warrant it.
5. **Hand off or finish.** Use `sudarshan-handoff` or the template. Include exact next action and authorization scope. Review the diff; commit, push, or publish only when authorized. Verify remote state before claiming completion.
6. **Retain durable lessons.** Save supported decisions in the project's notes or selected vault and update its index. Keep transient state in the handoff. Do not turn raw transcripts into startup instructions.

Example starting prompt:

> Read this repository's instructions and latest handoff. Implement [outcome]. Completion means [observable behavior]. Preserve current local changes. Use the existing tests and report their results. You may edit and test; ask before publishing or sending messages.

Switching agents: save the handoff in the existing project location, end or pause the current session, launch the other agent in the same checkout, and ask it to read that handoff and verify git status before continuing. Session IDs and chats do not have to travel between computers; the repository plus a compact authorized handoff carries the work.

For simultaneous coding, `git worktree add ../project-task -b task/short-name` creates an isolated checkout. Install dependencies according to that repository. Agent launchers apply across worktrees; do not copy global settings into every checkout.
