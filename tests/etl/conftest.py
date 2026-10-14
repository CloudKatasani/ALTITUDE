from pathlib import Path

import pytest

from altitude.etl.informatica import parse_powercenter
from altitude.etl.ssis import parse_dtsx

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
DTSX = FIXTURES / "ssis" / "LoadSalesMart.dtsx"
POWERCENTER = FIXTURES / "informatica" / "wf_sales_dw.xml"
CONTROLM = FIXTURES / "controlm" / "DWH_NIGHTLY.xml"
SQLAGENT = FIXTURES / "sqlagent" / "DWH_Nightly_Load.sql"


@pytest.fixture(scope="module")
def ssis_pkg():
    return parse_dtsx(DTSX)


@pytest.fixture(scope="module")
def infa_pkg():
    (pkg,) = parse_powercenter(POWERCENTER)
    return pkg


def graph(pkg, job_suffix):
    return next(g for g in pkg.graphs if g.job.endswith(job_suffix))
