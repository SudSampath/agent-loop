# Working on native desktop optimization

Read the repository instructions, docs/design.md, and this directory's README.md, DESIGN.md, and HANDOFF.md before editing. This standalone experimental component requires Python 3.11+; preserve the portable harness core and its platform requirements.

Use Python standard library only. Behavior checks use observable Given/When/Then docstrings. Run this directory's `python3 -m unittest discover -s tests -v` and the repository's root checks. Tests must use temporary config/state homes and synthetic fixtures. Do not launch paid inference or mutate live routing, hooks, trust, startup services, or existing Orca integration during automated tests.

Keep authentication stores, credentials, live client configuration, vault content, personal machine evidence, and private planning records outside this public repository. The native routing adapter is opt-in and separate from bootstrap installation. Preserve the guard and attestation on mock inference probes. Separate native transport proof, optimization attribution, and boot proof; record unsupported/cloud boundaries accurately.
