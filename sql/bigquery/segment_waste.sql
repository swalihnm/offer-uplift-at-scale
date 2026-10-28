-- Share of the population in each segment, and how much of it is wasted spend under "target everyone".
-- Wasted = sure things (respond anyway) and lost causes (never respond). Do-not-disturb is also a loss.

SELECT
  segment,
  share,
  mean_predicted_uplift,
  baseline_visit_rate,
  observed_visit_lift,
  CASE WHEN segment IN ('sure_thing', 'lost_cause', 'do_not_disturb') THEN 'wasted' ELSE 'target' END AS spend_bucket,
  SUM(share) OVER (PARTITION BY CASE WHEN segment IN ('sure_thing', 'lost_cause', 'do_not_disturb') THEN 'wasted' ELSE 'target' END) AS bucket_share
FROM `offer_uplift.segment_profile`
ORDER BY share DESC;
