"""Public website at ``/`` (no sign-in). Samples are computed once per workspace from the synthetic estate."""

from __future__ import annotations

import threading
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

from altitude.core import audit

from ..app import Context

router = APIRouter()
_lock = threading.Lock()


def _site_dir(ctx: Context) -> Path:
    return Path(ctx.workspace) / "site"


def site_files(ctx: Context) -> dict[str, str]:
    """Rendered pages (cached). Sample artefacts are written to ``<workspace>/site``."""
    with _lock:
        if "site_files" not in ctx.extras:
            from altitude.website.build import render_site
            from altitude.website.samples import collect

            samples = ctx.extras.get("site_samples") or collect(Path(ctx.workspace) / "site_cache", _site_dir(ctx))
            ctx.extras["site_samples"] = samples
            ctx.extras["site_files"] = render_site(samples, live=True)
        return ctx.extras["site_files"]


def _page(request: Request, name: str) -> Response:
    files = site_files(request.app.state.ctx)
    if name not in files:
        raise HTTPException(404, "no such page")
    media = "text/css" if name.endswith(".css") else ("application/json" if name.endswith(".json") else "text/html")
    return Response(files[name], media_type=media)


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request) -> Response:
    return _page(request, "index.html")


@router.get("/{name}.html", response_class=HTMLResponse, include_in_schema=False)
def page(request: Request, name: str) -> Response:
    return _page(request, f"{name}.html")


@router.get("/assets/site.css", include_in_schema=False)
def css(request: Request) -> Response:
    return _page(request, "assets/site.css")


@router.get("/samples/{path:path}", include_in_schema=False)
def sample(request: Request, path: str):
    ctx = request.app.state.ctx
    site_files(ctx)
    if path == "summary.json":
        return _page(request, "samples/summary.json")
    base = (_site_dir(ctx) / "samples").resolve()
    target = (base / path).resolve()
    if base not in target.parents or not target.is_file():
        raise HTTPException(404, "no such sample")
    return FileResponse(target)


@router.post("/contact", response_class=HTMLResponse, include_in_schema=False)
def contact(request: Request, name: str = Form(...), email: str = Form(...), company: str = Form(...),
            spend: str = Form(""), interest: str = Form("OFF-D0"), message: str = Form("")) -> HTMLResponse:
    """Inbound request: recorded as a go-to-market buying signal (and audited); no email is sent from here."""
    from altitude.gtm import record_signal
    from altitude.website.build import _env, context

    ctx: Context = request.app.state.ctx
    if "@" not in email or len(name) > 200 or len(company) > 200 or len(message) > 5000:  # threshold-ok: input limits
        raise HTTPException(422, "please check the form")
    detail = f"{interest} | {spend} | {name} <{email}> | {message[:500]}"
    sid = record_signal(ctx.store, company.strip(), "inbound_request", date.today(), "website", detail)
    audit.record(ctx.store, email, "website.contact", actor_type="human", subject_type="gtm_signal", subject_id=sid)
    files = site_files(ctx)  # ensures samples exist for the layout footer
    del files
    from altitude.core.theme import render as render_tokens

    html = _env(None).get_template("thanks.html").render(page="contact.html", title="Thank you", name=name.split()[0],
                                                         **context(ctx.extras["site_samples"], live=True))
    return HTMLResponse(render_tokens(html))
