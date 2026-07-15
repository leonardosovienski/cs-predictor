"""Read-only fixture predictions; avoids src.predict because it appends a ledger."""
from __future__ import annotations
import argparse, json, sqlite3, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from src.model import EloModel

def build(fixture: Path):
    f=json.loads(fixture.read_text(encoding='utf8')); m=EloModel()
    if m.platt is None: raise RuntimeError('canonical Platt calibrator unavailable')
    c=sqlite3.connect(f'file:{ROOT / "data" / "cs.db"}?mode=ro',uri=True)
    out=[]
    for a,b in f['matches']:
      try:
       r=m.predict_match(a,b,f['format']); meta=[]
       for n in (r['team_a'],r['team_b']):
        games,last=c.execute('select count(*),max(date) from matches where team_a=? or team_b=?',(n,n)).fetchone()
        meta.append({'stored_name':n,'status':'EXACT','rating':m.ratings[n],'games':games,'last_observed':last})
       p=max(r['prob_team_a'],r['prob_team_b']); band='muito equilibrado' if p<.55 else 'leve vantagem' if p<.60 else 'vantagem moderada' if p<.70 else 'vantagem forte'
       out.append({'team_a':a,'team_b':b,'status':'PREDICTED','format':f['format'],'elo_raw_probability_a':r['prob_team_a_raw'],'platt_probability_a':r['prob_team_a'],'probability_b':r['prob_team_b'],'rating_a':r['elo_a'],'rating_b':r['elo_b'],'favorite':r['team_a'] if r['prob_team_a']>=.5 else r['team_b'],'confidence':band,'score_probs':r['score_probs'],'teams':meta,'limitations':['no map pool/veto, odds, roster or manual regional adjustment']})
      except ValueError as e: out.append({'team_a':a,'team_b':b,'status':'BLOCKED','reason':str(e)})
    c.close(); return {'event':f['event'],'date':f['date'],'format':f['format'],'model':'Elo H1 + canonical Platt H2','predictions':out}
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--fixtures',type=Path,required=True);p.add_argument('--json',action='store_true');p.add_argument('--strict',action='store_true');p.add_argument('--output',type=Path);a=p.parse_args(argv);r=build(a.fixtures);s=json.dumps(r,ensure_ascii=False,sort_keys=True,indent=2)
 if a.output:a.output.write_text(s+'\n',encoding='utf8')
 print(s if a.json else '\n'.join(f"{x['team_a']} vs {x['team_b']}: {x['status']}" for x in r['predictions']))
 return 2 if a.strict and any(x['status']!='PREDICTED' for x in r['predictions']) else 0
if __name__=='__main__':raise SystemExit(main())
