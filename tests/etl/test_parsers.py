from altitude.etl.classify import assess
from altitude.etl.loader import detect

from .conftest import CONTROLM, DTSX, POWERCENTER, SQLAGENT, graph


def test_detect_formats():
    assert [detect(p) for p in (DTSX, POWERCENTER, CONTROLM, SQLAGENT)] == ["ssis", "informatica", "controlm", "sqlagent"]


def test_ssis_package_structure(ssis_pkg):
    assert ssis_pkg.package == "LoadSalesMart"
    assert ssis_pkg.var_types == {"load_date": "timestamp", "rows_loaded": "number"}
    assert [g.job.split("::")[1] for g in ssis_pkg.graphs] == [
        "DFT Load DimProduct", "DFT Load FactSales", "DFT Aggregate SalesByCategory"]
    fact = graph(ssis_pkg, "DFT Load FactSales")
    kinds = {n.id: n.kind for n in fact.nodes.values()}
    assert kinds == {"src_sales_order_detail": "source", "src_sales_order_detail_archive": "source",
                     "uni_all_orders": "union", "lkp_dim_product": "lookup", "der_line_total": "project",
                     "cspl_returns": "split", "dst_fact_sales": "target", "dst_fact_returns": "target"}
    src = fact.nodes["src_sales_order_detail"].props
    assert src["table"] == "sales_order_detail" and src["system"] == "src_erp" and "sql_override" not in src
    assert fact.nodes["src_sales_order_detail_archive"].props["table"] == "archive_sales_order_detail"
    lkp = fact.nodes["lkp_dim_product"].props
    assert lkp["keys"] == [("product_key", "product_id")] and lkp["returns"] == [("product_category", "category")]
    assert lkp["join"] == "inner"  # no-match rows are not routed anywhere
    split = fact.nodes["cspl_returns"].props
    assert split["semantics"] == "first_match" and split["default_group"] == "Sales"
    assert [g for g, _ in split["groups"]] == ["Returns", "Zero Quantity"]
    sales_edge = next(e for e in fact.edges if e.dst == "dst_fact_sales")
    assert sales_edge.src_port == "Sales" and ("product_id", "product_key") in sales_edge.fields
    dim = graph(ssis_pkg, "DFT Load DimProduct")
    outs = {o.name: o for o in dim.nodes["der_clean_product"].props["outputs"]}
    assert outs["product_name"].sql == "COALESCE(UPPER(TRIM(product_name)), 'UNNAMED')"  # readWrite replacement
    assert outs["price_band"].literal_values == ["PREMIUM", "STANDARD", "BUDGET"]
    assert {i.id for i in fact.issues} >= {"ETL-SSIS-03", "ETL-SSIS-04", "ETL-SSIS-05"}


def test_ssis_control_flow(ssis_pkg):
    tasks = {t.name: t for t in ssis_pkg.control_tasks}
    assert tasks["SQL Truncate FactSales"].recommendation_hint == "retire"
    assert tasks["SQL Log Start"].converted_sql.startswith("INSERT INTO dbo.EtlRunLog")
    assert "GETDATE" not in tasks["SQL Log Start"].converted_sql
    assert [i.id for i in tasks["SCR Notify Finance"].issues] == ["ETL-SSIS-01"]
    assert [i.id for i in tasks["EventHandler[OnError]"].issues] == ["ETL-SSIS-02"]
    assert ("DFT Load FactSales", "DFT Aggregate SalesByCategory") in ssis_pkg.precedence


def test_informatica_mappings(infa_pkg):
    assert [g.job for g in infa_pkg.graphs] == ["m_load_dim_customer", "m_load_fact_orders", "m_agg_customer_sales",
                                                "m_route_orders", "m_legacy_customer_merge"]
    dim = graph(infa_pkg, "m_load_dim_customer")
    assert dim.tags == ["m_load_dim_customer", "wf_sales_dw"]
    assert dim.domains == {"status": ["A", "I", "X"]}
    assert dim.nodes["exp_std_name"].props["outputs"][0].sql.startswith("CASE WHEN (in_name IS NULL)")  # reusable
    lkp = dim.nodes["lkp_region"].props
    assert lkp["keys"] == [("region_id", "in_region_id")] and lkp["returns"] == [("region_name", "region_name")]
    assert dim.nodes["seq_customer_key"].kind == "sequence"
    fact = graph(infa_pkg, "m_load_fact_orders")
    assert fact.nodes["sq_orders"].props["filter_sql"] == "amount > 0"
    calc = {o.name: o for o in fact.nodes["exp_order_calc"].props["outputs"]}
    assert "v_net_amount" not in calc["o_order_size"].sql and calc["o_order_size"].sql.startswith("CASE WHEN ROUND(")
    jnr = fact.nodes["jnr_order_customer"].props
    assert jnr["join_type"] == "left" and jnr["conditions"] == [("m_cust_id", "cust_id")]
    roles = {e.src: e.dst_port for e in fact.edges if e.dst == "jnr_order_customer"}
    assert roles == {"exp_order_calc": "detail", "sq_customers": "master"}
    rtr = graph(infa_pkg, "m_route_orders").nodes["rtr_orders"].props
    assert rtr["semantics"] == "all_match" and rtr["group_fields"]["LARGE"][0] == ("order_id", "order_id1")
    legacy = graph(infa_pkg, "m_legacy_customer_merge")
    assert {i.id for i in legacy.issues} == {"ETL-INF-01", "ETL-INF-04", "ETL-INF-05", "ETL-INF-06", "ETL-INF-07"}
    assert {n.kind for n in legacy.nodes.values()} >= {"unsupported"}


def test_classification_and_recommendations(ssis_pkg, infa_pkg):
    result = {a.job: a for a in assess([ssis_pkg, infa_pkg])}
    assert result["m_legacy_customer_merge"].classification == "complex"
    assert result["m_legacy_customer_merge"].recommendation == "re-engineer"
    assert "Update Strategy" in result["m_legacy_customer_merge"].rationale
    for job in ("m_load_dim_customer", "m_load_fact_orders", "LoadSalesMart::DFT Load FactSales"):
        assert (result[job].classification, result[job].recommendation) == ("transform", "lift")
    assert result["LoadSalesMart::SQL Truncate FactSales"].recommendation == "retire"
    assert result["LoadSalesMart::SCR Notify Finance"].recommendation == "re-engineer"
    for a in result.values():
        assert 0 < a.confidence <= 1 and a.rationale
    retired = {a.job: a for a in assess([infa_pkg], usage={"m_route_orders": 0, "m_load_fact_orders": 61})}
    assert retired["m_route_orders"].recommendation == "retire"
    assert retired["m_load_fact_orders"].recommendation == "lift"


def test_graph_hash_is_stable(infa_pkg):
    from altitude.etl.informatica import parse_powercenter

    (again,) = parse_powercenter(POWERCENTER)
    assert [g.hash() for g in again.graphs] == [g.hash() for g in infa_pkg.graphs]
