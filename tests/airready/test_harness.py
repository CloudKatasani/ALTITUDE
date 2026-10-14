"""Golden-question evaluation harness: expected SQL/answers, scored; refusal when ungrounded."""

from altitude.airready import harness
from altitude.cli import main


def test_golden_set_is_internally_consistent_and_compiler_passes():
    report = harness.run()
    assert report.golden_integrity == []
    assert report.score == 1.0 and report.passed
    gq3 = next(r for r in report.results if r.question_id == "GQ-003")
    assert gq3.candidate["kpi"] == "KPI-ORDERS" and gq3.candidate["dimensions"] == ["segment"]
    refusal = next(r for r in report.results if r.question_id == "GQ-008")
    assert refusal.passed and refusal.candidate["refuse"]


def test_longest_kpi_phrase_wins():
    c = harness.SemanticCompiler()
    assert c.compile("average order value by region").kpi_id == "KPI-AOV"     # not 'order value' (Bookings)
    assert c.compile("total gross revenue").kpi_id == "KPI-GROSS-REVENUE"     # not 'revenue'
    assert c.compile("what's our favourite colour") is None


def test_wrong_definition_fails_the_harness():
    compiler = harness.SemanticCompiler()

    def gross_for_everything(question):
        ans = compiler(question)
        if ans.get("sql"):
            ans = {**ans, "sql": ans["sql"].replace("NET_AMOUNT", "GROSS_AMOUNT")}
        return ans

    report = harness.run(gross_for_everything)
    failed = {r.question_id for r in report.results if not r.passed}
    assert {"GQ-001", "GQ-005", "GQ-006"} <= failed and not report.passed


def test_answering_out_of_scope_or_broken_sql_fails():
    report = harness.run(lambda q: {"sql": "SELECT 1"} if "weather" in q else {"sql": "SELECT * FROM NOPE"})
    assert report.score == 0.0
    assert any("out-of-scope" in r.reason for r in report.results)
    assert any("SQL failed" in r.reason for r in report.results)


def test_golden_integrity_detects_wrong_expected_answers():
    golden = harness.load_golden()
    golden["questions"][0]["expected"]["answer"] = [["EAST", 1.0]]
    report = harness.run(golden=golden)
    assert report.golden_integrity and not report.passed


def test_cli_eval(capsys):
    assert main(["airready", "eval"]) == 0
    assert "eval score 1.0" in capsys.readouterr().out
