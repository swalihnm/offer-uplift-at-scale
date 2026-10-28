-- Cumulative incremental visits and customers when the top deciles are targeted.
-- Window functions: a running sum over deciles ordered by predicted uplift.
-- Each decile's incremental outcomes are observed_lift * n.

WITH per_decile AS (
  SELECT
    decile,
    n,
    observed_lift * n AS incremental_visits_in_decile
  FROM `offer_uplift.uplift_deciles`
),
running AS (
  SELECT
    decile,
    SUM(incremental_visits_in_decile) OVER (ORDER BY decile ROWS UNBOUNDED PRECEDING) AS cum_incremental_visits,
    SUM(n) OVER (ORDER BY decile ROWS UNBOUNDED PRECEDING) AS cum_customers,
    SUM(incremental_visits_in_decile) OVER () AS total_incremental_visits,
    SUM(n) OVER () AS total_customers
  FROM per_decile
)
SELECT
  decile,
  cum_customers / total_customers AS share_targeted,
  cum_incremental_visits / total_incremental_visits AS share_of_incremental_visits_kept
FROM running
ORDER BY decile;
