"""CLI. From the repo root:

    python3 -m services.studio [--port 8765] [--host 127.0.0.1] [--allow-non-loopback] [--verbose]

`python3 services/studio/__main__.py` works too. STUDIO_ENGINE=fake (default) or module:factory picks the engine.
Exit 2 when the engine cannot be loaded or the address cannot be bound.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make the package importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "services.studio"

try:
    from .engine import EngineUnavailable, load_engine  # noqa: E402
    from .server import DEFAULT_PORT, StudioConfigError, make_server  # noqa: E402
except ImportError as _exc:  # a missing dependency: say which, no traceback
    print(f"studio: cannot start: missing module '{_exc.name}' "
          "(install with: pip install -r services/blueprint/requirements.txt)", file=sys.stderr)
    sys.exit(2)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m services.studio", description="Local Studio: the platform end to end, live.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--allow-non-loopback", action="store_true", help="allow binding an address other than loopback")
    ap.add_argument("--verbose", action="store_true", help="log request paths (never bodies) to stderr")
    args = ap.parse_args(argv)
    try:
        engine = load_engine()
    except EngineUnavailable as exc:
        print(f"studio: cannot start: {exc}", file=sys.stderr)
        return 2
    try:
        srv = make_server(args.host, args.port, args.allow_non_loopback, engine, quiet=not args.verbose)
    except StudioConfigError as exc:
        print(f"studio: cannot start: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"studio: cannot bind {args.host}:{args.port} ({type(exc).__name__})", file=sys.stderr)
        return 2
    host, port = srv.server_address[:2]
    shown = f"[{host}]" if ":" in host else host
    print(f"Studio running at http://{shown}:{port}/ (engine: {engine.kind}). Press Ctrl+C to stop.", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
