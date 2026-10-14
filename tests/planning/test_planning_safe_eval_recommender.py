from pathlib import Path

import pytest

from altitude.core.rubric import default_rubrics
from altitude.planning.recommender import evidence_inputs, recommend
from altitude.planning.safe_eval import ExpressionError, MissingInput, evaluate, evaluate_bool, variables


def test_safe_eval_semantics():
    env = {"deadline_weeks": 20, "share": 0.5, "band": "large", "nested": {"x": 3}}
    assert evaluate_bool("deadline_weeks < 26 and share > 0.4", env)
    assert not evaluate_bool("not (deadline_weeks < 26)", env)
    assert evaluate("deadline_weeks * 2 + nested.x - 1", env) == 42
    assert evaluate_bool("band in ['large', 'enterprise'] and 'medium' not in ['large']", env)
    assert evaluate_bool("-share < 0 or false", env)
    rs = default_rubrics()
    assert evaluate_bool("rubric.gates.waves.max_weeks_per_wave >= 1", {}, rs)
    assert variables("a < 1 and b.c > rubric.gates.unit_test_min") == {"a", "b.c"}
    with pytest.raises(MissingInput) as e:
        evaluate_bool("missing_input > 1", env)
    assert e.value.name == "missing_input"
    with pytest.raises(MissingInput):
        evaluate_bool("x > 1", {"x": None})


@pytest.mark.parametrize("src", [
    "__import__('os').system('echo pwned')",
    "open('/etc/passwd')",
    "deadline_weeks.__class__",
    "[x for x in range(3)]",
    "lambda: 1",
    "1; 2",
    "a = 1",
    "deadline_weeks < ",
    "'a' < 1",
    "1 / 0",
    "1 if true else 2",
    "x" * 3000,
])
def test_safe_eval_rejects_code(src):
    with pytest.raises((ExpressionError, MissingInput)):
        evaluate(src, {"deadline_weeks": 1, "x": 1})


def test_no_eval_or_exec_in_planning_code():
    root = Path(__file__).resolve().parents[2] / "services" / "altitude" / "planning"
    for f in root.glob("*.py"):
        text = f.read_text()
        assert "eval(" not in text.replace("_eval(", "").replace("evaluate(", "") and "exec(" not in text, f


def test_recommender_rules_from_spec():
    rs = default_rubrics()
    full = {"deadline_weeks": 20, "procedural_code_share": 0.5, "dead_object_share": 0.3, "model_quality_score": 70,
            "appetite_for_change": 2, "etl_tool_complexity": 0.1, "regulatory_freeze_windows": 0, "budget_band": "medium"}
    r = recommend(full, scope="programme", snapshot_id="ASM-X", rubrics=rs)
    assert r.pattern == "lift_and_shift" and r.rule_id == "deadline_procedural"
    assert r.confidence == pytest.approx(0.82) and "Deadline cannot absorb" in r.rationale
    assert {"lens": "cost", "prefers": "re_platform"}.items() <= next(d for d in r.dissent if d["lens"] == "cost").items()
    assert r.rubric_version == rs.version and r.snapshot_id == "ASM-X"
    r2 = recommend({**full, "deadline_weeks": 60, "model_quality_score": 30, "appetite_for_change": 4},
                   scope="programme", snapshot_id="ASM-X", rubrics=rs)
    assert r2.pattern == "re_architect" and r2.rule_id == "broken_model_with_appetite"
    r3 = recommend({**full, "deadline_weeks": 60}, scope="programme", snapshot_id="ASM-X", rubrics=rs)
    assert r3.pattern == "re_platform" and r3.rule_id == "default"
    # recommendation is reproducible
    assert recommend(full, scope="programme", snapshot_id="ASM-X", rubrics=rs) == r


def test_recommender_missing_inputs_reduce_confidence_and_are_not_guessed():
    rs = default_rubrics()
    r = recommend({"procedural_code_share": 0.7}, scope="w1", snapshot_id="ASM-X", rubrics=rs)
    assert r.pattern == "re_platform"  # no rule could be evaluated, so the default applies
    assert {u["rule"] for u in r.unevaluated} == {"deadline_procedural", "broken_model_with_appetite",
                                                  "complex_etl_modernise", "regulated_long_tail"}
    assert r.confidence < rs.get("rubric.pattern_recommender.default.confidence")
    assert "deadline_weeks" in r.missing_inputs and "missing inputs" in r.rationale
    assert any(d["lens"] == "value" for d in r.dissent)  # procedural share > 0.6 → value lens dissents


def test_recommender_rules_are_data():
    rs = default_rubrics()
    rules = rs.get("rubric.pattern_recommender.rules")
    changed = rs.with_overrides({"pattern_recommender": {"rules": [
        {**rules[0], "when": "deadline_weeks < 100 and procedural_code_share > 0.4"}] + rules[1:]}})
    inputs = {"deadline_weeks": 60, "procedural_code_share": 0.5}
    assert recommend(inputs, scope="p", snapshot_id="S", rubrics=rs).pattern == "re_platform"
    assert recommend(inputs, scope="p", snapshot_id="S", rubrics=changed).pattern == "lift_and_shift"


def test_evidence_inputs_from_assessment(ctx_for):
    ctx = ctx_for()
    ev = evidence_inputs(ctx, ctx.in_scope())
    assert 0 < ev["procedural_code_share"] <= 1
    assert ev["dead_object_share"] == pytest.approx(len(ctx.retired()) / len(ctx.objects), abs=0.001)
    assert ev["etl_tool_complexity"] == 0.5  # LoadProducts has a script task; LoadStaging does not
    assert ev["regulatory_freeze_windows"] > 0
    tags = ctx.tags()
    names = {ctx.name(o): t for o, t in tags.items()}
    assert "month_end" in names["SalesDW.etl.usp_MonthEndClose"] and "month_end" in names["SalesDW.rpt.vw_MonthEnd"]
    assert "regulatory" in names["SalesDW.rpt.RegulatoryFiling"]
    assert "SalesDW.etl.usp_LogLoad" not in names  # shared helper merely called is not tagged
