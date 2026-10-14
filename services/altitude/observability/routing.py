"""Alert routing: payload builders for Slack, Microsoft Teams, PagerDuty and ServiceNow, written to an outbox.

No network calls are made here: a delivery worker (or Snowflake notification integration) ships outbox files.
Payloads follow each target's public message format (Slack Block Kit, Teams MessageCard, PagerDuty Events v2,
ServiceNow Table API incident record).
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from altitude.core.ids import stable_id
from altitude.core.rubric import RubricSet, default_rubrics

from .config import load_alerts, resolve_route

TEST_INTERVAL_REF = "rubric.obs.routing.test_interval_days"


def _text(event: dict) -> str:
    return (f"[{event['SEVERITY'].upper()}] {event['ALERT_NAME']} — {event['ACCOUNT_NAME']}"
            f"{' / ' + event['DIMENSION'] if event.get('DIMENSION') else ''} ({event['EVALUATED_FOR']})")


def slack_payload(event: dict, route: dict, severities: dict) -> dict:
    prefix = severities.get(event["SEVERITY"], {}).get("slack_prefix", "")
    return {
        "channel": route.get("target"),
        "text": f"{prefix} {_text(event)}".strip(),
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": event["ALERT_NAME"][:150]}},
            {"type": "section", "text": {"type": "mrkdwn", "text": event["MESSAGE"]}},
            {"type": "context", "elements": [
                {"type": "mrkdwn", "text": f"*Runbook:* {event['RUNBOOK']}  *Owner:* {event['OWNER_ROLE']}  "
                                           f"*Alert:* {event['ALERT_ID']}  *Event:* {event['EVENT_ID']}"}]},
        ],
    }


def teams_payload(event: dict, route: dict, severities: dict) -> dict:
    return {
        "@type": "MessageCard", "@context": "https://schema.org/extensions",
        "summary": _text(event), "title": event["ALERT_NAME"],
        "sections": [{"activityTitle": _text(event), "text": event["MESSAGE"],
                      "facts": [{"name": "Severity", "value": event["SEVERITY"]},
                                {"name": "Runbook", "value": event["RUNBOOK"]},
                                {"name": "Owner", "value": event["OWNER_ROLE"]},
                                {"name": "Event", "value": event["EVENT_ID"]}]}],
        "channel": route.get("target"),
    }


def pagerduty_payload(event: dict, route: dict, severities: dict) -> dict:
    return {
        "routing_key_ref": route.get("routing_key_ref"),
        "event_action": "trigger",
        "dedup_key": f"{event['ALERT_ID']}:{event['ACCOUNT_NAME']}:{event.get('DIMENSION') or ''}",
        "payload": {
            "summary": _text(event)[:1024],
            "source": event["ACCOUNT_NAME"],
            "severity": severities.get(event["SEVERITY"], {}).get("pagerduty", "warning"),
            "component": event.get("DIMENSION") or event["ACCOUNT_NAME"],
            "class": event["ALERT_CLASS"],
            "custom_details": {"message": event["MESSAGE"], "runbook": event["RUNBOOK"], "owner": event["OWNER_ROLE"],
                               "event_id": event["EVENT_ID"]},
        },
        "service": route.get("target"),
    }


def servicenow_payload(event: dict, route: dict, severities: dict) -> dict:
    sev = severities.get(event["SEVERITY"], {})
    return {
        "table": "incident",
        "instance_ref": route.get("instance_ref"),
        "record": {
            "short_description": _text(event)[:160],
            "description": f"{event['MESSAGE']}\n\nRunbook: {event['RUNBOOK']}\nEvent: {event['EVENT_ID']}",
            "impact": sev.get("servicenow_impact", 3), "urgency": sev.get("servicenow_urgency", 3),
            "assignment_group": route.get("assignment_group") or route.get("target"),
            "category": "Data Platform", "subcategory": event["ALERT_CLASS"],
            "correlation_id": event["EVENT_ID"],
        },
    }


BUILDERS = {"slack": slack_payload, "teams": teams_payload, "pagerduty": pagerduty_payload,
            "servicenow": servicenow_payload}


def build_payload(event: dict, route: dict, severities: dict | None = None) -> dict:
    severities = severities if severities is not None else load_alerts().get("severities", {})
    channel = route.get("channel")
    if channel not in BUILDERS:
        raise ValueError(f"unsupported alert channel {channel!r}")
    return BUILDERS[channel](event, route, severities)


def write_outbox(outbox: str | Path, channel: str, event_id: str, payload: dict) -> str:
    path = Path(outbox) / channel / f"{event_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    return str(path)


# --------------------------------------------------------------------------- monthly routing test


def routing_test(db, registry: dict, outbox: str | Path, tested_for: date) -> list[dict]:
    """Send a test payload down every route referenced by the alert catalogue; record results in OPS.ROUTING_TEST."""
    cat = load_alerts()
    severities = cat.get("severities", {})
    results = []
    for route_ref in sorted({a["route_ref"] for a in cat["alerts"]}):
        test_id = stable_id("RTT", route_ref, tested_for.isoformat())
        rec = {"TEST_ID": test_id, "TESTED_FOR": tested_for, "ROUTE": route_ref, "CHANNEL": None, "OK": False,
               "DETAIL": None, "OUTBOX_PATH": None}
        try:
            name, route = resolve_route(registry, route_ref)
            event = {"EVENT_ID": test_id, "ALERT_ID": "ROUTING-TEST", "ALERT_CLASS": "routing_test",
                     "ALERT_NAME": "Routing test", "SEVERITY": "low", "ACCOUNT_NAME": registry.get("tenant_id", ""),
                     "DIMENSION": name, "EVALUATED_FOR": tested_for.isoformat(),
                     "MESSAGE": cat.get("routing_test", {}).get("message", "Routing test"), "RUNBOOK": "-",
                     "OWNER_ROLE": "-"}
            payload = {**build_payload(event, route, severities), "test": True}
            rec.update(CHANNEL=route["channel"], OK=True, DETAIL=f"route {name} -> {route.get('target')}",
                       OUTBOX_PATH=write_outbox(outbox, route["channel"], test_id, payload))
        except (KeyError, ValueError) as e:
            rec["DETAIL"] = str(e)
        results.append(rec)
    if not db.query("SELECT 1 FROM OPS.ROUTING_TEST WHERE TESTED_FOR = ?", [tested_for]):
        db.append_ops("ROUTING_TEST", results)
    return results


def routing_test_due(db, today: date, rubrics: RubricSet | None = None) -> bool:
    rubrics = rubrics or default_rubrics()
    last = db.scalar("SELECT max(TESTED_FOR) FROM OPS.ROUTING_TEST WHERE OK")
    if last is None:
        return True
    if isinstance(last, datetime):
        last = last.date()
    return (today - last).days >= int(rubrics.get(TEST_INTERVAL_REF))

