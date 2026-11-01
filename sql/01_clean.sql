-- =============================================================
-- 01 数据清洗与质量检查（DuckDB 语法）
-- 数据：D:/datasets/processed/lc_accepted.parquet
--
-- 清洗规则：
--   1. 排除 "Does not meet the credit policy.*"（政策外样本 2,749 条）
--   2. 排除 loan_status 为空（33 条）
--   3. issue_d / last_pymnt_d 格式为 Mon-YYYY，用 strptime 解析
--   4. is_bad = Charged Off / Default
--   5. mob（账龄）= 放款月 → 最后还款月；未结清则至观测截止 2018-12
-- =============================================================

WITH src AS (
    SELECT * FROM read_parquet('D:/datasets/processed/lc_accepted.parquet')
),
filtered AS (
    SELECT *
    FROM src
    WHERE loan_status NOT IN (
            'Does not meet the credit policy. Status:Fully Paid',
            'Does not meet the credit policy. Status:Charged Off')
      AND loan_status IS NOT NULL
      AND issue_d IS NOT NULL
)
SELECT
    -- 规模
    COUNT(*)                                        AS 有效笔数,
    (SELECT COUNT(*) FROM src)                       AS 原始笔数,
    (SELECT COUNT(*) FROM src) - COUNT(*)            AS 剔除笔数,
    ROUND(SUM(loan_amnt) / 1e8, 2)                   AS 放款总额_亿美元,
    MIN(strptime(issue_d, '%b-%Y')::DATE)            AS 最早放款,
    MAX(strptime(issue_d, '%b-%Y')::DATE)            AS 最晚放款,
    -- 目标变量
    SUM(CASE WHEN loan_status IN ('Charged Off', 'Default') THEN 1 ELSE 0 END) AS 坏账笔数,
    ROUND(SUM(CASE WHEN loan_status IN ('Charged Off', 'Default') THEN 1 ELSE 0 END)
          * 100.0 / COUNT(*), 2)                     AS 静态不良率,
    -- 数据陷阱提示：Current 占比越高，静态不良率越低估真实风险
    ROUND(SUM(CASE WHEN loan_status = 'Current' THEN 1 ELSE 0 END)
          * 100.0 / COUNT(*), 2)                     AS 在还中占比,
    -- 关键字段缺失率
    ROUND(SUM(CASE WHEN dti IS NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 3) AS dti缺失率,
    ROUND(SUM(CASE WHEN total_rec_prncp IS NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 3) AS 回收本金缺失率,
    ROUND(SUM(CASE WHEN member_id IS NULL OR member_id = '' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS member_id缺失率
FROM filtered;
