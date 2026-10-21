#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""score_rank / batch_line 统一重导 (pymysql显式utf8mb4, 修复docker管道乱码).
交叉校验: 2024文600=1985/521=25688; 2025物理427=348358; 2025历史471=90174 (河南省考试院公布口径)
"""
import os
import re
import sys

import pymysql

PW = os.environ.get('MYSQL_PASSWORD', '')
def conn():
    return pymysql.connect(host='127.0.0.1', port=3306, user='root', password=PW,
                           database='gaokao_platform', charset='utf8mb4')


def parse_html(path):
    html = open(path, encoding='utf-8', errors='ignore').read()
    trs = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S)
    seg = []
    for tr in trs:
        tds = [re.sub(r'<[^>]+>', '', c).strip()
               for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S)]
        m = re.match(r'^(\d{3})', tds[0]) if tds else None
        if len(tds) < 3 or not m:
            continue
        sc, cnt, cum = int(m.group(1)), int(tds[1]), int(tds[2])
        if 100 <= sc <= 750 and cum > 0:
            seg.append((sc, cnt, cum))
    seg.sort(key=lambda t: -t[0])
    fixed = []
    for sc, cnt, cum in seg:
        if fixed and cum <= fixed[-1][2]:
            continue
        fixed.append((sc, cnt, cum))
    return fixed


def check(seg, score, expect, label):
    d = dict((s, c) for s, n, c in seg)
    got = d.get(score)
    ok = got is not None and abs(got - expect) <= 2
    print('  check %s: cum@%d=%s expect %s -> %s' % (label, score, got, expect, 'OK' if ok else 'FAIL'))
    return ok


def main():
    jobs = [
        (2024, '文', 'data/raw/henan_2024_wenke.html',
         [(600, 1985), (521, 25688)]),
        (2025, '物理', 'data/raw/henan2025_wuli.html',
         [(427, 348358), (600, 45887)]),
        (2025, '历史', 'data/raw/henan2025_lishi.html',
         [(471, 90174), (600, 6178)]),
    ]
    c = conn()
    cur = c.cursor()
    cur.execute("DELETE FROM score_rank")
    print('cleared score_rank')
    nid = 900000
    all_ok = True
    for year, st, path, checks in jobs:
        seg = parse_html(path)
        print(year, st, 'rows=', len(seg))
        if len(seg) < 200:
            print('FATAL too few rows in', path)
            sys.exit(1)
        for score, expect in checks:
            if not check(seg, score, expect, '%d%s' % (year, st)):
                all_ok = False
        if not all_ok:
            print('FATAL cross-check failed')
            sys.exit(1)
        prev = 0
        for sc, cnt, cum in seg:
            same = max(cum - prev, 0)
            prev = cum
            cur.execute("INSERT INTO score_rank (id,province_id,year,subject_type,score,same_count,cum_count) "
                        "VALUES (%s,41,%s,%s,%s,%s,%s)", (nid, year, st, sc, same, cum))
            nid += 1
        print('  inserted', len(seg))
    cur.execute("DELETE FROM batch_line")
    for i, (year, st, batch, line) in enumerate([
            (2024, '文', '本科一批', 521), (2024, '文', '本科二批', 428),
            (2024, '理', '本科一批', 511), (2024, '理', '本科二批', 396),
            (2025, '物理', '特殊类型招生控制线', 535), (2025, '物理', '本科批', 427),
            (2025, '历史', '特殊类型招生控制线', 552), (2025, '历史', '本科批', 471),
            (2025, '物理', '专科批', 185), (2025, '历史', '专科批', 185)]):
        cur.execute("INSERT INTO batch_line (id,province_id,year,subject_type,batch,line_score) "
                    "VALUES (%s,41,%s,%s,%s,%s)", (i + 1, year, st, batch, line))
    c.commit()
    cur.execute("SELECT year, subject_type, COUNT(*) n, MAX(cum_count) top FROM score_rank "
                "GROUP BY year, subject_type ORDER BY year, subject_type")
    for r in cur.fetchall():
        print(r)
    c.close()
    print('ALL_OK' if all_ok else 'CHECK_FAILED')


if __name__ == '__main__':
    main()
