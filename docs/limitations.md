# Limitations

1. **Balance is worse than the 0.1 SMD threshold suggests. The CUPED gap is fully explained by it.** Raw minus adjusted lift equals β·(x̄_treated − x̄_control) exactly (0.3356 pp, ratio 1.0000000), so CUPED is correct and the disagreement is the imbalance itself. All 12 features have |SMD| < 0.1 (max 0.049), which passes the spec's check. But with about 14M rows, a clean randomization would give SMDs near 0.001. The observed values are roughly 10–65× larger than chance, and CUPED moves the visit lift from +1.03pp (raw) to +0.70pp (adjusted), with non-overlapping 95% CIs. The cause is not explained. Until it is, treat the raw intent-to-treat estimate as the headline and the CUPED estimate as unresolved.

2. **Exact duplicate rows look like a data artifact.** 2,221,150 rows (about 16%) have an identical copy elsewhere in the file. Of these, 95.7% are treated, and they contain 42 visits in total, against a 5.9% visit rate for unique treated rows. Dropping them broke the randomization (treated share 83.9%, SRM chi-square 12,065, p = 0). Keeping them lowers the treated visit rate and shrinks the headline lift from +1.91 pp (unique rows, but arms unbalanced) to +1.03 pp (all rows). The headline uses all rows. Whether the repeats are logging errors or real customers needs confirming with the data owner.

3. **Anonymized features.** The segments are data-driven clusters of anonymized features, not demographics.

4. **Economics are assumptions.** The cost and value figures in `conf/economics.yaml` are placeholders. The sensitivity grid shows the decision changes with them: the valid-chosen cutoff ranges from 11.5% to 31% of customers, and targeting everyone is unprofitable in 5 of 9 settings.

5. **Cutoff chosen on the valid split, reported on test.** The 23% cutoff is the profit-maximising share on the valid split, and the test profit (+$398k, ROI 248%) is reported at that cutoff. An earlier version chose the cutoff on test (19%, +$412k, ROI 311%), which was optimistic. The sensitivity grid applies the same rule in every cell.

6. **Class-transformation learner underperforms, and its real-data failure is not reproduced.** Its test Qini is −1,727, and its scores correlate with the T-learner at 0.009. On synthetic data with a similar average effect (about +0.7 pp) it is weakly positive (Qini 34 against 376 for the S-learner), and at a 50/50 split it is still weak (26 against 215). So the method is weak here, but the strongly negative real-data value is not explained. The likely cause is the large class weights (1/(1−π) ≈ 6.7 on control non-responders) fitting noise. It is reported, not used.

7. **Do-not-disturb segment is consistent with the prediction but too small to confirm.** Predicted uplift is −0.21 pp. The observed visit lift is +0.06 pp with a 95% CI of −0.27 to +0.40 pp, so the prediction sits inside the interval. The segment has about 159,000 test customers, but only 24,000 of them are control, which limits precision.

8. **Uplift models trained on a sample.** The learners use a 1.5M-row stratified sample of the train split, and the X-learner uses in-sample imputations. The test and valid splits are scored in pandas, not Spark.

9. **Single experiment.** The results come from one randomized test with one offer.
