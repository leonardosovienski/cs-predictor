"""CS market-shadow readiness; maturity requires a validated settlement."""
import argparse,json,sqlite3,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from src.prospective_market import ProspectiveStore
from src.beyond_market_closure import closure_record, is_production_market_db
def status(path,now=None,market_db=None):
 closed=closure_record() if market_db and is_production_market_db(Path(market_db)) else None
 if closed and closed.get('scientific_status') == 'CLOSED_BY_HUMAN_DECISION':
  return {'scientific_status':'CLOSED_BY_HUMAN_DECISION','operational_status':'NO_GO','reason':closed['human_decision']['reason'],'closure_record':str((ROOT/'docs/records/beyond_market_closure.json').relative_to(ROOT)),'decision_ready':False}
 if market_db and Path(market_db).exists():
  store=ProspectiveStore(market_db);c=store.connect()
  try:return store.status(c,now=now)
  finally:c.close()
 rows=[json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()] if path.exists() else []
 eligible=[r for r in rows if all(k in r for k in ('model_probability_a','model_probability_b','ratings_sha256','observed_at','scheduled_at'))]
 latest={}
 for r in eligible:
  key=r.get('market_id') or r.get('quote_id')
  if key not in latest or r['observed_at']>latest[key]['observed_at']: latest[key]=r
 observed=now or datetime.now(timezone.utc); passed=sum(datetime.fromisoformat(r['scheduled_at'])<observed for r in latest.values())
 return {'raw_quotes':len(rows),'legacy_ineligible':len(rows)-len(eligible),'eligible_quotes':len(eligible),'eligible_matches':len(latest),'event_time_passed':passed,'matured_matches':0,'required_matured_matches':50,'required_calendar_days':30,'decision_ready':False,'verdict':'BLOCKED_BY_MARKET_DATA','reason':'Market DB/resultado/closing/settlement ausentes'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--quotes',type=Path,default=ROOT/'data'/'market_shadow.jsonl');p.add_argument('--market-db',type=Path,default=ROOT/'data'/'market.db');a=p.parse_args();print(json.dumps(status(a.quotes,market_db=a.market_db),sort_keys=True)); return 3 if is_production_market_db(a.market_db) and closure_record().get('scientific_status') == 'CLOSED_BY_HUMAN_DECISION' else 0
if __name__=='__main__': raise SystemExit(main())
