from __future__ import annotations
import argparse,csv,hashlib,io,os,re,shutil,sys,tempfile
from datetime import datetime
from decimal import Decimal,InvalidOperation
from pathlib import Path
from urllib.parse import parse_qs,urlparse
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError

ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/"deliverables"
TX=["transaction_id","date","account","category","description","amount","currency","status","source","source_version","amount_status"]
BU=["period","category","budget_amount","currency","owner","review_rule","source","source_version"]
RE=["date","source","metric","value","currency","source_version"]
SCHEMAS={"transactions":TX,"budget":BU,"revenue":RE}
class BriefError(Exception): pass
def clear_outputs():
    for p in (OUT/"normalized/transactions.csv",OUT/"normalized/budget.csv",OUT/"normalized/revenue.csv",OUT/"report.md"): p.unlink(missing_ok=True)
    (OUT/".complete").unlink(missing_ok=True)
def sheet_info(url):
    parsed=urlparse(url); q=parse_qs(parsed.query); f=parse_qs(parsed.fragment); parts=parsed.path.split("/")
    try: sid=parts[parts.index("d")+1]
    except (ValueError,IndexError): sid="unknown"
    return sid,(q.get("gid") or f.get("gid") or ["0"])[0]
def export_endpoint(url):
    sid,gid=sheet_info(url)
    if sid=="unknown": raise BriefError("invalid Google Sheets URL: spreadsheet id not found")
    return f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv&gid={gid}"
def fetch(url):
    sid,gid=sheet_info(url); endpoint=export_endpoint(url)
    try:
        with urlopen(Request(endpoint,headers={"User-Agent":"daily-financial-health-brief/1.0","Accept":"text/csv"}),timeout=30) as r:
            raw=r.read(); status=r.status; final_url=r.geturl(); content_type=r.headers.get_content_type()
    except HTTPError as e:
        reason="authentication or permission required" if e.code in (401,403) else ("bad request, check spreadsheet id and gid" if e.code==400 else "HTTP request failed")
        raise BriefError(f"source fetch failed endpoint={endpoint} status={e.code}: {reason}") from e
    except (URLError,OSError) as e: raise BriefError(f"source fetch failed endpoint={endpoint}: {type(e).__name__}") from e
    if status != 200: raise BriefError(f"source fetch failed endpoint={endpoint} status={status}: HTTP status is not 200")
    if content_type != "text/csv": raise BriefError(f"source fetch failed endpoint={endpoint} status={status}: content_type={content_type!r}, expected text/csv")
    try: rows=list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    except Exception as e: raise BriefError(f"CSV parse failed endpoint={endpoint}: {type(e).__name__}") from e
    if not rows: raise BriefError(f"source has no data rows endpoint={endpoint}")
    print(f"source_fetch endpoint={endpoint} status={status} final_url={final_url} content_type={content_type} row_count={len(rows)}",file=sys.stderr)
    return sid,gid,rows,hashlib.sha256(raw).hexdigest(),status,final_url,content_type
def role(rows):
    fields=set(rows[0])
    for name,schema in SCHEMAS.items():
        if set(schema).issubset(fields): return name
    raise BriefError(f"unrecognized source schema: {sorted(fields)}")
MONEY_RE=re.compile(r"^[+-]?(?:0|[1-9]\d{0,2}(?:,\d{3})+|[1-9]\d*)(?:\.\d+)?$")
MONEY_METRICS={"collected_revenue","outstanding_balance","payment_plan_balance"}
COUNT_METRICS={"enrolled_students","past_due_accounts"}
def dec(value,field,row):
    if value=="": return None
    if not MONEY_RE.fullmatch(value): raise BriefError(f"invalid {field} value {value!r} in row {row}")
    try: return Decimal(value.replace(",",""))
    except InvalidOperation as e: raise BriefError(f"invalid {field} value {value!r} in row {row}") from e
def money(value): return "" if value is None else format(value,"f")
def material(variance,baseline):
    v,b=abs(Decimal(variance)),abs(Decimal(baseline)); return v>Decimal("500") if b==0 else v>Decimal("500") and v>b*Decimal("0.10")
def validate(name,rows):
    if not set(SCHEMAS[name]).issubset(rows[0]): raise BriefError(f"{name} missing required columns")
    keys=set(); numeric={"transactions":["amount"],"budget":["budget_amount"],"revenue":["value"]}[name]
    for i,row in enumerate(rows,2):
        for field in numeric:
            value=row.get(field,"")
            if name=="revenue" and row["metric"] in COUNT_METRICS:
                if not re.fullmatch(r"\d+",value): raise BriefError(f"invalid count value {value!r} in row {i}")
            elif name=="revenue" and row["metric"] not in MONEY_METRICS:
                raise BriefError(f"unconfigured revenue metric {row['metric']!r} in row {i}")
            elif name=="transactions" and value=="" and row["amount_status"]=="unknown":
                continue
            else: dec(value,field,i)
        if name=="transactions":
            if not row["transaction_id"]: raise BriefError(f"transactions row {i} has blank transaction_id")
            key=row["transaction_id"]
        elif name=="budget": key=(row["period"],row["category"])
        else: key=(row["date"],row["source"],row["metric"])
        if key in keys: raise BriefError(f"{name} duplicate key at row {i}: {key}")
        keys.add(key)
def write_csv(path,name,rows):
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=SCHEMAS[name],lineterminator="\n"); w.writeheader()
        for row in rows:
            out={k:row.get(k,"") for k in SCHEMAS[name]}
            if name in ("transactions","budget"):
                field="amount" if name=="transactions" else "budget_amount"
                if out[field] != "": out[field]=money(dec(out[field],field,0))
            elif row["metric"] in MONEY_METRICS: out["value"]=money(dec(out["value"],"value",0))
            w.writerow(out)
def build_report(args,tx,bu,rev,meta):
    d=args.reporting_date; prior=args.prior_business_date; month=d[:7]
    def total(day,status):
        return sum((dec(r["amount"],"amount",r["transaction_id"]) or Decimal("0") for r in tx if r["date"]==day and r["status"]==status),Decimal("0"))
    posted=total(d,"posted"); pending=total(d,"pending"); disputed=total(d,"disputed"); prior_total=total(prior,"posted")
    spend={}
    for r in tx:
        if r["date"][:7]==month and r["date"]<=d and r["status"]=="posted":
            amount=dec(r["amount"],"amount",r["transaction_id"])
            if amount is not None: spend[r["category"]]=spend.get(r["category"],Decimal("0"))+amount
    budgets={r["category"]:dec(r["budget_amount"],"budget_amount",i) for i,r in enumerate(bu,2) if r["period"]==month}
    unresolved=[r for r in tx if r["date"][:7]==month and r["date"]<=d and r["status"] in ("pending","disputed")]
    revenue=[r for r in rev if r["date"]==args.revenue_snapshot_date and r["metric"] in args.revenue_metrics]
    lines=["# Daily Financial Health Brief","",f"Reporting date: {d}","",f"Reporting-date posted total: {money(posted)}",f"Reporting-date pending-confirmed total: {money(pending)}",f"Reporting-date disputed-confirmed total: {money(disputed)}",f"Prior-business-day posted total: {money(prior_total)}",f"Signed change between posted totals: {money(posted-prior_total)}","","## Month-to-date posted spend versus budget"]
    for c in sorted(set(spend)|set(budgets)):
        actual=spend.get(c,Decimal("0")); budget=budgets.get(c); lines.append(f"- {c}: posted={money(actual)}, budget={money(budget)}, variance={money(actual-budget) if budget is not None else 'UNRESOLVED'}")
    lines += ["","## Unresolved items",f"Rows pending or disputed from {month}-01 through {d}: {len(unresolved)}","Amounts remain blank and excluded from totals when amount_status is unknown.","","## Revenue snapshot"]
    for r in revenue: lines.append(f"- {r['metric']}: {r['value']} {r['currency']}".rstrip())
    lines += ["","## Unresolved assumptions","- Reporting date is an explicit run parameter and is not independently approved by Operations.","- Prior business date is explicitly supplied. The Skill does not establish a holiday calendar.","- Reporting timezone remains a stakeholder policy choice. The Google Sheets display timezone is not treated as the reporting timezone.","- Complete CSV retrieval and row validation do not independently prove that Operations approved the ledger population.","- Revenue snapshot selection is explicitly supplied and may require stakeholder approval.","- Source sign conventions, missing category budgets, and missing revenue metrics remain unconfirmed policies and require stakeholder clarification when material.","","## Source metadata"]
    for m in meta: lines.append(f"- {m['role']}: URL={m['url']}; spreadsheet_id={m['spreadsheet_id']}; gid={m['gid']}; fetched_at={m['fetched_at']}; source_version={m['source_version']}; row_count={m['row_count']}; sha256={m['sha256']}")
    return "\n".join(lines+["","Draft for human review. The Operations owner decides actions and treatment of unresolved items."])+"\n"
def run(args):
    clear_outputs(); by={}; meta=[]; fetched_at=datetime.now().astimezone().isoformat()
    for url in (args.transaction_url,args.budget_url,args.revenue_url):
        sid,gid,rows,digest,status,final_url,content_type=fetch(url); name=role(rows); validate(name,rows)
        if name in by: raise BriefError(f"duplicate source role {name}")
        by[name]=rows; meta.append({"role":name,"url":url,"spreadsheet_id":sid,"gid":gid,"fetched_at":fetched_at,"source_version":";".join(sorted({r.get("source_version","") for r in rows})),"row_count":len(rows),"sha256":digest,"final_url":final_url,"content_type":content_type})
    if set(by)!=set(SCHEMAS): raise BriefError("all three source roles are required")
    stage=Path(tempfile.mkdtemp(prefix="brief-",dir=ROOT))
    try:
        for name in SCHEMAS: write_csv(stage/f"{name}.csv",name,by[name])
        (stage/"report.md").write_text(build_report(args,by["transactions"],by["budget"],by["revenue"],meta),encoding="utf-8")
        publish(stage)
    finally: shutil.rmtree(stage,ignore_errors=True)

def publish(stage):
    OUT.mkdir(parents=True,exist_ok=True); backup=Path(tempfile.mkdtemp(prefix="brief-backup-",dir=ROOT)); moved=[]; had_marker=(OUT/".complete").exists()
    try:
        target=OUT/"normalized"; target.mkdir(parents=True,exist_ok=True)
        paths=[target/f"{name}.csv" for name in SCHEMAS]+[OUT/"report.md"]
        for path in paths:
            if path.exists():
                dest=backup/path.name; os.replace(path,dest); moved.append((dest,path))
        for name in SCHEMAS: os.replace(stage/f"{name}.csv",target/f"{name}.csv")
        os.replace(stage/"report.md",OUT/"report.md")
        (OUT/".complete").write_text("complete\n",encoding="ascii")
    except Exception:
        (OUT/".complete").unlink(missing_ok=True)
        for path in [OUT/"report.md"]+[OUT/"normalized"/f"{name}.csv" for name in SCHEMAS]: path.unlink(missing_ok=True)
        for src,dst in reversed(moved):
            if src.exists(): os.replace(src,dst)
        if had_marker: (OUT/".complete").write_text("complete\n",encoding="ascii")
        raise
    finally: shutil.rmtree(backup,ignore_errors=True)
def main():
    p=argparse.ArgumentParser(); p.add_argument("--reporting-date",required=True); p.add_argument("--prior-business-date",required=True); p.add_argument("--revenue-snapshot-date",required=True); p.add_argument("--revenue-metrics",nargs="+",default=["collected_revenue","outstanding_balance"])
    p.add_argument("--transaction-url",required=True); p.add_argument("--budget-url",required=True); p.add_argument("--revenue-url",required=True)
    try: run(p.parse_args())
    except BriefError as e: clear_outputs(); print(f"ERROR: {e}",file=sys.stderr); return 2
    return 0
if __name__=="__main__": raise SystemExit(main())
