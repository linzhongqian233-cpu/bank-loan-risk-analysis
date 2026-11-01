# -*- coding: utf-8 -*-
"""统一路径配置

换机器复现时用环境变量覆盖：
    $env:LC_CSV     = "D:/data/accepted_2007_to_2018Q4.csv"
    $env:LC_PARQUET = "D:/data/lc_accepted.parquet"
"""
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_CSV = os.environ.get("LC_CSV", "D:/datasets/raw/lending_club/accepted_2007_to_2018Q4.csv")
DATA_PARQUET = os.environ.get("LC_PARQUET", "D:/datasets/processed/lc_accepted.parquet")

REPORTS = os.path.join(PROJECT_ROOT, "reports")
FIGURES = os.path.join(REPORTS, "figures")
TABLES = os.path.join(REPORTS, "tables")
DOCS = os.path.join(PROJECT_ROOT, "docs")

# 观测截止月（数据最后一个月），用于计算账龄与 Vintage 观测窗口
OBS_END = "DATE '2018-12-01'"

PARQUET = f"read_parquet('{DATA_PARQUET}')"
