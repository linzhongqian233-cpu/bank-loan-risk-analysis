-- =============================================================
-- 05 回款分析（DuckDB 语法）
--
-- 口径：
--   本金回收率 = 已收本金 / 放款金额      —— 衡量「本金拿回多少」
--   总回款率   = 总回款   / 放款金额      —— 含利息与回收，衡量「这笔生意赚不赚」
--
-- 关键发现：高风险评级本金回收率低，但因利率高，总回款率反而更高。
-- =============================================================

WITH src AS (
    SELECT * FROM read_parquet('D:/datasets/processed/lc_accepted.parquet')
    WHERE loan_status NOT IN (
            'Does not meet the credit policy. Status:Fully Paid',
            'Does not meet the credit policy. Status:Charged Off')
      AND loan_status IS NOT NULL AND issue_d IS NOT NULL
),
b AS (
    SELECT loan_amnt, grade, int_rate,
           total_rec_prncp, total_rec_int, total_pymnt, out_prncp, recoveries
    FROM src
)
SELECT grade                                              AS 评级,
       COUNT(*)                                          AS 笔数,
       ROUND(AVG(int_rate), 2)                           AS 平均利率,
       ROUND(SUM(loan_amnt) / 1e8, 2)                    AS 放款_亿美元,
       ROUND(SUM(total_rec_prncp) / 1e8, 2)              AS 已收本金_亿美元,
       ROUND(SUM(total_rec_int) / 1e8, 2)                AS 利息收入_亿美元,
       ROUND(SUM(recoveries) / 1e6, 1)                   AS 核销后回收_百万美元,
       ROUND(SUM(out_prncp) / 1e8, 2)                    AS 未偿本金_亿美元,
       ROUND(SUM(total_rec_prncp) * 100.0 / SUM(loan_amnt), 2) AS 本金回收率,
       ROUND(SUM(total_pymnt) * 100.0 / SUM(loan_amnt), 2)     AS 总回款率
FROM b
GROUP BY grade
ORDER BY grade;
