---
name: check-follow-ups
description: Find email threads where the user sent the last message and is still waiting on a reply, ranked by how much the silence matters. Read-only report; never sends.
---

# check-follow-ups

Find threads that went quiet on the other side and need a nudge. This is a read-only report: never send, archive, label, or draft in the mail account unless the request explicitly asks for drafts.

Arguments: blank (5+ business days silent, last 30 days), `--days=N` (silence threshold in business days), `--window=Nd` (how far back to scan), `--drafts` (also write a suggested nudge for each high-priority thread in the report).

1. **Find the mail tools.** Use the connected Gmail tools. If only authentication stubs are available, stop and ask the user to authenticate.
2. **Collect candidates.** Search sent mail in the window (`in:sent after:YYYY/MM/DD`). For each thread, keep it only if the user's message is the last one, the silence meets the threshold (weekends excluded), and the message asked for something or expected a reply.
3. **Exclude** automated senders, notifications, auto-replies and out-of-office responses, closings with no expected reply ("thanks", "sounds good"), threads the user moved on from in a later thread with the same person, and threads silent longer than 30 days (those need a fresh approach, not a nudge; list their count only).
4. **Rank.**
   - **High:** an explicit, time-bound ask the user is blocked on, such as an interview step, application or offer status, a requested introduction, or a decision someone owes the user.
   - **Medium:** an external conversation where a reply is expected but nothing is blocked, such as a networking follow-up or a shared document awaiting feedback.
   - **Low:** a reply would be nice, or the thread is mostly informational.
5. **Report.**

```
Follow-ups — YYYY-MM-DD (window Nd, M+ business days silent)

## High (N)
| Sent | Days silent | Recipient | Subject | Thread |
- <Subject>: what the user asked for, and the suggested next step (nudge, different contact, or let it go)

## Medium (N)
| ... |

## Low (N)
| ... |

Older than 30 days: N threads (not ranked)
```

With `--drafts`, add a short suggested nudge under each high-priority thread: direct but not pushy, restate the ask in one line, and make it easy to answer. Write in the user's voice from the vault's voice file if available. Show drafts in the report only; create mail drafts only if the user asks after reviewing them.

Keep the report short and bias toward threads where silence actually costs something. Report what the mail tools returned; if a thread could not be read, say so rather than guessing its state.
