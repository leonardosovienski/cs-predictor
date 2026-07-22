import json,pytest
from src.betting import go_gate,record_bet,settle_bet
def test_paper_bet_and_idempotent_settlement(tmp_path):
    log=tmp_path/'bets.jsonl'; bet=record_bet(selection='Vitality',prob_model=.6,decimal_odds=2,bankroll=1000,path=log); assert bet['stake']==20
    assert settle_bet(bet,True,path=log)==settle_bet(bet,False,path=log)
def test_real_fails_closed(tmp_path):
    with pytest.raises(PermissionError): record_bet(selection='Vitality',prob_model=.6,decimal_odds=2,bankroll=1000,real=True,path=tmp_path/'b',gate_path=tmp_path/'missing')
def test_cs_gate_allows_only_prospective_shadow(tmp_path):
    p=tmp_path/'g'; p.write_text(json.dumps({'verdict':'GATE_PASSED_FOR_PROSPECTIVE_SHADOW','matured_matches':1000,'required_matured_matches':1000,'calendar_days':90,'required_calendar_days':90})); assert go_gate(p)['decision']=='GATE_PASSED_FOR_PROSPECTIVE_SHADOW'
    with pytest.raises(PermissionError): record_bet(selection='Vitality',prob_model=.6,decimal_odds=2,bankroll=1000,real=True,gate_path=p)
