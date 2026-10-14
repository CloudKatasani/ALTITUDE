# AUTO-GENERATED — DO NOT EDIT. Source: altitude.observability.generate. Regenerate with `altitude generate`.
"""Package O dashboards in Streamlit-in-Snowflake (dashboards 1, 2, 4 and 8) over OBS.KPI."""

import streamlit as st
from snowflake.snowpark.context import get_active_session

session = get_active_session()
st.set_page_config(page_title="Platform Observability", layout="wide")


def q(sql, params=None):
    return session.sql(sql, params=params or []).to_pandas()


accounts = q("SELECT DISTINCT ACCOUNT_NAME FROM OBS.KPI.KPI_COST_011 ORDER BY 1")["ACCOUNT_NAME"].tolist()
account = st.sidebar.selectbox("Account", accounts)
days = st.sidebar.slider("Window (days)", 7, 90, 28)
page = st.sidebar.radio("Dashboard", ["Executive Cost & Value", "Platform Health", "Pipelines & Freshness",
                                      "Chargeback statements"])
win = "PERIOD >= DATEADD(DAY, -?, (SELECT MAX(PERIOD) FROM OBS.KPI.KPI_COST_011)) AND ACCOUNT_NAME = ?"

if page == "Executive Cost & Value":
    st.header("Executive Cost & Value")
    c1, c2, c3 = st.columns(3)
    mom = q("SELECT VALUE FROM OBS.KPI.KPI_COST_004 WHERE ACCOUNT_NAME = ? ORDER BY PERIOD DESC LIMIT 1", [account])
    fvb = q("SELECT VALUE FROM OBS.KPI.KPI_COST_005 WHERE ACCOUNT_NAME = ? ORDER BY PERIOD DESC LIMIT 1", [account])
    spend = q(f"SELECT PERIOD, VALUE FROM OBS.KPI.KPI_COST_011 WHERE {win} ORDER BY PERIOD", [days, account])
    c1.metric("Spend in window ($)", f"{spend['VALUE'].sum():,.0f}")
    c2.metric("Month-on-month (%)", "-" if mom.empty else f"{mom['VALUE'][0]:+.1f}")
    c3.metric("Forecast vs budget", "-" if fvb.empty else f"{fvb['VALUE'][0]:.0%}")
    st.subheader("Daily spend (KPI-COST-011)")
    st.line_chart(spend, x="PERIOD", y="VALUE")
    st.subheader("Spend by warehouse (KPI-COST-002)")
    st.bar_chart(q(f"SELECT DIMENSION, SUM(VALUE) AS USD FROM OBS.KPI.KPI_COST_002 WHERE {win} GROUP BY 1",
                   [days, account]), x="DIMENSION", y="USD")
    st.subheader("Cost by cost centre (KPI-COST-003)")
    st.bar_chart(q(f"SELECT DIMENSION, SUM(VALUE) AS USD FROM OBS.KPI.KPI_COST_003 WHERE {win} GROUP BY 1",
                   [days, account]), x="DIMENSION", y="USD")
elif page == "Platform Health":
    st.header("Platform Health")
    phi = q("SELECT PERIOD, VALUE FROM OBS.KPI.KPI_PHI_001 WHERE ACCOUNT_NAME = ? ORDER BY PERIOD", [account])
    st.metric("Health Index", "-" if phi.empty else f"{phi['VALUE'].iloc[-1]:.1f}")
    st.bar_chart(q("SELECT DIMENSION AS PILLAR, VALUE FROM OBS.KPI.KPI_PHI_002 WHERE ACCOUNT_NAME = ? AND PERIOD = "
                   "(SELECT MAX(PERIOD) FROM OBS.KPI.KPI_PHI_002 WHERE ACCOUNT_NAME = ?)", [account, account]),
                 x="PILLAR", y="VALUE")
    st.dataframe(q("SELECT ALERT_CLASS, SEVERITY, COUNT(*) AS FIRED FROM OBS.OPS.ALERT_EVENT WHERE STATUS = 'fired' "
                   "AND ACCOUNT_NAME = ? GROUP BY 1, 2 ORDER BY 3 DESC", [account]))
elif page == "Pipelines & Freshness":
    st.header("Pipelines & Freshness")
    st.line_chart(q(f"SELECT PERIOD, VALUE FROM OBS.KPI.KPI_REL_001 WHERE {win} ORDER BY PERIOD", [days, account]),
                  x="PERIOD", y="VALUE")
    st.bar_chart(q(f"SELECT DIMENSION, AVG(VALUE) AS ATTAINMENT FROM OBS.KPI.KPI_REL_003 WHERE {win} GROUP BY 1",
                   [days, account]), x="DIMENSION", y="ATTAINMENT")
    st.dataframe(q("SELECT FQ_NAME, SCHEDULED_TIME, ERROR_MESSAGE FROM OBS.CURATED.FACT_TASK_RUN WHERE STATE = 'FAILED' "
                   "AND ACCOUNT_NAME = ? ORDER BY SCHEDULED_TIME DESC LIMIT 50", [account]))
else:
    st.header("Chargeback statements")
    month = st.selectbox("Month", q("SELECT DISTINCT DATE_TRUNC('MONTH', PERIOD) AS M FROM OBS.KPI.KPI_COST_003 "
                                    "ORDER BY 1 DESC")["M"].tolist())
    cb = q("SELECT DIMENSION AS COST_CENTRE, SUM(VALUE) AS USD FROM OBS.KPI.KPI_COST_003 WHERE ACCOUNT_NAME = ? AND "
           "DATE_TRUNC('MONTH', PERIOD) = ? GROUP BY 1 ORDER BY 2 DESC", [account, month])
    st.dataframe(cb)
    st.download_button("Export CSV", cb.to_csv(index=False), file_name=f"chargeback_{month}.csv")
