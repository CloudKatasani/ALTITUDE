"""``altitude serve`` — run the API and portal."""

from __future__ import annotations

import argparse


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .app import create_app

    uvicorn.run(create_app(workspace=args.workspace), host=args.host, port=args.port)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("serve", help="run the REST API and portal")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--workspace", default=".altitude")
    p.set_defaults(func=_cmd_serve)
