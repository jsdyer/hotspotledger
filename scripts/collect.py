#!/usr/bin/env python3
from source import collect
if __name__ == '__main__':
    try: collect()
    except (OSError,ValueError,RuntimeError) as exc: raise SystemExit(str(exc)) from None
