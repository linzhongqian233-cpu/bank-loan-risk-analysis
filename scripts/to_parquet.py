# -*- coding: utf-8 -*-
"""CSV → Parquet（1.56 GB → 258 MB，约 21 秒）"""
import duckdb
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA_CSV, DATA_PARQUET


def main():
    if not os.path.exists(DATA_CSV):
        print(f"[错误] 找不到 CSV: {DATA_CSV}")
        print("请设置环境变量 LC_CSV 指向 accepted_2007_to_2018Q4.csv")
        sys.exit(1)

    os.makedirs(os.path.dirname(DATA_PARQUET), exist_ok=True)

    if os.path.exists(DATA_PARQUET):
        print(f"Parquet 已存在，跳过：{DATA_PARQUET} ({os.path.getsize(DATA_PARQUET)/1024/1024:.0f} MB)")
        return

    t = time.time()
    duckdb.sql(f"""
        COPY (
            SELECT * FROM read_csv('{DATA_CSV}', header=true, sample_size=-1)
        ) TO '{DATA_PARQUET}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    print(f"完成：{DATA_PARQUET}  {os.path.getsize(DATA_PARQUET)/1024/1024:.0f} MB，"
          f"耗时 {time.time()-t:.1f} 秒")


if __name__ == "__main__":
    main()
