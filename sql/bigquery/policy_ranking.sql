-- Rank the targeting policies by profit and by ROI (window functions over the policy table).
-- Rows with no cost (target nobody) have a NULL ROI, so they sort last on ROI.

SELECT
  policy,
  share_targeted,
  cost,
  incremental_value,
  profit,
  roi,
  cost_per_incremental_conversion,
  RANK() OVER (ORDER BY profit DESC) AS rank_by_profit,
  RANK() OVER (ORDER BY roi DESC NULLS LAST) AS rank_by_roi
FROM `offer_uplift.policy_comparison`
ORDER BY rank_by_profit;
