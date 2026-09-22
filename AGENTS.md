# Working on this harness

Read README.md and docs/design.md before editing. Preserve existing user configuration and Orca hooks. Use Python standard library only; support macOS, Linux, and Windows through WSL2. Never add credentials, vault contents, or live client configurations.

Behavior checks use Given/When/Then docstrings. Run `python3 -m unittest discover -s tests -v`. Test installations in temporary directories, never against the developer's real agent homes. Do not launch paid agent sessions in automated tests.
