import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/"daily-financial-health-brief/scripts"))
import run
from urllib.error import HTTPError
from unittest.mock import patch

def test_material_boundaries():
    assert run.material("500.01","10000") is False
    assert run.material("1000.01","1000") is True
    assert run.material("500.01","0") is True

def test_unknown_amount():
    assert run.dec("","amount",2)==""

def test_money_formats():
    assert run.dec("360","amount",2)==run.Decimal("360")
    assert run.dec("8000.00","amount",2)==run.Decimal("8000.00")
    assert run.dec("8,000.00","amount",2)==run.Decimal("8000.00")
    assert run.dec("-8,000.00","amount",2)==run.Decimal("-8000.00")
    assert run.dec("+8,000.00","amount",2)==run.Decimal("8000.00")
    assert run.dec("0.00","amount",2)==run.Decimal("0.00")
    assert run.dec("0","amount",2)==run.Decimal("0")

def test_malformed_money_rejected():
    for value in ("8,00.00","8,000.0.0","1,2,3","nonnumeric"):
        try: run.dec(value,"amount",2)
        except run.BriefError: pass
        else: assert False

def test_revenue_metric_validation():
    row={k:"" for k in run.RE}; row.update(metric="enrolled_students",value="12")
    run.validate("revenue",[row])
    row["value"]="12.5"
    try: run.validate("revenue",[row])
    except run.BriefError: pass
    else: assert False

def test_role_schema():
    assert run.role([{k:"" for k in run.TX}])=="transactions"
    assert run.role([{k:"" for k in run.BU}])=="budget"
    assert run.role([{k:"" for k in run.RE}])=="revenue"

def test_fetch_failure():
    try: run.fetch("https://invalid.example.invalid/nope")
    except run.BriefError as e: assert "source fetch failed" in str(e)
    else: assert False

def test_sheet_info_reads_fragment_gid():
    sid,gid=run.sheet_info("https://docs.google.com/spreadsheets/d/16HhjfR9uG1oUwSFNjQvAvU9Q9gVjzxL0ufBzTJe82v8/edit#gid=386574278")
    assert sid=="16HhjfR9uG1oUwSFNjQvAvU9Q9gVjzxL0ufBzTJe82v8"
    assert gid=="386574278"

def test_export_endpoint():
    endpoint=run.export_endpoint("https://docs.google.com/spreadsheets/d/id/edit#gid=7")
    assert endpoint=="https://docs.google.com/spreadsheets/d/id/export?format=csv&gid=7"

def test_http_error_is_sanitized():
    error=HTTPError("https://docs.google.com/spreadsheets/d/id/export?format=csv&gid=7",400,"Bad Request",{},None)
    with patch.object(run,"urlopen",side_effect=error):
        try: run.fetch("https://docs.google.com/spreadsheets/d/id/edit#gid=7")
        except run.BriefError as e:
            message=str(e)
            assert "status=400" in message and "gid=7" in message
            assert "token" not in message.lower()
        else: assert False
