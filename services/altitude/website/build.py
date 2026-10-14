"""Render the public website.

Content comes from data: the service catalogue (``knowledge/commercial/catalog.yaml``), the site copy
(``knowledge/website/site.yaml``), rubric guardrails and the live samples computed from the synthetic estate
(:mod:`altitude.website.samples`). Names and colours come from theme tokens, so a partner edition re-brands the
site by configuration. ``render_site`` returns ``{relative path: content}``; ``build_site`` writes a static site.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from altitude.core.knowledge import load_yaml
from altitude.core.rubric import default_rubrics
from altitude.core.theme import render as render_tokens
from altitude.core.theme import tokens

TEMPLATES = Path(__file__).parent / "templates"

PAGES = [
    # (file, template, nav label, title)
    ("index.html", "index.html", None, "Home"),
    ("offerings.html", "offerings.html", "Offerings", "Offerings"),
    ("package-d.html", "package_d.html", "Diagnostics", "Platform Deep Diagnostics"),
    ("package-o.html", "package_o.html", "Observability", "Platform Observability"),
    ("migration.html", "migration.html", "Migration", "Migration factory"),
    ("managed-run.html", "managed_run.html", "Managed Run", "Managed Run & agents"),
    ("ai-ready.html", "ai_ready.html", "AI-Ready", "AI-Ready programme"),
    ("marketplace.html", "marketplace.html", "Marketplace", "Data Product & Agent Marketplace"),
    ("pricing.html", "pricing.html", "Pricing", "Pricing & guarantees"),
    ("why-us.html", "why_us.html", "Why us", "Why choose us"),
    ("industries.html", "industries.html", None, "Industries"),
    ("contact.html", "contact.html", None, "Book a D0 Snapshot"),
]


def _usd(v: Any) -> str:
    return f"${float(v or 0):,.0f}"


def _usd_range(r: list) -> str:
    lo, hi = (float(x) for x in r)
    if hi == 0:
        return "Free"
    k = lambda x: f"${x / 1000:,.0f}K" if x >= 1000 else f"${x:,.0f}"  # noqa: E731  # threshold-ok: display units
    if lo >= 1_000_000 or hi >= 1_000_000:  # threshold-ok: display unit switch
        k = lambda x: f"${x / 1_000_000:,.1f}M" if x >= 1_000_000 else f"${x / 1000:,.0f}K"  # noqa: E731  # threshold-ok: display units
    return k(lo) if lo == hi else f"{k(lo)}–{k(hi)}"


def _price(o: dict) -> str:
    """Offer price: one-off fee, subscription, or both — a subscription-only offer is never shown as 'Free'."""
    fee, monthly = o.get("fee_usd") or [0, 0], o.get("monthly_usd")
    if monthly and not fee[1]:
        return f"{_usd_range(monthly)}/month"
    if monthly:
        return f"{_usd_range(fee)} + {_usd_range(monthly)}/month"
    return _usd_range(fee)


def _scrollable_tables(html: str) -> str:
    """Give every table its own horizontal scroll container so the page never scrolls sideways on phones."""
    import re

    return re.sub(r"(<table\b.*?</table>)", r'<div class="scroll">\1</div>', html, flags=re.S)


def _env(theme: str | None) -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
    env.filters["usd"] = _usd
    env.filters["usd_range"] = _usd_range
    env.filters["price"] = _price
    env.filters["pct"] = lambda v: f"{float(v or 0):.0%}"
    env.filters["label"] = lambda s: str(s).replace("_", " ")
    return env


def context(samples: dict, theme: str | None = None, live: bool = False, bare: bool = False) -> dict:
    cat = load_yaml("commercial/catalog.yaml")
    rs = default_rubrics()
    return {
        "theme": tokens(theme), "site": load_yaml("website/site.yaml"), "offers": cat["offers"],
        "offer": {o["id"]: o for o in cat["offers"]}, "tiers": cat["tiers"],
        "tier": {t["tier"]: t for t in cat["tiers"]}, "guarantees": cat["guarantees"],
        "guardrails": {"value_floor_multiple": rs.get("rubric.commercial.value_floor_multiple"),
                       "fee_credit_window_days": rs.get("rubric.commercial.fee_credit_window_days"),
                       "qualification_min_annual_spend_usd": rs.get("rubric.commercial.qualification_min_annual_spend_usd")},
        "s": samples, "nav": [(f, label) for f, _, label, _ in PAGES if label], "live": live, "bare": bare,
    }


def render_site(samples: dict, theme: str | None = None, live: bool = False,
                bare_index: bool = False) -> dict[str, str]:
    """``bare_index`` renders index.html without the document wrapper (for hosts that supply it)."""
    env = _env(theme)
    out = {}
    for file, template, _label, title in PAGES:
        ctx = context(samples, theme, live, bare=bare_index and file == "index.html")
        html = env.get_template(template).render(page=file, title=title, **ctx)
        html = _scrollable_tables(html)
        if bare_index:  # the host serves the home page at the artifact root, not as index.html
            html = html.replace('href="index.html"', 'href="./"')
        out[file] = render_tokens(html, theme)
    out["assets/site.css"] = (TEMPLATES / "site.css").read_text()
    out["samples/summary.json"] = json.dumps(samples, indent=2, sort_keys=True, default=str) + "\n"
    return out


def build_site(out_dir: str | Path, theme: str | None = None, cache_dir: str | Path | None = None,
               bare_index: bool = False) -> list[str]:
    """Compute samples and write a self-contained static site (relative links) to ``out_dir``."""
    from .samples import collect

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    samples = collect(cache_dir or out.parent / f"{out.name}_cache", out)
    files = render_site(samples, theme, bare_index=bare_index)
    for rel, content in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())
