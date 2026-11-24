import csv,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/"daily-financial-health-brief/scripts"))
import run

class HardeningTests(unittest.TestCase):
    def args(self):
        return SimpleNamespace(reporting_date="2026-08-11",prior_business_date="2026-08-10",revenue_snapshot_date="2026-08-11",revenue_metrics=["collected_revenue","outstanding_balance"])
    def test_five_figures_and_date_windows(self):
        tx=[{"transaction_id":"a","date":"2026-08-10","status":"posted","amount":"10","amount_status":"confirmed","category":"x"},{"transaction_id":"b","date":"2026-08-11","status":"posted","amount":"12.50","amount_status":"confirmed","category":"x"},{"transaction_id":"c","date":"2026-08-11","status":"pending","amount":"3","amount_status":"confirmed","category":"x"},{"transaction_id":"d","date":"2026-08-11","status":"disputed","amount":"4","amount_status":"confirmed","category":"x"},{"transaction_id":"e","date":"2026-08-12","status":"posted","amount":"99","amount_status":"confirmed","category":"x"}]
        bu=[{"period":"2026-08","category":"x","budget_amount":"20"}]; rev=[]
        text=run.build_report(self.args(),tx,bu,rev,[])
        for expected in ("12.50","3","4","10","2.50","2026-08-01 through 2026-08-11: 2"): self.assertIn(expected,text)
    def test_report_documents_assumptions(self):
        text=run.build_report(self.args(),[],[],[],[])
        self.assertIn("Reporting timezone remains a stakeholder policy choice",text)
        self.assertIn("do not independently prove",text)
    def test_materiality_boundaries(self):
        self.assertFalse(run.material("500","10000")); self.assertFalse(run.material("1000","10000")); self.assertTrue(run.material("1000.01","10000")); self.assertTrue(run.material("500.01","0"))
    def test_unknown_blank(self): self.assertIsNone(run.dec("","amount",2))
    def test_schema_and_rows(self):
        rows=[{k:"" for k in run.TX}]; rows[0]["transaction_id"]="x"; rows[0]["amount"]="360"
        run.validate("transactions",rows); self.assertEqual(run.TX, list(run.TX))
    def test_duplicate_rejected(self):
        row={k:"" for k in run.TX}; row.update(transaction_id="x",amount="1",status="posted",amount_status="confirmed")
        with self.assertRaises(run.BriefError): run.validate("transactions",[row,row.copy()])
    def test_count_metric(self):
        row={k:"" for k in run.RE}; row.update(metric="enrolled_students",value="3")
        run.validate("revenue",[row]); row["value"]="3.5"
        with self.assertRaises(run.BriefError): run.validate("revenue",[row])
    def test_stage_publication_marker(self):
        with tempfile.TemporaryDirectory(dir=run.ROOT) as d:
            stage=Path(d); [run.write_csv(stage/f"{n}.csv",n,[{k:"" for k in run.SCHEMAS[n]}]) for n in run.SCHEMAS]
            (stage/"report.md").write_text("x")
            old=run.OUT
            try:
                run.OUT=stage/"out"; run.publish(stage); self.assertTrue((run.OUT/".complete").exists())
            finally: run.OUT=old
    def test_failed_rerun_clears_stale_outputs(self):
        with tempfile.TemporaryDirectory(dir=run.ROOT) as d:
            old=run.OUT; run.OUT=Path(d)/"out"; (run.OUT/"normalized").mkdir(parents=True); (run.OUT/"report.md").write_text("stale"); (run.OUT/".complete").write_text("complete")
            try:
                bad=self.args(); bad.transaction_url=bad.budget_url=bad.revenue_url="https://invalid.example.invalid"
                with self.assertRaises(run.BriefError): run.run(bad)
                self.assertFalse((run.OUT/"report.md").exists()); self.assertFalse((run.OUT/".complete").exists())
            finally: run.OUT=old
    def test_publication_rollback(self):
        with tempfile.TemporaryDirectory(dir=run.ROOT) as d:
            stage=Path(d)/"stage"; stage.mkdir(); out=Path(d)/"out"; (out/"normalized").mkdir(parents=True); (out/"report.md").write_text("old"); (out/".complete").write_text("complete")
            for n in run.SCHEMAS: run.write_csv(stage/f"{n}.csv",n,[{k:"" for k in run.SCHEMAS[n]}])
            (stage/"report.md").write_text("new")
            old=run.OUT; run.OUT=out; real=run.os.replace; calls=[0]
            def fail_once(src,dst):
                calls[0]+=1
                if calls[0]==5: raise OSError("simulated interruption")
                return real(src,dst)
            try:
                with patch.object(run.os,"replace",side_effect=fail_once):
                    with self.assertRaises(OSError): run.publish(stage)
                self.assertEqual((out/"report.md").read_text(),"old"); self.assertEqual((out/".complete").read_text(),"complete\n")
            finally: run.OUT=old

if __name__=="__main__": unittest.main()
