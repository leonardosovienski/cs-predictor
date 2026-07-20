"""CS market-shadow readiness; legacy quotes without frozen model are excluded."""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def status(path,now=None):
 rows=[json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()] if path.exists() else []
 eligible=[r for r in rows if all(k in r for k in ('model_probability_a','model_probability_b','ratings_sha256','observed_at','scheduled_at'))]
 latest={}
 for r in eligible:
  key=r.get('market_id') or r.get('quote_id')
  if key not in latest or r['observed_at']>latest[key]['observed_at']: latest[key]=r
 observed=now or datetime.now(timezone.utc); matured=sum(datetime.fromisoformat(r['scheduled_at'])<observed for r in latest.values())
 return {'raw_quotes':len(rows),'legacy_ineligible':len(rows)-len(eligible),'eligible_quotes':len(eligible),'eligible_matches':len(latest),'matured_matches':matured,'required_matured_matches':50,'required_calendar_days':30,'decision_ready':matured>=50,'verdict':'PENDING_SAMPLE' if matured<50 else 'READY_FOR_BLINDED_EVALUATION'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--quotes',type=Path,default=ROOT/'data'/'market_shadow.jsonl');a=p.parse_args();print(json.dumps(status(a.quotes),sort_keys=True))
if __name__=='__main__':main()
