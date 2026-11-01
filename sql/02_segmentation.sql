-- =============================================================
-- 02 风险分层：各评级不良率（DuckDB 语法）
--
-- 口径：不良 = Charged Off + Default
-- 注意：分母包含 Current（在还中），因此这是「静态不良率」，
--       会低估真实风险；严格的 cohort 口径见 03_vintage.sql
-- =============================================================

WITH src AS (
    SELECT * FROM read_parquet('D:/datasets/processed/lc_accepted.parquet')
    WHERE loan_status NOT IN (
            'Does not meet the credit policy. Status:Fully Paid',
            'Does not meet the credit policy. Status:Charged Off')
      AND loan_status IS NOT NULL AND issue_d IS NOT NULL
),
b AS (
    SELECT loan_amnt, int_rate, term, grade, sub_grade, dti, annual_inc,
           CASE WHEN loan_status IN ('Charged Off', 'Default') THEN 1 ELSE 0 END AS is_bad
    FROM src
)
SELECT grade                                   AS 评级,
       COUNT(*)                                AS 笔数,
       ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS 笔数占比,
       ROUND(AVG(int_rate), 2)                AS 平均利率,
       ROUND(AVG(loan_amnt), 0)                AS 平均金额,
       ROUND(AVG(dti), 1)                      AS 平均DTI,
       ROUND(AVG(annual_inc), 0)               AS 平均年收入,
       SUM(is_bad)                             AS 坏账笔数,
       ROUND(SUM(is_bad) * 100.0 / COUNT(*), 2) AS 不良率,
       -- 利差：利率 - 不良率，粗略衡量定价缓冲
       ROUND(AVG(int_rate) - SUM(is_bad) * 100.0 / COUNT(*), 2) AS 粗利差
FROM b
GROUP BY grade
ORDER BY grade;
