# -*- coding: utf-8 -*-
"""CSV -> Parquet（1.56 GB -> 258 MB，约 21 秒）"""
import duckdb, os, time

SRC = "read_csv('D:/datasets/raw/lending_club/accepted_2007_to_2018Q4.csv', header=true, sample_size=-1)"
DST = 'D:/datasets/processed/lc_accepted.parquet'

os.makedirs(os.path.dirname(DST), exist_ok=True)
if os.path.exists(DST):
    print('已存在，跳过')
else:
    t = time.time()
    duckdb.sql(f"COPY (SELECT * FROM {SRC}) TO '{DST}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    print(f'完成: {os.path.getsize(DST)/1024/1024:.0f} MB, {time.time()-t:.1f} 秒')
