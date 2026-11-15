"""First-run migration from XenAdmin Rocky (the name before Flagship).

If ~/.local/state/flagship does not exist yet but ~/.local/state/xenadmin-rocky
does, its files (operation journals) are COPIED to the new location. The same
is done for ~/.config/xenadmin-rocky if that directory is present. Nothing in
the old locations is changed or removed.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Optional

APP_NAME = 'flagship'
LEGACY_NAME = 'xenadmin-rocky'
MARKER = 'MIGRATED-FROM-xenadmin-rocky.txt'


def _config_base() -> Path:
    base = os.environ.get('XDG_CONFIG_HOME', '')
    return Path(base) if base and Path(base).is_absolute() else Path.home() / '.config'


def _state_base() -> Path:
    base = os.environ.get('XDG_STATE_HOME', '')
    return Path(base) if base and Path(base).is_absolute() else Path.home() / '.local/state'


def journal_dir() -> Path:
    return _state_base() / APP_NAME / 'journals'


def legacy_journal_dir() -> Path:
    return _state_base() / LEGACY_NAME / 'journals'


def _copy_tree(src: Path, dst: Path) -> int:
    """Copy regular files only (no sockets/symlinks), 0700 dirs. Returns count."""
    tmp = dst.parent / f'.{dst.name}.migrating-{os.getpid()}'
    shutil.rmtree(tmp, ignore_errors=True)
    n = 0
    try:
        for root, dirs, files in os.walk(src, followlinks=False):
            rel = Path(root).relative_to(src)
            (tmp / rel).mkdir(mode=0o700, parents=True, exist_ok=True)
            for name in files:
                sp = Path(root) / name
                if sp.is_file() and not sp.is_symlink():
                    shutil.copy2(sp, tmp / rel / name)
                    os.chmod(tmp / rel / name, 0o600)
                    n += 1
        os.chmod(tmp, 0o700)
        dst.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.replace(tmp, dst)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return n


def migrate_legacy() -> Optional[str]:
    """Run once. Returns a short status message if anything was copied."""
    new_state = _state_base() / APP_NAME
    old_state = _state_base() / LEGACY_NAME
    new_cfg = _config_base() / APP_NAME
    old_cfg = _config_base() / LEGACY_NAME
    if new_state.exists() or new_cfg.exists():
        return None
    if not old_state.is_dir() and not old_cfg.is_dir():
        return None
    copied = 0
    sources = []
    try:
        if old_state.is_dir() and not new_state.exists():
            copied += _copy_tree(old_state, new_state)
            sources.append(str(old_state))
        if old_cfg.is_dir() and not new_cfg.exists():
            copied += _copy_tree(old_cfg, new_cfg)
            sources.append(str(old_cfg))
        marker_parent = new_state if new_state.is_dir() else new_cfg
        marker_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        (marker_parent / MARKER).write_text(
            f'Copied from {", ".join(sources)} on {time.strftime("%Y-%m-%d %H:%M:%S %Z")} by Flagship.\n'
            f'The original files were left unchanged.\n',
            encoding='utf-8',
        )
        os.chmod(marker_parent / MARKER, 0o600)
    except (OSError, ValueError) as exc:
        origin = old_state if old_state.is_dir() else old_cfg
        return f'Could not copy XenAdmin Rocky data from {origin}: {exc}'
    return f'Imported {copied} file(s) from XenAdmin Rocky ({", ".join(sources)}); originals kept.'
