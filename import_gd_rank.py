#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""广东任意年份分数段PDF(文字层) -> score_rank 通用入库.
用法: python3 import_gd_rank.py <科类> <年份> <pdf路径> <锚点分1:锚点值1,锚点分2:锚点值2>
锚点来自考试院官方通稿数字.
"""
import os
import re
import sys

import fitz
import pymysql

PW = os.environ.get('MYSQL_PASSWORD', '')
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
            # 去掉页脚水印干扰: '广东省教育考试院' 混进数字行时剔除
            cells = [c for c in cells if c != '广东省教育考试院' and c != '广东' and c != '省教育考试院']
            idx = None
            for i, c in enumerate(cells):
                m = re.match(r'^(\d{3})(?:（.*)?$', c)
                if m and i + 2 < len(cells):
                    idx = i
                    break
            if idx is None:
                continue
            sc = int(re.match(r'^(\d{3})', cells[idx]).group(1))
            try:
                cnt = int(cells[idx + 1])
                cum = int(cells[idx + 2])
            except ValueError:
                continue
            if 100 <= sc <= 750 and cum > 0 and cnt >= 0 and sc not in seg:
                seg[sc] = (cnt, cum)
    doc.close()
    return seg


def main():
    ke, year, path = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    anchors = []
    for pair in sys.argv[4].split(','):
        sc, v = pair.split(':')
        anchors.append((int(sc), int(v)))
    seg = parse_pdf(path)
    scores = sorted(seg, reverse=True)
    print(ke, year, 'scores:', len(scores), 'range', scores[0], '->', scores[-1])
    if len(scores) < 400:
        print('FATAL too few')
        sys.exit(1)
    prev = 0
    for sc in scores:
        if seg[sc][1] < prev:
            print('FATAL monotonic at', sc)
            sys.exit(1)
        prev = seg[sc][1]
    all_ok = True
    for sc, expect in anchors:
        got = seg.get(sc, (None, None))[1]
        ok = got is not None and abs(got - expect) <= 2
        print('  anchor %d: %s expect %s -> %s' % (sc, got, expect, 'OK' if ok else 'FAIL'))
        if not ok:
            all_ok = False
    if not all_ok:
        print('FATAL anchors')
        sys.exit(1)
    c = pymysql.connect(host='127.0.0.1', port=3306, user='root', password=PW,
                        database='gaokao_platform', charset='utf8mb4')
    cur = c.cursor()
    cur.execute("DELETE FROM score_rank WHERE province_id=44 AND year=%s AND subject_type=%s", (year, ke))
    nid = 990000 + (year % 100) * 100000 + (60000 if ke == '物理' else 30000)
    prev = 0
    for sc in scores:
        cnt, cum = seg[sc]
        same = max(cum - prev, 0)
        prev = cum
        cur.execute("INSERT INTO score_rank (id,province_id,year,subject_type,score,same_count,cum_count) "
                    "VALUES (%s,44,%s,%s,%s,%s,%s)", (nid, year, ke, sc, same, cum))
        nid += 1
    c.commit()
    cur.execute("SELECT year, subject_type, COUNT(*) FROM score_rank WHERE province_id=44 GROUP BY year, subject_type")
    for r in cur.fetchall():
        print('gd rank:', r)
    c.close()
    print('IMPORT_OK')


if __name__ == '__main__':
    main()
