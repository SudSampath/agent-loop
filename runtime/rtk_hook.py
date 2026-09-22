"""Optional adapter based on the locally verified Codex Bash hook contract."""
import json
import shutil
import subprocess
import sys


def main():
    event = json.load(sys.stdin)
    if event.get('hook_event_name') != 'PreToolUse' or event.get('tool_name') != 'Bash':
        return
    original = event.get('tool_input', {}).get('command')
    binary = shutil.which('rtk')
    if not binary or not isinstance(original, str) or not original.strip():
        return
    result = subprocess.run([binary, 'rewrite', original], capture_output=True,
                            text=True, timeout=4, cwd=event.get('cwd') or None)
    rewritten = result.stdout.strip()
    if result.returncode in (0, 3) and rewritten and rewritten != original:
        updated = dict(event['tool_input'], command=rewritten)
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',
              'permissionDecision': 'allow', 'updatedInput': updated}}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, TypeError, AttributeError, subprocess.SubprocessError):
        pass  # Optimization failure must leave the original tool call usable.
