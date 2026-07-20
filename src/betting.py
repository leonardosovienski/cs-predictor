"""Paper betting and a fail-closed financial gate for CS2 moneylines."""
from __future__ import annotations
from datetime import datetime, timezone
import json, os, uuid
from pathlib import Path
from .config import ROOT
KELLY_SHRINK=0.25; KELLY_CAP=0.02
def kelly_stake(prob,odds,bankroll):
    if not 0<prob<1 or odds<=1 or bankroll<=0: raise ValueError("prob, odds ou bankroll inválidos")
    raw=max(0.0,(prob*odds-1)/(odds-1)); return round(bankroll*min(raw*KELLY_SHRINK,KELLY_CAP),2)
def go_gate(path=None):
    p=Path(path or ROOT/'data'/'market_gate.json')
    if not p.exists(): return {'decision':'NO-GO','reason':'market_gate.json ausente; amostra financeira não avaliada'}
    d=json.loads(p.read_text(encoding='utf-8')); ready=(d.get('verdict') in {'GO','COMPROVADA'} and d.get('matured_matches',0)>=d.get('required_matured_matches',1000) and d.get('calendar_days',0)>=d.get('required_calendar_days',90))
    return {'decision':'GO' if ready else 'NO-GO','reason':'gate financeiro aprovado' if ready else 'amostra financeira/gate insuficiente'}
def record_bet(*,selection,prob_model,decimal_odds,bankroll,real=False,event_id=None,path=None,gate_path=None,**metadata):
    if real and go_gate(gate_path)['decision']!='GO': raise PermissionError('aposta real bloqueada pelo gate financeiro')
    row={'id':str(uuid.uuid4()),'event':'bet','domain':'cs','created_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),'event_id':event_id,'market':'moneyline','selection':selection,'prob_model':prob_model,'decimal_odds':decimal_odds,'edge':round(prob_model*decimal_odds-1,6),'bankroll':bankroll,'stake':kelly_stake(prob_model,decimal_odds,bankroll),'real':real,**metadata}
    target=Path(path or os.environ.get('BETS_LOG_PATH',ROOT/'data'/'bets.jsonl')); target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('a',encoding='utf-8',newline='\n') as f: f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n'); f.flush(); os.fsync(f.fileno())
    return row
def settle_bet(bet,won,*,path=None):
    target=Path(path or os.environ.get('BETS_LOG_PATH',ROOT/'data'/'bets.jsonl'))
    if target.exists():
        for line in target.read_text(encoding='utf-8').splitlines():
            row=json.loads(line)
            if row.get('event')=='settlement' and row.get('id')==bet['id']: return row
    pnl=bet['stake']*(bet['decimal_odds']-1) if won else -bet['stake']; row={'id':bet['id'],'event':'settlement','won':bool(won),'pnl':round(pnl,2),'settled_at':datetime.now(timezone.utc).isoformat(timespec='seconds')}
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('a',encoding='utf-8',newline='\n') as f: f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n'); f.flush(); os.fsync(f.fileno())
    return row
