"""``altitude site build`` — export the public website as static HTML."""

from __future__ import annotations

import argparse


def _cmd_build(args: argparse.Namespace) -> int:
    from .build import build_site

    files = build_site(args.out, theme=args.theme)
    print(f"wrote {len(files)} files to {args.out} (open {args.out}/index.html)")
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("site", help="public website: build a static export")
    s = p.add_subparsers(dest="site_cmd", required=True)
    b = s.add_parser("build", help="compute live samples from the synthetic estate and write the static site")
    b.add_argument("--out", default="out/site")
    b.add_argument("--theme", default=None, help="theme tokens to use (default: ALTITUDE_THEME or 'default')")
    b.set_defaults(func=_cmd_build)
