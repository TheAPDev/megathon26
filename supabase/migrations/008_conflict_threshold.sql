-- Conflict threshold tightened to 1.5x (high label) / 0.6x (low label), matching greenghar/engine/score.py.
-- gg.score was re-created with the new thresholds (see 004_engine_functions.sql, now current), then:
with x as (select h.home_id, s.warnings, s.confidence from public.homes h cross join lateral gg.score(h) s where h.bee_star_label is not null)
update public.home_scores hs set warnings = x.warnings, confidence = x.confidence, computed_at = now(), engine_version = 'gg.score v1.1'
from x where hs.home_id = x.home_id and (hs.warnings is distinct from x.warnings or hs.confidence is distinct from x.confidence);
