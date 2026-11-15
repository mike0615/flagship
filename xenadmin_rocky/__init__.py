"""Compatibility package. Flagship was called XenAdmin Rocky."""

from importlib import import_module
import sys

import flagship
from flagship import APP_NAME, __version__  # noqa: F401

__all__ = ['APP_NAME', '__version__']

_SUBMODULES = (
    'about_config', 'api', 'app', 'console', 'console_window', 'device_panel',
    'devices', 'dialogs', 'help', 'history', 'journal', 'migrate', 'protocol',
    'redaction', 'rfb', 'tasks', 'wizard', 'workflows',
)

for _name in _SUBMODULES:
    _mod = import_module(f'flagship.{_name}')
    sys.modules[f'xenadmin_rocky.{_name}'] = _mod
    globals()[_name] = _mod
