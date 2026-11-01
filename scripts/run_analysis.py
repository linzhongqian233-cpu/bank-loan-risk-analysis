# -*- coding: utf-8 -*-
"""银行贷款风险分析 —— 全流程分析脚本

数据：Lending Club accepted loans 2007-06 ~ 2018-12（2,260,701 笔）
前置：D:/datasets/processed/lc_accepted.parquet

产出：
  reports/figures/*.png      图表
  reports/tables/*.csv       数据表（供看板使用）
  console                    关键指标
"""
import duckdb
import os
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import PARQUET, OBS_END, FIGURES, TABLES

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

FIG = FIGURES
TAB = TABLES
os.makedirs(FIG, exist_ok=True)
os.makedirs(TAB, exist_ok=True)

P = PARQUET

# ------------------------------------------------------------------
# 清洗视图
#   - 排除 "Does not meet the credit policy" 特殊样本
#   - issue_d / last_pymnt_d 格式为 Mon-YYYY
#   - bad = Charged Off / Default
#   - mob (month on book)：放款月 → 最后还款月，作为违约发生时点近似
# ------------------------------------------------------------------
BASE = f"""
WITH src AS (
    SELECT * FROM {P}
    WHERE loan_status NOT IN (
        'Does not meet the credit policy. Status:Fully Paid',
        'Does not meet the credit policy. Status:Charged Off'
    )
      AND loan_status IS NOT NULL
      AND issue_d IS NOT NULL
),
clean AS (
    SELECT
        CAST(id AS VARCHAR)                    AS loan_id,
        loan_amnt, funded_amnt, int_rate, term, grade, sub_grade,
        purpose, home_ownership, annual_inc, dti, emp_length,
        loan_status,
        strptime(issue_d, '%b-%Y')::DATE       AS issue_date,
        CASE WHEN last_pymnt_d IS NULL OR last_pymnt_d = '' THEN NULL
             ELSE strptime(last_pymnt_d, '%b-%Y')::DATE END AS last_pymnt_date,
        total_rec_prncp, total_rec_int, total_pymnt, out_prncp, recoveries,
        CASE WHEN loan_status IN ('Charged Off','Default') THEN 1 ELSE 0 END AS is_bad,
        CASE WHEN loan_status IN ('Fully Paid','Charged Off','Default') THEN 1 ELSE 0 END AS is_closed
    FROM src
)
SELECT * FROM clean
"""

# 账龄：放款月 → (违约贷款的)最后还款月 或 观测截止（OBS_END 来自 common.py）
BASE2 = f"""
WITH b AS ({BASE})
SELECT *,
       date_diff('month', issue_date, COALESCE(last_pymnt_date, {OBS_END})) AS mob
FROM b
"""


def q(sql):
    return duckdb.sql(sql).df()


print("=" * 78)
print("【0】数据概览")
print("=" * 78)
print(q(f"""
WITH b AS ({BASE})
SELECT COUNT(*) AS 有效笔数,
       ROUND(SUM(loan_amnt)/1e8, 2) AS 放款总额_亿美元,
       SUM(is_bad) AS 坏账笔数,
       ROUND(SUM(is_bad)*100.0/COUNT(*), 2) AS 静态不良率_百分比,
       ROUND(SUM(is_closed)*100.0/COUNT(*), 2) AS 已结清占比,
       MIN(issue_date) AS 最早放款, MAX(issue_date) AS 最晚放款
FROM b
""").to_string(index=False))

# ------------------------------------------------------------------
print("\n" + "=" * 78)
print("【1】风险分层：各 grade 的不良率")
print("=" * 78)
seg = q(f"""
WITH b AS ({BASE})
SELECT grade AS 评级,
       COUNT(*) AS 笔数,
       ROUND(AVG(int_rate), 2) AS 平均利率,
       ROUND(AVG(loan_amnt), 0) AS 平均金额,
       ROUND(AVG(dti), 1) AS 平均DTI,
       SUM(is_bad) AS 坏账笔数,
       ROUND(SUM(is_bad)*100.0/COUNT(*), 2) AS 不良率
FROM b GROUP BY grade ORDER BY grade
""")
print(seg.to_string(index=False))
seg.to_csv(os.path.join(TAB, "01_grade_default_rate.csv"), index=False, encoding="utf-8-sig")

fig, ax1 = plt.subplots(figsize=(9, 4.8))
ax1.bar(seg["评级"], seg["不良率"], color="#C44E52", alpha=.85, label="不良率(%)")
ax1.set_ylabel("不良率 (%)", color="#C44E52")
ax1.tick_params(axis="y", labelcolor="#C44E52")
ax2 = ax1.twinx()
ax2.plot(seg["评级"], seg["平均利率"], marker="o", color="#4C78A8", label="平均利率(%)")
ax2.set_ylabel("平均利率 (%)", color="#4C78A8")
ax2.tick_params(axis="y", labelcolor="#4C78A8")
ax1.set_title("Lending Club · 各评级不良率与平均利率（2007–2018）", fontsize=13)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "01_grade_default_rate.png"), dpi=140)
plt.close(fig)

# ------------------------------------------------------------------
print("\n" + "=" * 78)
print("【2】Vintage 账龄分析（核心）")
print("     口径：仅统计观测期足够长的 cohort，避免 right-censoring 低估")
print("=" * 78)
# 各 cohort 的样本量与观测月数
coh = q(f"""
WITH b AS ({BASE})
SELECT date_trunc('quarter', issue_date)::DATE AS 放款季度,
       COUNT(*) AS 笔数,
       MIN(date_diff('month', issue_date, {OBS_END})) AS 可观测月数,
       SUM(is_bad) AS 坏账
FROM b GROUP BY 放款季度 ORDER BY 放款季度
""")
print(f"共 {len(coh)} 个季度 cohort，放款季度范围 {coh['放款季度'].iloc[0]} ~ {coh['放款季度'].iloc[-1]}")

# MOB 累积不良率矩阵：行=季度，列=账龄(6/12/24/36)
vint = q(f"""
WITH b AS ({BASE2}),
agg AS (
  -- 观测月数必须按 cohort 统一计算（放款季度首日 → 观测截止），
  -- 不能用 MIN(mob)：那样会取到「当月即还款」的 0，导致全部失效
  SELECT date_trunc('quarter', issue_date)::DATE AS cohort,
         COUNT(*) AS n,
         date_diff('month', date_trunc('quarter', issue_date)::DATE, DATE '2018-12-01') AS max_obs,
         SUM(CASE WHEN is_bad=1 AND mob <= 6  THEN 1 ELSE 0 END) AS bad_6,
         SUM(CASE WHEN is_bad=1 AND mob <= 12 THEN 1 ELSE 0 END) AS bad_12,
         SUM(CASE WHEN is_bad=1 AND mob <= 24 THEN 1 ELSE 0 END) AS bad_24,
         SUM(CASE WHEN is_bad=1 AND mob <= 36 THEN 1 ELSE 0 END) AS bad_36
  FROM b GROUP BY cohort
)
SELECT cohort AS 放款季度, n AS 笔数, max_obs AS 可观测月数,
       CASE WHEN max_obs >= 6  THEN ROUND(bad_6 *100.0/n, 2) END AS "MOB6不良率",
       CASE WHEN max_obs >= 12 THEN ROUND(bad_12*100.0/n, 2) END AS "MOB12不良率",
       CASE WHEN max_obs >= 24 THEN ROUND(bad_24*100.0/n, 2) END AS "MOB24不良率",
       CASE WHEN max_obs >= 36 THEN ROUND(bad_36*100.0/n, 2) END AS "MOB36不良率"
FROM agg ORDER BY 放款季度
""")
print(vint.tail(12).to_string(index=False))
vint.to_csv(os.path.join(TAB, "02_vintage_matrix.csv"), index=False, encoding="utf-8-sig")

# Vintage 曲线（只取观测充分的季度）
plot_df = vint.dropna(subset=["MOB12不良率"]).copy()
if len(plot_df) > 0:
    xs = np.arange(len(plot_df))
    fig, ax = plt.subplots(figsize=(11, 5))
    for col, color in [("MOB6不良率", "#72B7B2"), ("MOB12不良率", "#4C78A8"), ("MOB24不良率", "#F58518")]:
        d = plot_df.dropna(subset=[col])
        if len(d) == 0:
            continue
        ax.plot(range(len(d)), d[col], marker="o", markersize=3, linewidth=1.8, label=col, color=color)
    ax.set_xticks(range(len(plot_df)))
    ax.set_xticklabels([str(x)[:7] for x in plot_df["放款季度"]], rotation=90, fontsize=7)
    ax.set_ylabel("累计不良率 (%)")
    ax.set_xlabel("放款季度 (Vintage)")
    ax.set_title("Vintage 曲线：不同放款季度的累计不良率（按账龄）", fontsize=13)
    ax.legend()
    ax.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "02_vintage_curves.png"), dpi=140)
    plt.close(fig)

# ------------------------------------------------------------------
print("\n" + "=" * 78)
print("【3】账龄 × 状态 分布（迁徙率替代：本数据无月度状态快照）")
print("=" * 78)
mob_dist = q(f"""
WITH b AS ({BASE2})
SELECT CASE
         WHEN mob < 6  THEN '00-05'
         WHEN mob < 12 THEN '06-11'
         WHEN mob < 24 THEN '12-23'
         WHEN mob < 36 THEN '24-35'
         ELSE '36+' END AS 账龄区间,
       COUNT(*) AS 笔数,
       ROUND(SUM(CASE WHEN loan_status='Fully Paid' THEN 1 ELSE 0 END)*100.0/COUNT(*),2) AS 已结清,
       ROUND(SUM(CASE WHEN loan_status='Current' THEN 1 ELSE 0 END)*100.0/COUNT(*),2) AS 在还中,
       ROUND(SUM(CASE WHEN loan_status LIKE 'Late%' OR loan_status='In Grace Period' THEN 1 ELSE 0 END)*100.0/COUNT(*),2) AS 逾期中,
       ROUND(SUM(is_bad)*100.0/COUNT(*),2) AS 已核销
FROM b GROUP BY 账龄区间 ORDER BY 账龄区间
""")
print(mob_dist.to_string(index=False))
mob_dist.to_csv(os.path.join(TAB, "03_mob_status_dist.csv"), index=False, encoding="utf-8-sig")

# ------------------------------------------------------------------
print("\n" + "=" * 78)
print("【4】回款分析（本项目增量：三个参考模板都没做）")
print("=" * 78)
rec = q(f"""
WITH b AS ({BASE})
SELECT grade AS 评级,
       ROUND(SUM(loan_amnt)/1e8, 2) AS 放款_亿美元,
       ROUND(SUM(total_rec_prncp)/1e8, 2) AS 已收本金_亿美元,
       ROUND(SUM(recoveries)/1e6, 1) AS 回收_百万美元,
       ROUND(SUM(total_rec_prncp)*100.0/SUM(loan_amnt), 2) AS 本金回收率,
       ROUND(SUM(total_pymnt)*100.0/SUM(loan_amnt), 2) AS 总回款率,
       ROUND(SUM(out_prncp)/1e8, 2) AS 未偿本金_亿美元
FROM b GROUP BY grade ORDER BY grade
""")
print(rec.to_string(index=False))
rec.to_csv(os.path.join(TAB, "04_recovery_by_grade.csv"), index=False, encoding="utf-8-sig")

fig, ax = plt.subplots(figsize=(9, 4.6))
ax.bar(rec["评级"], rec["本金回收率"], color="#54A24B", alpha=.85)
for i, v in enumerate(rec["本金回收率"]):
    ax.text(i, v + 1, f"{v:.1f}%", ha="center", fontsize=9)
ax.set_ylim(0, 115)
ax.set_ylabel("本金回收率 (%)")
ax.set_xlabel("评级")
ax.set_title("各评级本金回收率（已收本金 / 放款金额）", fontsize=13)
ax.grid(axis="y", alpha=.3)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "03_recovery_by_grade.png"), dpi=140)
plt.close(fig)

print("\n产物：")
for d in (FIG, TAB):
    for f in sorted(os.listdir(d)):
        print(f"  {os.path.join(os.path.basename(d), f)}")
