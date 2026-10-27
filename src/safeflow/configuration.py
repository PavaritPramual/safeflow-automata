"""Local authentication configuration; secrets never enter run metadata."""
import os
from pathlib import Path


def load_key():
    key = os.environ.get('SAFEFLOW_API_KEY')
    path = Path('.env')
    if not key and path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if line.startswith('SAFEFLOW_API_KEY='):
                key = line.split('=', 1)[1].strip()
                break
    if not key or len(key) < 24:
        raise RuntimeError('Set SAFEFLOW_API_KEY (at least 24 characters); see setup guide')
    return key
