#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""广东省2024分数段统计表(考试院官方PDF, 有文字层) -> score_rank 入库.
结构: 每页两栏并排: 本科(分数|分数段人数|累计人数) + 专科(同). 取本科栏.
锚点: 物理600+ = 22216, 本科线442 -> 253795; 历史600+ = 3046, 428 -> 96266 (官方通稿)
"""
import os
import glob
import re
import sys

import fitz
import pymysql

PW = os.environ.get('MYSQL_PASSWORD', '')
JOBS = [
    ('物理', 'data/raw/eea_2024_fd/2.广东省2024年高考普通类（物理）分数段统计表（含本、专科层次加分）.pdf',
     [(600, 22216), (442, 253795)]),
    ('历史', 'data/raw/eea_2024_fd/1.广东省2024年高考普通类（历史）分数段统计表（含本、专科层次加分）.pdf',
     [(600, 3046), (428, 96266)]),
]


def parse_pdf(path):
    doc = fitz.open(path)
    seg = {}
    for page in doc:
        words = page.get_text('words')
        rows = {}
        for w in words:
            key = round(w[1] / 8)
            rows.setdefault(key, []).append((w[0], w[4]))
        for key in sorted(rows):
            cells = [t for _, t in sorted(rows[key])]
            # 找以数字开头的分数单元格(如 695（含以上）/664)
            idx = None
            for i, c in enumerate(cells):
                m = re.match(r'^(\d{3})(?:（.*)?$', c)
                if m and i + 2 < len(cells):
                    idx = i
                    break
            if idx is None:
                continue
            m = re.match(r'^(\d{3})', cells[idx])
            sc = int(m.group(1))
            try:
                cnt = int(cells[idx + 1])
                cum = int(cells[idx + 2])
            except ValueError:
                continue
            if 100 <= sc <= 750 and cum > 0 and cnt >= 0:
                # 本科栏优先(前半页); 重复分数以先出现的为准
                if sc not in seg:
                    seg[sc] = (cnt, cum)
    doc.close()
    return seg


def main():
    c = pymysql.connect(host='127.0.0.1', port=3306, user='root', password=PW,
                        database='gaokao_platform', charset='utf8mb4')
    cur = c.cursor()
    # 清掉广东2024旧分段(若有)保证幂等
    cur.execute("DELETE FROM score_rank WHERE province_id=44 AND year=2024")
    nid = 990000
    all_ok = True
    for ke, path, anchors in JOBS:
        seg = parse_pdf(path)
        scores = sorted(seg, reverse=True)
        print(ke, 'parsed scores:', len(scores), 'range', scores[0], '->', scores[-1])
        if len(scores) < 400:
            print('FATAL too few')
            sys.exit(1)
        # 单调
        prev = 0
        for sc in scores:
            if seg[sc][1] <= prev:
                print('FATAL monotonic at', sc)
                sys.exit(1)
            prev = seg[sc][1]
        # 锚点
        d = seg
        for sc, expect in anchors:
            got = d.get(sc, (None, None))[1]
            ok = got is not None and abs(got - expect) <= 2
            print('  anchor %d: %s expect %s -> %s' % (sc, got, expect, 'OK' if ok else 'FAIL'))
            if not ok:
                all_ok = False
        if not all_ok:
            print('FATAL anchor failed')
            sys.exit(1)
        prev = 0
        for sc in scores:
            cnt, cum = seg[sc]
            same = max(cum - prev, 0)
            prev = cum
            cur.execute("INSERT INTO score_rank (id,province_id,year,subject_type,score,same_count,cum_count) "
                        "VALUES (%s,44,2024,%s,%s,%s,%s)", (nid, ke, sc, same, cum))
            nid += 1
        print('  inserted', len(scores))
    c.commit()
    cur.execute("SELECT year, subject_type, COUNT(*) FROM score_rank WHERE province_id=44 "
                "GROUP BY year, subject_type")
    for r in cur.fetchall():
        print('gd rank:', r)
    c.close()
    print('GD_RANK_2024_OK')


if __name__ == '__main__':
    main()
