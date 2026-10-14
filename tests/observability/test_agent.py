"""Ask-the-platform agent: golden questions answered with citations; ungrounded questions refused."""

from datetime import date

import pytest

from altitude.core.ai import requires_review
from altitude.core.store import Store
from altitude.observability.agent import AskThePlatform
from altitude.observability.config import kpi_index, load_golden

GOLDEN = load_golden()
ANSWERABLE = [g for g in GOLDEN if not g["expected"].get("refuse")]
REFUSALS = [g for g in GOLDEN if g["expected"].get("refuse")]


@pytest.fixture(scope="module")
def agent(obs_seeded):
    return AskThePlatform(obs_seeded, store=Store())


def _expected_value(db, kpi_id, start, end, dims):
    k = kpi_index()[kpi_id]
    where, params = ["KPI_ID = ?", "PERIOD BETWEEN ? AND ?", "VALUE IS NOT NULL"], [kpi_id, start, end]
    if dims:
        where.append(f"DIMENSION IN ({', '.join('?' for _ in dims)})")
        params += dims
    rows = db.query(f"SELECT PERIOD, DIMENSION, VALUE FROM SEMANTIC.KPI_VALUES WHERE {' AND '.join(where)}", params)
    vals = [r["VALUE"] for r in rows]
    if k["aggregation"] == "sum":
        return sum(vals)
    if k["aggregation"] == "latest":
        last = max(r["PERIOD"] for r in rows)
        latest = [r["VALUE"] for r in rows if r["PERIOD"] == last]
        return sum(latest) / len(latest)
    return sum(vals) / len(vals)


@pytest.mark.parametrize("g", ANSWERABLE, ids=[g["id"] for g in ANSWERABLE])
def test_golden_question_is_answered_with_citations(agent, obs_seeded, g):
    exp = g["expected"]
    ans = agent.ask(g["question"])
    assert ans.answered, ans.text
    assert ans.kpi_id == exp["kpi_id"]
    assert ans.value is not None
    for s in exp.get("answer_contains", []):
        assert s in ans.text, (s, ans.text)
    if "dimension" in exp:
        assert ans.dimension == exp["dimension"]
    start, end = (date.fromisoformat(x) for x in ans.window)
    if "window_days" in exp:
        assert (end - start).days + 1 == exp["window_days"]
    # citations: the KPI, its certified definition, the KPI rows used and the RAW sources behind them
    (cit,) = ans.citations
    assert cit["kpi_id"] == exp["kpi_id"] and cit["kpi_table"].startswith("KPI.")
    assert cit["definition_hash"] and cit["rows"] and cit["rows_total"] >= len(cit["rows"])
    assert all(start.isoformat() <= r["period"] <= end.isoformat() for r in cit["rows"])
    assert cit["source_tables"] and any(s["rows_in_window"] > 0 for s in cit["source_tables"])
    assert all(s["table"].startswith("RAW.") for s in cit["source_tables"])
    assert exp["kpi_id"] in ans.text
    # the answer is grounded: it equals the KPI aggregated over the cited window
    if exp.get("ranking"):
        assert ans.ranking and ans.value == ans.ranking[0]["value"]
        assert [r["value"] for r in ans.ranking] == sorted((r["value"] for r in ans.ranking), reverse=True)
    else:
        dims = [ans.dimension] if ans.dimension else None
        assert ans.value == pytest.approx(_expected_value(obs_seeded, exp["kpi_id"], start, end, dims))
    assert 0 < ans.confidence <= 1 and exp["kpi_id"] in ans.rationale


@pytest.mark.parametrize("g", REFUSALS, ids=[g["id"] for g in REFUSALS])
def test_ungrounded_questions_are_refused(agent, g):
    ans = agent.ask(g["question"])
    assert not ans.answered and ans.refusal_reason
    assert ans.value is None and ans.citations == []
    assert "can't answer" in ans.text


def test_every_answer_and_refusal_is_recorded_as_an_inference(obs_seeded):
    store = Store()
    a = AskThePlatform(obs_seeded, store=store)
    ok = a.ask("How many credits did WH_DS use in the last 7 days?")
    no = a.ask("What will the weather be in Paris tomorrow?")
    rows = {r["inference_id"]: r for r in store.query("SELECT * FROM ai_inference")}
    assert set(rows) == {ok.inference_id, no.inference_id}
    for r in rows.values():
        assert r["rationale"] and r["confidence"] is not None and r["prompt_template"].startswith("obs.ask")
        assert r["provider"] == "template"
    assert rows[no.inference_id]["kind"] == "refusal"
    # a zero-confidence refusal is queued for human review; a grounded answer above the bar is not
    queued = {i["subject_id"] for i in store.query("SELECT subject_id FROM review_item WHERE status = 'open'")}
    assert rows[no.inference_id]["subject_id"] in queued
    assert requires_review(no.confidence)


def test_account_and_dimension_filters(obs_seeded):
    a = AskThePlatform(obs_seeded)
    all_wh = a.ask("How many credits were used in the last 7 days?")
    one = a.ask("How many credits did WH_ELT_PROD use in the last 7 days?")
    assert one.dimension == "WH_ELT_PROD" and 0 < one.value < all_wh.value
    other = a.ask("How many credits did WH_DS use in the last 7 days?", account="NOT_AN_ACCOUNT")
    assert not other.answered and "no values" in other.refusal_reason
