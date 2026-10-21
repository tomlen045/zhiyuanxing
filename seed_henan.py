#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""河南2024一分一段(文科)采集入库. 来源: 河南省教育考试院2024-06-25发布, 教育在线转载."""
import os
import re
import subprocess
import sys

PW = os.environ.get('MYSQL_PASSWORD', '')
RAW = 'data/raw/henan_2024_wenke.html'


def run_sql(sql):
    cmd = ['docker', 'exec', '-i', 'gaokao-mysql', 'mysql', '-uroot', '-p' + PW,
           'gaokao_platform', '-e', sql]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print('SQL_ERROR:', r.stderr.strip()[:400])
        sys.exit(1)
    return r.stdout


def parse(html):
    trs = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S)
    seg = []
    for tr in trs:
        tds = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S)
        cells = [re.sub(r'<[^>]+>', '', c).strip() for c in tds]
        if len(cells) < 3 or not re.fullmatch(r'\d{3}', cells[0]):
            continue
        sc, cnt, cum = int(cells[0]), int(cells[1]), int(cells[2])
        if 100 <= sc <= 750 and cum > 0:
            seg.append((sc, cnt, cum))
    seg.sort(key=lambda t: -t[0])
    fixed = []
    for sc, cnt, cum in seg:
        if fixed and cum <= fixed[-1][2]:
            continue
        fixed.append((sc, cnt, cum))
    return fixed


def main():
    html = open(RAW, encoding='utf-8', errors='ignore').read()
    seg = parse(html)
    print('parsed_rows=', len(seg))
    if len(seg) < 50:
        print('FATAL too few rows')
        sys.exit(1)
    cum600 = [c for s, n, c in seg if s == 600]
    print('cum_at_600=', cum600, '(expect 1985 per official release)')
    if not cum600 or abs(cum600[0] - 1985) > 2:
        print('FATAL cross-check at 600 failed')
        sys.exit(1)

    run_sql("INSERT IGNORE INTO province (id,name,region,exam_mode,batch_count) "
            "VALUES (41,'河南','华中','老文理',2)")

    vals = []
    prev = 0
    for i, (sc, cnt, cum) in enumerate(seg, 1):
        same = cum - prev
        prev = cum
        if same < 0:
            same = 0
        vals.append("({},41,2024,'文',{},{},{})".format(900000 + i, sc, same, cum))
    sql = ("INSERT IGNORE INTO score_rank (id,province_id,year,subject_type,score,same_count,cum_count) VALUES "
           + ','.join(vals) + ';')
    run_sql(sql)
    print('imported score_rank rows:', len(vals))

    run_sql("INSERT IGNORE INTO batch_line (id,province_id,year,subject_type,batch,line_score) VALUES "
            "(1,41,2024,'文','本科一批',521),(2,41,2024,'文','本科二批',428),"
            "(3,41,2024,'理','本科一批',511),(4,41,2024,'理','本科二批',396)")

    print(run_sql("SELECT COUNT(*) AS n, MIN(score) AS lo, MAX(score) AS hi FROM score_rank "
                  "WHERE province_id=41 AND year=2024 AND subject_type='文'").strip())
    print(run_sql("SELECT score,cum_count FROM score_rank WHERE province_id=41 AND year=2024 "
                  "AND subject_type='文' AND score IN (600,521,511) ORDER BY score DESC").strip())
    print('VERIFY_BATCH_LINES:')
    print(run_sql("SELECT id,batch,line_score FROM batch_line WHERE year=2024").strip())


if __name__ == '__main__':
    main()
