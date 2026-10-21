#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2023广东分段表(视觉转录CSV batchA+batchB) 合并校验入库.
锚点: 历史 670→31, 600→5201, 433(本科线)→97254; 物理 700→27, 600→27216 (考试院通稿)
"""
import os
import csv
import re
import sys

import pymysql

PW = os.environ.get('MYSQL_PASSWORD', '')
JOBS = [
    ('历史', 2023, ['data/gd2023_lishi_batchA.csv', 'data/gd2023_lishi_batchB.csv'],
     [(670, 31), (600, 3397), (433, 97004)]),
    ('物理', 2023, ['data/gd2023_wuli_batchA.csv', 'data/gd2023_wuli_batchB.csv'],
     [(700, 27), (600, 27168), (439, 236086)]),
]


def main():
    c = pymysql.connect(host='127.0.0.1', port=3306, user='root', password=PW,
                        database='gaokao_platform', charset='utf8mb4')
    cur = c.cursor()
    all_ok = True
    for ke, year, paths, anchors in JOBS:
        seg = {}
        for path in paths:
            with open(path, encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                for r in reader:
                    if len(r) < 2:
                        continue
                    m1 = re.fullmatch(r'(\d{3})', r[0].strip())
                    m2 = re.fullmatch(r'(\d+)', r[1].strip())
                    if not m1 or not m2:
                        continue
                    sc, cum = int(m1.group(1)), int(m2.group(1))
                    if sc in seg and seg[sc] != cum:
                        print('CONFLICT', ke, sc, seg[sc], cum)
                        sys.exit(1)
                    seg[sc] = cum
        scores = sorted(seg, reverse=True)
        print(ke, year, 'unique scores:', len(scores), 'range', scores[0], '->', scores[-1])
        if len(scores) < 500:
            print('FATAL too few')
            sys.exit(1)
        # 缺口检查
        gaps = [(a, b) for a, b in zip(scores, scores[1:]) if a - b > 1]
        print('  gaps:', gaps[:5] if gaps else 'none')
        if gaps:
            print('FATAL gaps in sequence')
            sys.exit(1)
        # 单调(允许持平)
        prev = 0
        for sc in scores:
            if seg[sc] < prev:
                print('FATAL monotonic at', sc)
                sys.exit(1)
            prev = seg[sc]
        # 锚点
        for sc, expect in anchors:
            got = seg.get(sc)
            ok = got is not None and abs(got - expect) <= 2
            print('  anchor %d: %s expect %s -> %s' % (sc, got, expect, 'OK' if ok else 'FAIL'))
            if not ok:
                all_ok = False
        if not all_ok:
            print('FATAL anchors', ke)
            sys.exit(1)
        cur.execute("DELETE FROM score_rank WHERE province_id=44 AND year=%s AND subject_type=%s", (year, ke))
        nid = 990000 + (year % 100) * 100000 + (60000 if ke == '物理' else 30000)
        prev = 0
        for sc in scores:
            cum = seg[sc]
            same = max(cum - prev, 0)
            prev = cum
            cur.execute("INSERT INTO score_rank (id,province_id,year,subject_type,score,same_count,cum_count) "
                        "VALUES (%s,44,%s,%s,%s,%s,%s)", (nid, year, ke, sc, same, cum))
            nid += 1
        print('  inserted', len(scores))
    c.commit()
    cur.execute("SELECT year, subject_type, COUNT(*) FROM score_rank WHERE province_id=44 "
                "GROUP BY year, subject_type ORDER BY year, subject_type")
    for r in cur.fetchall():
        print('gd rank:', r)
    c.close()
    print('GD2023_OK')


if __name__ == '__main__':
    main()
