-- =============================================================
-- 04 账龄 × 贷款状态分布（DuckDB 语法）
--
-- 用途：本数据无月度状态快照，无法计算真正的迁徙率（Roll Rate），
--       用「账龄 × 当前状态」分布做近似，用于定位风险暴露窗口。
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
        loan_status,
        CASE WHEN loan_status IN ('Charged Off', 'Default') THEN 1 ELSE 0 END AS is_bad,
        date_diff('month',
                  strptime(issue_d, '%b-%Y')::DATE,
                  COALESCE(CASE WHEN last_pymnt_d IS NULL OR last_pymnt_d = '' THEN NULL
                                ELSE strptime(last_pymnt_d, '%b-%Y')::DATE END,
                           DATE '2018-12-01')) AS mob
    FROM src
)
SELECT CASE WHEN mob < 6  THEN '00-05'
            WHEN mob < 12 THEN '06-11'
            WHEN mob < 24 THEN '12-23'
            WHEN mob < 36 THEN '24-35'
            ELSE '36+' END                                          AS 账龄区间,
       COUNT(*)                                                     AS 笔数,
       ROUND(SUM(CASE WHEN loan_status = 'Fully Paid' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS 已结清,
       ROUND(SUM(CASE WHEN loan_status = 'Current' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2)    AS 在还中,
       ROUND(SUM(CASE WHEN loan_status LIKE 'Late%' OR loan_status = 'In Grace Period'
                      THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2)                                 AS 逾期中,
       ROUND(SUM(is_bad) * 100.0 / COUNT(*), 2)                                                     AS 已核销
FROM b
GROUP BY 账龄区间
ORDER BY 账龄区间;
