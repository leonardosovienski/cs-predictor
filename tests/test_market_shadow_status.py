import json
from datetime import datetime,timezone
from scripts.market_shadow_status import status
def test_legacy_quotes_are_not_retroactively_eligible(tmp_path):
 p=tmp_path/'q'; rows=[{'quote_id':'old','scheduled_at':'2026-01-01T00:00:00+00:00'}, {'quote_id':'new','market_id':'m','observed_at':'2025-12-01T00:00:00+00:00','scheduled_at':'2026-01-01T00:00:00+00:00','model_probability_a':.6,'model_probability_b':.4,'ratings_sha256':'x'}];p.write_text('\n'.join(json.dumps(x) for x in rows))
 out=status(p,datetime(2026,2,1,tzinfo=timezone.utc));assert out['legacy_ineligible']==1 and out['event_time_passed']==1 and out['matured_matches']==0
