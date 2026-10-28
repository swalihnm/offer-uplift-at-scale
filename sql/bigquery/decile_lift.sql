-- Observed uplift per predicted-uplift decile, and how each decile compares with the average.
-- Decile 1 = customers the model ranks as most persuadable.

SELECT
  decile,
  n,
  observed_lift,
  observed_lift / AVG(observed_lift) OVER () AS lift_vs_simple_avg_of_deciles,
  observed_lift - MIN(observed_lift) OVER () AS lift_above_worst_decile
FROM `offer_uplift.uplift_deciles`
ORDER BY decile;
