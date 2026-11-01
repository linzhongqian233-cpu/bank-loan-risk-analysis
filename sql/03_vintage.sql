-- =============================================================
-- 03 Vintage 账龄分析（本项目核心，DuckDB 语法）
--
-- 口径：
--   行 = 放款季度（Vintage cohort）
--   列 = 账龄 MOB（month on book），即放款后第 N 个月
--   值 = 该 cohort 在 MOB ≤ N 时的累计不良率
--
-- ⚠ 两个关键坑：
--   1. 观测窗口必须按 cohort 统一计算（放款季度首日 → 观测截止），
--      不能用 MIN(mob)——每个 cohort 都有"当月即还款"的贷款，
--      MIN 会取到 0，导致全部账龄不良率变成 NaN。
--   2. 观测不足的格子应留 NULL（不填 0），否则会凭空压低留存/不良率。
-- =============================================================

WITH src AS (
    SELECT * FROM read_parquet('D:/datasets/processed/lc_accepted.parquet')
    WHERE loan_status NOT IN (
            'Does not meet the credit policy. Status:Fully Paid',
            'Does not meet the credit policy. Status:Charged Off')
      AND loan_status IS NOT NULL AND issue_d IS NOT NULL
),
b AS (
    SELECT
        strptime(issue_d, '%b-%Y')::DATE AS issue_date,
        CASE WHEN last_pymnt_d IS NULL OR last_pymnt_d = '' THEN NULL
             ELSE strptime(last_pymnt_d, '%b-%Y')::DATE END AS last_pymnt_date,
        CASE WHEN loan_status IN ('Charged Off', 'Default') THEN 1 ELSE 0 END AS is_bad
    FROM src
),
b2 AS (
    SELECT *,
           date_diff('month', issue_date, COALESCE(last_pymnt_date, DATE '2018-12-01')) AS mob
    FROM b
),
agg AS (
    SELECT date_trunc('quarter', issue_date)::DATE AS cohort,
           COUNT(*)                                AS n,
           -- 观测月数：按 cohort 统一算，不用 MIN(mob)
           date_diff('month', date_trunc('quarter', issue_date)::DATE, DATE '2018-12-01') AS age,
           SUM(CASE WHEN is_bad = 1 AND mob <= 6  THEN 1 ELSE 0 END)  AS bad_6,
           SUM(CASE WHEN is_bad = 1 AND mob <= 12 THEN 1 ELSE 0 END)  AS bad_12,
           SUM(CASE WHEN is_bad = 1 AND mob <= 24 THEN 1 ELSE 0 END)  AS bad_24,
           SUM(CASE WHEN is_bad = 1 AND mob <= 36 THEN 1 ELSE 0 END)  AS bad_36
    FROM b2
    GROUP BY cohort
)
SELECT cohort                AS 放款季度,
       n                     AS 笔数,
       age                   AS 可观测月数,
       CASE WHEN age >= 6  THEN ROUND(bad_6  * 100.0 / n, 2) END AS MOB6不良率,
       CASE WHEN age >= 12 THEN ROUND(bad_12 * 100.0 / n, 2) END AS MOB12不良率,
       CASE WHEN age >= 24 THEN ROUND(bad_24 * 100.0 / n, 2) END AS MOB24不良率,
       CASE WHEN age >= 36 THEN ROUND(bad_36 * 100.0 / n, 2) END AS MOB36不良率
FROM agg
ORDER BY 放款季度;
