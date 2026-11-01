# -*- coding: utf-8 -*-
"""生成风控报表风格看板（Plotly，独立 HTML，内嵌 JS）

与项目一（ECharts 卡片式）不同：
  - 技术栈换成 Plotly
  - 视觉范式换成「风险报表」：以 Vintage 热力图矩阵为主角
  - 深色金融风配色，适合放信贷风险内容

输出：docs/index.html（GitHub Pages 直接以 /docs 为站点根）
"""
import duckdb
import os
import sys
import json
import plotly.graph_objects as go
from plotly.subplots import make_subplots

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import PARQUET, OBS_END, DOCS

OUT = os.path.join(DOCS, "index.html")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

P = PARQUET

BASE = f"""
WITH src AS (
    SELECT * FROM {P}
    WHERE loan_status NOT IN (
        'Does not meet the credit policy. Status:Fully Paid',
        'Does not meet the credit policy. Status:Charged Off')
      AND loan_status IS NOT NULL AND issue_d IS NOT NULL
),
clean AS (
    SELECT CAST(id AS VARCHAR) AS loan_id, loan_amnt, int_rate, grade,
           loan_status,
           strptime(issue_d,'%b-%Y')::DATE AS issue_date,
           CASE WHEN last_pymnt_d IS NULL OR last_pymnt_d='' THEN NULL
                ELSE strptime(last_pymnt_d,'%b-%Y')::DATE END AS last_pymnt_date,
           total_rec_prncp, total_rec_int, total_pymnt, out_prncp, recoveries,
           CASE WHEN loan_status IN ('Charged Off','Default') THEN 1 ELSE 0 END AS is_bad
    FROM src
),
b AS (
    SELECT *,
      date_diff('month', issue_date, COALESCE(last_pymnt_date, {OBS_END})) AS mob
    FROM clean
)
SELECT * FROM b
"""

# ---------------- 1. Vintage 热力图矩阵 ----------------
KS = list(range(3, 37, 3))
cols = ",\n".join(
    f"SUM(CASE WHEN is_bad=1 AND mob<={k} THEN 1 ELSE 0 END) AS b{k}" for k in KS
)
vt = duckdb.sql(f"""
WITH b AS ({BASE}),
agg AS (
  SELECT date_trunc('quarter', issue_date)::DATE AS cohort,
         COUNT(*) AS n,
         date_diff('month', date_trunc('quarter', issue_date)::DATE, {OBS_END}) AS age,
         {cols}
  FROM b GROUP BY cohort
)
SELECT * FROM agg ORDER BY cohort
""").df()

cohorts = [str(x)[:7] for x in vt["cohort"]]
z, text = [], []
for _, row in vt.iterrows():
    rz, rt = [], []
    for k in KS:
        if row["age"] >= k and row["n"] > 0:
            v = row[f"b{k}"] * 100.0 / row["n"]
            rz.append(round(v, 2))
            rt.append(f"{v:.1f}%")
        else:
            rz.append(None)
            rt.append("—")
    z.append(rz)
    text.append(rt)

fig_vintage = go.Figure(go.Heatmap(
    z=z, x=[f"MOB{k}" for k in KS], y=cohorts,
    text=text, texttemplate="%{text}",
    colorscale=[[0, "#0d1b2a"], [0.35, "#1b4965"], [0.65, "#c96f2f"], [1, "#8c1c13"]],
    colorbar=dict(title="累计不良率<br>(%)", thickness=12, len=0.85),
    hovertemplate="放款季度 %{y}<br>账龄 %{x}<br>累计不良率 %{text}<extra></extra>",
    xgap=1, ygap=1,
))
fig_vintage.update_layout(
    title=dict(text="Vintage 累计不良率矩阵（仅显示观测充分的格子）", font=dict(size=15, color="#e8eef5")),
    height=760, margin=dict(l=70, r=30, t=55, b=60),
    paper_bgcolor="#0d1b2a", plot_bgcolor="#0d1b2a",
    font=dict(color="#c9d6e3", size=10),
    yaxis=dict(autorange="reversed", tickfont=dict(size=9)),
    xaxis=dict(side="top"),
)

# ---------------- 2. 评级：不良率 vs 利率 ----------------
gr = duckdb.sql(f"""
WITH b AS ({BASE})
SELECT grade AS g, COUNT(*) AS n,
       ROUND(AVG(int_rate),2) AS rate,
       ROUND(SUM(is_bad)*100.0/COUNT(*),2) AS dr,
       ROUND(SUM(loan_amnt)/1e6,0) AS amt
FROM b GROUP BY g ORDER BY g
""").df()

fig_grade = make_subplots(specs=[[{"secondary_y": True}]])
fig_grade.add_trace(go.Bar(
    x=gr["g"], y=gr["dr"], name="不良率 %",
    marker_color="#c96f2f", text=[f"{v:.1f}%" for v in gr["dr"]],
    textposition="outside", textfont=dict(color="#e8eef5", size=10),
    hovertemplate="评级 %{x}<br>不良率 %{y:.2f}%<extra></extra>",
), secondary_y=False)
fig_grade.add_trace(go.Scatter(
    x=gr["g"], y=gr["rate"], name="平均利率 %", mode="lines+markers",
    line=dict(color="#5fa8d3", width=2.5), marker=dict(size=8),
    hovertemplate="评级 %{x}<br>平均利率 %{y:.2f}%<extra></extra>",
), secondary_y=True)
fig_grade.update_yaxes(title_text="不良率 (%)", secondary_y=False, gridcolor="#1b2b3d")
fig_grade.update_yaxes(title_text="平均利率 (%)", secondary_y=True, showgrid=False)
fig_grade.update_layout(
    title=dict(text="评级 × 不良率 × 定价：A→G 不良率升 11.6 倍，利率仅升 4 倍", font=dict(size=15, color="#e8eef5")),
    height=420, margin=dict(l=60, r=60, t=55, b=45),
    paper_bgcolor="#0d1b2a", plot_bgcolor="#0d1b2a",
    font=dict(color="#c9d6e3"), legend=dict(orientation="h", y=1.12, x=0),
    bargap=0.45,
)

# ---------------- 3. 回款构成（堆叠） ----------------
rc = duckdb.sql(f"""
WITH b AS ({BASE})
SELECT grade AS g,
       ROUND(SUM(total_rec_prncp)/1e8, 2)      AS 已收本金,
       ROUND(SUM(total_rec_int)/1e8, 2)        AS 利息收入,
       ROUND(SUM(recoveries)/1e8, 3)           AS 核销后回收,
       ROUND(SUM(out_prncp)/1e8, 2)            AS 未偿本金,
       ROUND(SUM(total_rec_prncp)*100.0/SUM(loan_amnt), 1) AS 本金回收率
FROM b GROUP BY g ORDER BY g
""").df()

fig_recovery = go.Figure()
for name, color in [("已收本金", "#2a9d8f"), ("利息收入", "#5fa8d3"),
                    ("核销后回收", "#e9c46a"), ("未偿本金", "#8c1c13")]:
    fig_recovery.add_trace(go.Bar(
        x=rc["g"], y=rc[name], name=name, marker_color=color,
        hovertemplate="评级 %{x}<br>" + name + " %{y:.2f} 亿美元<extra></extra>",
    ))
fig_recovery.update_layout(
    barmode="stack",
    title=dict(text="各评级资金去向：本金 / 利息 / 回收 / 未偿（亿美元）", font=dict(size=15, color="#e8eef5")),
    height=420, margin=dict(l=60, r=30, t=55, b=45),
    paper_bgcolor="#0d1b2a", plot_bgcolor="#0d1b2a",
    font=dict(color="#c9d6e3"),
    legend=dict(orientation="h", y=1.12, x=0),
    xaxis=dict(gridcolor="#1b2b3d"), yaxis=dict(gridcolor="#1b2b3d"),
)

# ---------------- 4. 账龄 × 状态 ----------------
ms = duckdb.sql(f"""
WITH b AS ({BASE})
SELECT CASE WHEN mob<6 THEN '0-5' WHEN mob<12 THEN '6-11'
            WHEN mob<24 THEN '12-23' WHEN mob<36 THEN '24-35' ELSE '36+' END AS age,
       COUNT(*) AS n,
       ROUND(SUM(CASE WHEN loan_status='Fully Paid' THEN 1 ELSE 0 END)*100.0/COUNT(*),1) AS paid,
       ROUND(SUM(CASE WHEN loan_status='Current' THEN 1 ELSE 0 END)*100.0/COUNT(*),1) AS curr,
       ROUND(SUM(CASE WHEN loan_status LIKE 'Late%' OR loan_status='In Grace Period' THEN 1 ELSE 0 END)*100.0/COUNT(*),1) AS late,
       ROUND(SUM(is_bad)*100.0/COUNT(*),1) AS bad
FROM b GROUP BY age ORDER BY age
""").df()

fig_mob = go.Figure()
for label, col, color in [("已结清", "paid", "#2a9d8f"), ("在还中", "curr", "#5fa8d3"),
                          ("逾期中", "late", "#e9c46a"), ("已核销", "bad", "#8c1c13")]:
    fig_mob.add_trace(go.Bar(
        x=ms["age"], y=ms[col], name=label, marker_color=color,
        hovertemplate="账龄 %{x} 月<br>" + label + " %{y:.1f}%<extra></extra>",
    ))
fig_mob.update_layout(
    barmode="stack",
    title=dict(text="账龄 × 贷款状态：风险集中在放款后 6–24 个月", font=dict(size=15, color="#e8eef5")),
    height=420, margin=dict(l=60, r=30, t=55, b=45),
    paper_bgcolor="#0d1b2a", plot_bgcolor="#0d1b2a",
    font=dict(color="#c9d6e3"),
    legend=dict(orientation="h", y=1.12, x=0),
    xaxis=dict(title="账龄（月）", gridcolor="#1b2b3d"), yaxis=dict(title="占比 %", gridcolor="#1b2b3d"),
)

# ---------------- KPI ----------------
kpi = duckdb.sql(f"""
WITH b AS ({BASE})
SELECT COUNT(*) AS n, ROUND(SUM(loan_amnt)/1e8,0) AS amt,
       ROUND(SUM(is_bad)*100.0/COUNT(*),2) AS dr,
       ROUND(AVG(int_rate),2) AS rate
FROM b
""").df().iloc[0]

def fig_html(fig):
    return fig.to_html(full_html=False, include_plotlyjs=False,
                       config={"displayModeBar": False, "responsive": True})

HTML = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>银行贷款风险分析 · 风控报表</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
<style>
  :root{{--bg:#0d1b2a;--panel:#111f30;--line:#1b2b3d;--ink:#e8eef5;--sub:#8fa3b8;--warn:#c96f2f;--danger:#8c1c13}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--ink);
       font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}}
  .topbar{{padding:26px 34px 20px;border-bottom:1px solid var(--line);
          background:linear-gradient(135deg,#0d1b2a 0%,#132b42 100%)}}
  .topbar h1{{margin:0 0 8px;font-size:22px;letter-spacing:.5px}}
  .topbar .meta{{color:var(--sub);font-size:12.5px}}
  .topbar .thesis{{margin-top:14px;padding:12px 16px;background:rgba(201,111,47,.1);
                 border-left:3px solid var(--warn);font-size:13.5px;line-height:1.75;color:#dbe6f0}}
  .wrap{{padding:22px 34px 60px;max-width:1500px;margin:0 auto}}
  .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin-bottom:22px}}
  .kpi{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:16px 18px}}
  .kpi .lb{{color:var(--sub);font-size:12px;margin-bottom:8px;letter-spacing:.3px}}
  .kpi .vl{{font-size:26px;font-weight:600;line-height:1.1}}
  .kpi .hint{{color:var(--sub);font-size:11.5px;margin-top:6px}}
  .panel{{background:var(--panel);border:1px solid var(--line);border-radius:8px;
         padding:16px 18px;margin-bottom:20px}}
  .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
  @media(max-width:1000px){{.grid2{{grid-template-columns:1fr}}}}
  .foot{{color:var(--sub);font-size:12px;line-height:1.9;border-top:1px solid var(--line);padding-top:18px}}
  .tag{{display:inline-block;padding:2px 8px;border-radius:3px;background:rgba(201,111,47,.18);
       color:#e0a06a;font-size:11.5px;margin-right:6px}}
</style>
</head>
<body>
<div class="topbar">
  <h1>银行贷款风险分析 · 风控报表</h1>
  <div class="meta">Lending Club Accepted Loans · 2007-06 ~ 2018-12 · {kpi.n:,.0f} 笔 · {kpi.amt:.0f} 亿美元 · DuckDB + Plotly</div>
  <div class="thesis">
    <strong>核心结论：</strong>评级从 A 到 G，不良率从 <strong>3.28%</strong> 升至 <strong>38.08%</strong>，相差 11.6 倍，而平均利率仅从 7.08% 升至 28.22%（约 4 倍）——
    <strong>风险增速快于定价增速</strong>。Vintage 矩阵显示 2007Q4 放款 24 期累计不良率达 15.5%（危机冲击），2013–2015 年降至 10.4–10.9%，
    但 2016 年起回升至 13.6%。
  </div>
</div>

<div class="wrap">
  <div class="kpis">
    <div class="kpi"><div class="lb">有效贷款笔数</div><div class="vl">{kpi.n:,.0f}</div><div class="hint">剔除 2,782 条政策外样本</div></div>
    <div class="kpi"><div class="lb">放款总额</div><div class="vl">{kpi.amt:.0f} 亿美元</div><div class="hint">2007–2018，139 个月</div></div>
    <div class="kpi"><div class="lb">静态不良率</div><div class="vl" style="color:#c96f2f">{kpi.dr:.2f}%</div><div class="hint">Charged Off + Default</div></div>
    <div class="kpi"><div class="lb">平均利率</div><div class="vl">{kpi.rate:.2f}%</div><div class="hint">A 级 7.08% / G 级 28.22%</div></div>
    <div class="kpi"><div class="lb">最差 cohort</div><div class="vl" style="color:#8c1c13">15.5%</div><div class="hint">2007Q4 · MOB24 累计不良</div></div>
  </div>

  <div class="panel">
    <span class="tag">核心图</span>
    <span style="color:#8fa3b8;font-size:12.5px">行=放款季度（Vintage），列=账龄（月），颜色=累计不良率。空格表示观测期不足，不做外推。</span>
    {fig_html(fig_vintage)}
  </div>

  <div class="grid2">
    <div class="panel">{fig_html(fig_grade)}</div>
    <div class="panel">{fig_html(fig_mob)}</div>
  </div>

  <div class="panel">{fig_html(fig_recovery)}</div>

  <div class="foot">
    <strong>数据局限：</strong>① 无月度状态快照，无法计算真正的迁徙率（Roll Rate），仅以「账龄 × 状态」近似；
    ② 38.85% 贷款处于 Current 状态，直接计算静态不良率会低估风险，故采用 Vintage 账龄截断；
    ③ <code>member_id</code> 全为空，分析单元为借款笔数而非借款人。<br>
    完整分析脚本见仓库 <code>scripts/run_analysis.py</code>，口径说明见 <code>docs/data_quality.md</code>。
  </div>
</div>
</body>
</html>
"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(HTML)

print(f"看板已生成: {OUT}  ({os.path.getsize(OUT)/1024:.0f} KB)")
print(f"Vintage 矩阵: {len(cohorts)} 个 cohort × {len(KS)} 个账龄档")
print(f"KPI: {kpi.n:,.0f} 笔 / {kpi.amt:.0f} 亿美元 / 不良率 {kpi.dr:.2f}%")
