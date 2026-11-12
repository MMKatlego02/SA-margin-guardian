-- Q1 ageing buckets: how much of the stock is old, and how much of the flagged risk sits in each bucket?
SELECT CASE WHEN days_on_lot < 30  THEN '1) 0-29 days'
            WHEN days_on_lot < 60  THEN '2) 30-59 days'
            WHEN days_on_lot < 90  THEN '3) 60-89 days'
            WHEN days_on_lot < 120 THEN '4) 90-119 days'
            ELSE '5) 120+ days' END       AS age_bucket,
       COUNT(*)                           AS vehicles,
       SUM(flagged)                       AS flagged,
       ROUND(AVG(margin_pct), 1)          AS avg_margin_pct,
       ROUND(SUM(at_risk_rand))           AS at_risk_rand
FROM vehicle_margins
GROUP BY age_bucket
ORDER BY age_bucket;

-- Q2 margin by dealer: weighted margin (profit / price) so expensive cars count for more than cheap ones.
SELECT dealer_location,
       COUNT(*)                                                        AS vehicles,
       ROUND(100.0 * SUM(projected_profit) / SUM(projected_sale_price), 2) AS weighted_margin_pct,
       ROUND(AVG(days_on_lot), 1)                                      AS avg_days_on_lot,
       SUM(flagged)                                                    AS flagged,
       ROUND(100.0 * SUM(flagged) / COUNT(*), 1)                       AS pct_flagged
FROM vehicle_margins
GROUP BY dealer_location
ORDER BY weighted_margin_pct;

-- Q3 ten worst vehicles: the biggest projected rand losses, with the recommended action.
SELECT vehicle_id, brand, model, dealer_location, days_on_lot,
       ROUND(projected_profit) AS projected_profit,
       ROUND(margin_pct, 1)    AS margin_pct,
       recommendation
FROM vehicle_margins
ORDER BY projected_profit ASC, vehicle_id
LIMIT 10;

-- Q4 window function: rank dealers by at-risk rand and show each dealer's share of the group total.
SELECT dealer_location,
       ROUND(SUM(at_risk_rand))                                              AS at_risk_rand,
       RANK() OVER (ORDER BY SUM(at_risk_rand) DESC)                         AS risk_rank,
       ROUND(100.0 * SUM(at_risk_rand) / SUM(SUM(at_risk_rand)) OVER (), 1)  AS pct_of_group_at_risk
FROM vehicle_margins
GROUP BY dealer_location
ORDER BY risk_rank;

-- Q5 brand comparison: margin, speed of sale and risk side by side.
SELECT brand,
       COUNT(*)                                                        AS vehicles,
       ROUND(AVG(days_on_lot), 1)                                      AS avg_days_on_lot,
       ROUND(100.0 * SUM(projected_profit) / SUM(projected_sale_price), 2) AS weighted_margin_pct,
       ROUND(100.0 * SUM(flagged) / COUNT(*), 1)                       AS pct_flagged,
       ROUND(SUM(at_risk_rand))                                        AS at_risk_rand
FROM vehicle_margins
GROUP BY brand
ORDER BY weighted_margin_pct;
