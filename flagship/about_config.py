"""Fixed content for Help > About Flagship."""

from __future__ import annotations

from pathlib import Path

from . import APP_NAME as _APP_NAME
from . import __version__

_ICON_DIR = Path(__file__).resolve().parent / 'icons'
LOGO_FILE = _ICON_DIR / 'flagship.png'
LOGO_SVG = _ICON_DIR / 'flagship.svg'

APP_NAME = _APP_NAME
VERSION = __version__
TAGLINE = 'Native XAPI desktop client for Rocky Linux 9 and 10'
TOOLSET = (
    'Part of the Anderson Computer cyber chief toolset, '
    'together with Skiff, Sonar and Porthole.'
)
AUTHOR = 'Mike Anderson'
COPYRIGHT = 'Copyright (c) 2026 Mike Anderson'
LINKS = [
    ('Project page', 'https://github.com/mike0615/flagship'),
    ('www.andersoncomputer.net', 'https://www.andersoncomputer.net'),
]
CREDITS = (
    'Inspired by XCP-ng Center. Flagship is an independent project and is '
    'not an official XCP-ng or XenServer product. Original XCP-ng Center '
    'notices are preserved in upstream/LICENSE.xcp-ng.'
)
LICENSE_NOTICE = (
    'Flagship is free software, released under the BSD 2-Clause License. '
    'Redistribution and use in source and binary forms, with or without '
    'modification, are permitted provided the copyright notice and this '
    'permission notice are retained.\n\n'
    'Flagship is provided "as is", without warranty of any kind, express '
    'or implied, including but not limited to the implied warranties of '
    'merchantability and fitness for a particular purpose. See the BSD '
    '2-Clause License for more details.'
)
