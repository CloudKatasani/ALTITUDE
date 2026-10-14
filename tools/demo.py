#!/usr/bin/env python3
"""End-to-end demo: start the API + portal, run the flagship flow through the REST API, capture the portal.

    make demo                       # writes out/demo/{demo_log.json, screenshots/*.png, ws/...}
    python tools/demo.py OUT_DIR [--port 8099] [--keep-running]

Uses the synthetic "Acme Utilities" estate (seeded issues), so it needs no Snowflake account. Screenshots are
taken when Playwright is installed (``pip install -e '.[demo]'``); the browser comes from
``ALTITUDE_DEMO_BROWSER``, the pre-installed ``/opt/pw-browsers/chromium`` if present, or Playwright's default.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
LEAD = {"X-Altitude-User": "lead@acme.example", "X-Altitude-Role": "delivery_lead"}
EXEC = {"X-Altitude-User": "cio@acme.example", "X-Altitude-Role": "exec"}
ENGAGEMENT_FACTS = {  # what the delivery team told us; Sherpa challenges the plan from these
    "pattern": "lift_and_shift", "procedural_object_count": 4200, "test_harness": False,
    "dead_object_share": 0.42, "pruning_done": False, "deadline_weeks": 20,
}


def wait_healthy(client: httpx.Client, proc: subprocess.Popen) -> None:
    for _ in range(120):
        if proc.poll() is not None:
            raise SystemExit(f"server exited with {proc.returncode}; see server.log")
        try:
            if client.get("/api/v1/health").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise SystemExit("server did not become healthy")


def run_flow(c: httpx.Client) -> tuple[list, dict]:
    log: list = []

    def step(name: str, resp: httpx.Response) -> dict:
        if resp.status_code >= 400:
            raise SystemExit(f"{name} failed: HTTP {resp.status_code} {resp.text[:500]}")
        out = resp.json()
        log.append((name, out))
        print(f"  ✓ {name}")
        return out

    eng = step("create engagement", c.post("/api/v1/engagements", json={
        "tenant": "Acme", "client": "Acme Utilities", "package": "D2", "name": "Acme Utilities — Package D + O",
        "industry": "utilities"}))
    step("record engagement facts", c.put(f"/api/v1/engagements/{eng['engagement_id']}/facts",
                                          json={"facts": ENGAGEMENT_FACTS}))
    snap = step("seal synthetic estate snapshot", c.post("/api/v1/skills/build_synthetic_snapshot",
                                                         json={"profile": "seeded", "days": 90}))
    run = step("Package D run", c.post("/api/v1/diagnostics/runs", json={
        "snapshot_id": snap["snapshot_id"], "tier": "D2", "engagement_id": eng["engagement_id"]}))
    sugg = c.get("/api/v1/diagnostics/suggestions").json()
    picks = [s for s in sugg if s["quadrant"] == "quick_win" and not s["needs_review"]][:3]
    for s in picks:
        step(f"accept {s['suggestion_id']}", c.post(f"/api/v1/diagnostics/suggestions/{s['suggestion_id']}/transition",
                                                    json={"to_status": "accepted", "comment": "validated in workshop"}))
    step("implement first quick win", c.post(f"/api/v1/diagnostics/suggestions/{picks[0]['suggestion_id']}/transition",
                                             json={"to_status": "implemented", "comment": "applied via remediation pack"}))
    for item in c.get("/api/v1/review-queue").json()[:2]:
        step(f"review {item['item_id']}", c.post(f"/api/v1/review-queue/{item['item_id']}/decision",
                                                 json={"decision": "approved"}))
    step("ask Sherpa", c.post("/api/v1/sherpa/ask", json={
        "question": "Which warehouses are idle-heavy and what will auto-suspend save?", "facts": ENGAGEMENT_FACTS}))
    step("Architecture Review Board", c.post("/api/v1/review-board", json={
        "title": "Wave 1: re-platform Finance on Snowflake",
        "facts": {"pattern": "re_platform", "modernise_backlog": True, "annual_value_usd": 900000,
                  "annual_cost_usd": 350000, "estimate_p80_weeks": 14, "deadline_weeks": 16,
                  "unmasked_classified_columns": 1},
        "evidence_refs": [run["run_id"]], "engagement_id": eng["engagement_id"]}))
    step("Package O harvest + KPIs", c.post("/api/v1/observability/harvest", json={"as_of": "2026-09-30", "days": 45}))
    step("evaluate alerts", c.post("/api/v1/observability/alerts/evaluate", json={}))
    step("render dashboards", c.post("/api/v1/observability/dashboards"))
    step("ask the platform", c.post("/api/v1/observability/ask",
                                    json={"question": "What is the idle credit share by warehouse?"}))
    for agent in ("AG-WAREHOUSE-RIGHTSIZER", "AG-ACCESS-HYGIENE", "AG-COST-SENTINEL"):
        step(f"evals + promote {agent}", c.post(f"/api/v1/agents/{agent}/evals?promote=true"))
        step(f"run {agent}", c.post(f"/api/v1/agents/{agent}/runs", json={"snapshot_id": snap["snapshot_id"]}))
    step("board pack", c.post("/api/v1/skills/generate_board_pack", json={"snapshot_id": snap["snapshot_id"]}))
    step("gate: move to Fix", c.post(f"/api/v1/engagements/{eng['engagement_id']}/phase", headers=EXEC,
                                     json={"phase": "fix"}))
    return log, {"snapshot_id": snap["snapshot_id"], "suggestion_id": picks[0]["suggestion_id"]}


def screenshots(base: str, ws: Path, out: Path, ids: dict) -> list[str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  (playwright not installed: pip install -e '.[demo]' for screenshots)")
        return []
    exe = os.environ.get("ALTITUDE_DEMO_BROWSER") or ("/opt/pw-browsers/chromium"
                                                      if Path("/opt/pw-browsers/chromium").exists() else None)
    out.mkdir(parents=True, exist_ok=True)
    pages = [("01_outcome_path", "/"), ("02_findings", "/findings"),
             ("03_suggestion", f"/suggestion?id={ids['suggestion_id']}"), ("04_progress", "/progress"),
             ("05_sherpa", "/sherpa?q=Which+warehouses+are+idle-heavy%3F"), ("06_review_queue", "/review"),
             ("07_review_board", "/decisions"), ("08_agents", "/agents"), ("09_observability", "/dashboards")]
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(base + "/login")
        page.fill("input[name=user]", "lead@acme.example")
        page.select_option("select[name=role]", "delivery_lead")
        page.click("button[type=submit]")
        for name, url in pages:
            page.goto(base + url)
            page.screenshot(path=str(out / f"{name}.png"), full_page=True)
        dash_dir = ws / "dashboards"
        for i, name in enumerate(("executive_cost_value", "platform_health", "pipelines_freshness")):
            f = next(dash_dir.rglob(f"{name}.html"), None)
            if f:
                page.goto(base + "/dashboards/files/" + str(f.relative_to(dash_dir)))
                page.screenshot(path=str(out / f"1{i}_{name}.png"), full_page=True)
        board = next((ws / "board_pack").rglob("board_dashboard.html"), None)
        if board:
            page.goto(board.as_uri())
            page.screenshot(path=str(out / "20_board_dashboard.png"), full_page=True)
        browser.close()
    return sorted(p.name for p in out.iterdir())


def summary(log: list) -> None:
    d = dict(log)
    run = d["Package D run"]
    print(f"\nPackage D: {run['suggestions']} suggestions, Platform Health Index {run['platform_health_index']}")
    s = d["ask Sherpa"]
    print(f"Sherpa: grounded={s['grounded']} cites {', '.join(s['citations'])}; "
          f"challenges {', '.join(c['id'] for c in s['challenges']) or 'none'}")
    b = d["Architecture Review Board"]
    print(f"Review board: {b['recommendation']} ({b['support_share']:.0%} weighted support)")
    print(f"Ask the platform: {d['ask the platform']['text']}")
    for k in ("run AG-WAREHOUSE-RIGHTSIZER", "run AG-ACCESS-HYGIENE", "run AG-COST-SENTINEL"):
        print(f"{k[4:]}: {d[k]['summary']}")
    print(f"Board pack numbers hash: {d['board pack']['numbers_hash']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", nargs="?", default=str(ROOT / "out" / "demo"))
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--keep-running", action="store_true", help="leave the server up after the demo")
    args = ap.parse_args(argv)
    out = Path(args.out).resolve()
    ws = out / "ws"
    if ws.exists():
        import shutil

        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    env = dict(os.environ, ALTITUDE_AUTH="dev", ALTITUDE_WORKSPACE=str(ws))
    altitude = Path(sys.executable).with_name("altitude")
    cmd = [str(altitude)] if altitude.exists() else [sys.executable, "-m", "altitude.cli"]
    proc = subprocess.Popen(cmd + ["serve", "--port", str(args.port), "--workspace", str(ws)], env=env, cwd=ROOT,
                            stdout=open(out / "server.log", "w"), stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{args.port}"
    try:
        with httpx.Client(base_url=base, headers=LEAD, timeout=900) as c:
            wait_healthy(c, proc)
            print(f"Server up at {base} (workspace {ws})")
            log, ids = run_flow(c)
        (out / "demo_log.json").write_text(json.dumps(log, indent=2, default=str))
        summary(log)
        shots = screenshots(base, ws, out / "screenshots", ids)
        if shots:
            print(f"\nScreenshots in {out / 'screenshots'}: {', '.join(shots)}")
        if args.keep_running:
            print(f"\nPortal running at {base} — sign in with any user and a role. Ctrl-C to stop.")
            proc.wait()
    finally:
        if proc.poll() is None:
            proc.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
