import sqlite3
from pathlib import Path
SCHEMA="""CREATE TABLE IF NOT EXISTS matches(source TEXT,source_event_id TEXT,started_at TEXT,team_a_id INTEGER,team_b_id INTEGER,team_a TEXT,team_b TEXT,score_a INTEGER,score_b INTEGER,winner TEXT,format INTEGER,league TEXT,serie TEXT,unit TEXT,shadow_only INTEGER CHECK(shadow_only=1),PRIMARY KEY(source,source_event_id));"""
def connect(path): p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);c=sqlite3.connect(p);c.executescript(SCHEMA);return c
def ingest(conn,rows):
 n=0
 for r in rows:
  if r.get('shadow_only') is not True or r.get('unit')!='series': raise ValueError('registro histórico inseguro')
  conn.execute('INSERT OR REPLACE INTO matches VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)',(r['source'],r['source_event_id'],r['started_at'],r['team_a_id'],r['team_b_id'],r['team_a'],r['team_b'],r['score_a'],r['score_b'],r['winner'],r.get('format'),r.get('league'),r.get('serie'),r['unit']));n+=1
 conn.commit();return n
def report(conn):
 total=conn.execute('select count(*) from matches').fetchone()[0]; leagues=conn.execute('select count(distinct league) from matches').fetchone()[0]; academy=conn.execute("select count(*) from matches where lower(team_a||' '||team_b||' '||coalesce(league,'')) like '%academy%'").fetchone()[0]
 return {'series':total,'leagues':leagues,'academy_series':academy,'promotion_safe':False,'reason':'exige filtro Tier 1/2 compatível com o backtest HLTV'}
