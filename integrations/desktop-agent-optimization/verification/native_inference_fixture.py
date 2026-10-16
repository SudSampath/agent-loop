"""Emit compressible synthetic tool output for the native Headroom proof."""

import json


def fixture():
    return {'fixture': 'desktop-headroom-v1', 'records': [
        {'id': index, 'status': 'ok', 'marker': f'KEEP-{index:03d}-FIDELITY',
         'detail': ('Synthetic operation completed successfully; no private data. ' * 6).strip()}
        for index in range(120)
    ]}


if __name__ == '__main__':
    print(json.dumps(fixture(), indent=2))
