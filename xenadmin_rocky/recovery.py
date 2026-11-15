"""Compatibility entry point. Prefer `flagship` or `flagship-recovery`."""
from flagship.recovery import *  # noqa: F403
from flagship.recovery import main

if __name__ == '__main__':
    raise SystemExit(main())
