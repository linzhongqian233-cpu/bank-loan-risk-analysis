# 复现指南与验证记录

## 1. 环境

| 项 | 版本 |
|---|---|
| Python | 3.12 |
| duckdb | 2.0.0 |
| pandas | 3.1.0 |
| matplotlib | 3.11.2 |
| plotly | 7.1.0 |

```bash
py -m pip install -r requirements.txt
```

## 2. 数据获取

Lending Club Accepted Loans（2007-06 ～ 2018-12，226 万笔，151 字段）：

- **免登录镜像**（推荐）：Hugging Face
  `https://huggingface.co/datasets/codesignal/lending-club-loan-accepted`
  文件：`accepted_2007_to_2018Q4.csv`（约 1.56 GB）
- Kaggle 原始来源：`wordsforthewise/lending-club`（需账号）

放好后用环境变量指向：

```powershell
$env:LC_CSV     = "D:/datasets/raw/lending_club/accepted_2007_to_2018Q4.csv"
$env:LC_PARQUET = "D:/datasets/processed/lc_accepted.parquet"
```

> 不设环境变量时使用 `scripts/common.py` 里的默认路径。

## 3. 三步跑通

```powershell
py scripts/to_parquet.py      # 1.56 GB → 258 MB
py scripts/run_analysis.py    # 分层 / Vintage / 账龄状态 / 回款
py scripts/build_report.py    # 生成 docs/index.html 看板
```

## 4. 预期输出（实测记录）

| 步骤 | 输出 | 实测耗时 |
|---|---|---|
| `to_parquet.py` | 258 MB Parquet | **21.2 秒** |
| `run_analysis.py` | 3 张 PNG + 4 份 CSV | 约 20 秒 |
| `build_report.py` | `docs/index.html` 47 KB | 约 15 秒 |

**校验数字**：

| 指标 | 预期值 |
|---|---|
| 原始行数 | 2,260,701 |
| 有效笔数 | **2,257,919**（剔除 2,782）|
| 放款总额 | **339.91 亿美元** |
| 静态不良率 | **11.90%** |
| Current 占比 | 38.85% |
| A 级不良率 | **3.28%** |
| G 级不良率 | **38.08%** |
| 2007Q4 cohort MOB24 | **15.51%** |

## 5. SQL 单独执行

`sql/01~05.sql` 为 DuckDB 语法，可直接用 DuckDB CLI 或 Python 运行：

```python
import duckdb
print(duckdb.sql(open('sql/03_vintage.sql', encoding='utf-8').read()).df())
```

| 文件 | 内容 | 实测 |
|---|---|---|
| `01_clean.sql` | 清洗规则 + 数据质量检查 | ✅ |
| `02_segmentation.sql` | 评级分层不良率 + 粗利差 | ✅ 7 行 |
| `03_vintage.sql` | **Vintage 矩阵（核心）** | ✅ 47 行 |
| `04_mob_status.sql` | 账龄 × 状态分布 | ✅ 5 行 |
| `05_recovery.sql` | 回款构成与回收率 | ✅ 7 行 |

## 6. 常见问题

| 现象 | 原因 | 解决 |
|---|---|---|
| `Vintage 全部是 NaN` | 观测月数用了 `MIN(mob)`，取到"当月即还款"的 0 | 改为按 cohort 计算「季度首日 → 观测截止」 |
| `Could not convert string '' to DOUBLE` | 数值列（如 `dti`）与空字符串比较 | 数值列只用 `IS NULL` 判断 |
| `issue_d` 解析失败 | 格式是 `Dec-2015` 而不是标准日期 | `strptime(issue_d, '%b-%Y')` |
| 静态不良率偏低 | 分母含 38.85% 的 Current | 用 Vintage 账龄截断，或单独统计已结清部分 |
| 看板图空白 | `cdn.plot.ly` 被墙 | 页面自带本地 fallback（`docs/plotly.min.js`）|

## 7. 已验证清单

- [x] `to_parquet.py` 可独立运行，重复运行跳过
- [x] `run_analysis.py` 输出与已提交图表一致
- [x] `build_report.py` 可重建 47 KB 看板
- [x] 5 个 SQL 文件全部执行通过
- [x] 看板在 GitHub Pages 可访问（HTTP 200）
- [x] 脚本路径支持环境变量覆盖（`LC_CSV` / `LC_PARQUET`）
- [ ] 换机器从零复现（需重新下载 1.56 GB，未做端到端验证）
