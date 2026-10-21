#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2024河南文科一本投档线(2份CSV)合并入库 + 2024理科一分一段(2份CSV)入库.
均来自官方数据视觉转录, 子代理已做过算术校验; 此处再做合并级校验后入库.
"""
import os
import csv
import re
import sys
import zlib

import pymysql

PW = os.environ.get('MYSQL_PASSWORD', '')
WK_CSVS = ['data/henan2024_wenke_batch1.csv', 'data/henan2024_wenke_batch2.csv']
WK_SRC = '河南省教育考试院2024河南本科一批投档线(文科,本地宝公开转载,视觉转录)'
RK_CSVS = ['data/henan2024_like_rank_batch1.csv', 'data/henan2024_like_rank_batch2.csv']


def num(s):
    s = (s or '').strip().replace(',', '')
    return int(s) if re.fullmatch(r'-?\d+', s) else None


def import_wenke(cur):
    rows = {}
    for path in WK_CSVS:
        with open(path, encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader)
            for r in reader:
                r = (r + [''] * 11)[:11]
                code, name = r[0].strip(), r[1].strip()
                if not re.fullmatch(r'\d{4}', code) or not name:
                    continue
                rec = {2024: (num(r[2]), num(r[3])), 2023: (num(r[4]), num(r[5])),
                       2022: (num(r[7]), num(r[8])), 2021: (num(r[9]), num(r[10]))}
                key = code + '|' + name
                if key in rows:
                    for y in rec:
                        if rows[key][y][0] is None and rec[y][0] is not None:
                            rows[key][y] = rec[y]
                        elif rec[y][0] is not None and rows[key][y] != rec[y]:
                            print('CONFLICT', key, y, rows[key][y], rec[y])
                            sys.exit(1)
                else:
                    rows[key] = rec
    n2024 = sum(1 for r in rows.values() if r[2024][0] is not None)
    print('wenke unique schools:', len(rows), 'with 2024 data:', n2024)
    if n2024 < 300:
        print('FATAL too few wenke rows')
        sys.exit(1)
    vals = sorted((r[2024][1], r[2024][0]) for r in rows.values()
                  if r[2024][0] is not None and r[2024][1] is not None)
    bad = sum(1 for i in range(1, len(vals)) if vals[i][1] > vals[i - 1][1])
    print('wenke monotonic violations:', bad)
    if bad > 3:
        print('FATAL monotonic')
        sys.exit(1)
    # 锚点: 郑州大学文科584/4004 (官方通稿)
    d = {}
    for key, r in rows.items():
        d[key.split('|')[1]] = r
    zd = d.get('郑州大学')
    print('郑大文科2024:', zd[2024] if zd else None)
    if not zd or zd[2024][0] != 584:
        print('FATAL anchor 郑大584')
        sys.exit(1)
    n = 0
    for key, rec in rows.items():
        name = key.split('|')[1]
        code = key.split('|')[0]
        cur.execute("SELECT id FROM school WHERE name=%s", (name,))
        got = cur.fetchone()
        if got:
            s_id = got[0]
        else:
            s_id = zlib.crc32(name.encode('utf-8')) % 2000000000
            cur.execute("INSERT IGNORE INTO school (id,name,school_code,province_id,city,school_type,level,nature) "
                        "VALUES (%s,%s,%s,0,'','未知','本科','未知')", (s_id, name, code))
        for year in (2024, 2023, 2022, 2021):
            score, rank = rec[year]
            if score is None or rank is None:
                continue
            g_id = zlib.crc32(('%s|41|%d|%sw' % (s_id, year, code)).encode()) % 9000000000000000000
            cur.execute("INSERT IGNORE INTO major_group (id,school_id,province_id,year,group_code,group_name,batch,subject_type) "
                        "VALUES (%s,%s,41,%s,%s,%s,'本科一批','文')",
                        (g_id, s_id, year, code + 'w', name))
            a_id = zlib.crc32(('adm|%d|%d' % (g_id, year)).encode()) % 9000000000000000000
            cur.execute("INSERT IGNORE INTO admission_record (id,group_id,province_id,year,subject_type,"
                        "min_score,min_rank,data_source,verify_status) "
                        "VALUES (%s,%s,41,%s,'文',%s,%s,%s,2)", (a_id, g_id, year, score, rank, WK_SRC))
            n += cur.rowcount
    print('wenke admission rows inserted:', n)


def import_like_rank(cur):
    seg = {}
    for path in RK_CSVS:
        with open(path, encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            header = next(reader)
            for r in reader:
                if len(r) < 3:
                    continue
                sc, cnt, cum = num(r[0]), num(r[1]), num(r[2])
                if sc is None or cum is None or not (100 <= sc <= 750):
                    continue
                if sc in seg and seg[sc] != (cnt, cum):
                    # 重叠分数点: 数值必须一致
                    print('RANK CONFLICT at', sc, seg[sc], (cnt, cum))
                    sys.exit(1)
                seg[sc] = (cnt, cum)
    scores = sorted(seg, reverse=True)
    print('like rank unique scores:', len(scores), 'range', scores[0], '->', scores[-1])
    # 全链单调+差分校验
    prev = 0
    for sc in scores:
        cum = seg[sc][1]
        if cum <= prev:
            print('FATAL monotonic break at', sc, cum, prev)
            sys.exit(1)
        prev = cum
    d = seg
    print('anchor 600:', d.get(600), 'expect (None,23638)内cum=23638')
    if not d.get(600) or d[600][1] != 23638:
        print('FATAL anchor 600')
        sys.exit(1)
    if not d.get(511) or d[511][1] != 130195:
        print('FATAL anchor 511')
        sys.exit(1)
    nid = 970000
    prev = 0
    for sc in scores:
        cnt, cum = seg[sc]
        same = max(cum - prev, 0)
        prev = cum
        cur.execute("INSERT IGNORE INTO score_rank (id,province_id,year,subject_type,score,same_count,cum_count) "
                    "VALUES (%s,41,2024,'理',%s,%s,%s)", (nid, sc, same, cum))
        nid += 1
    print('like rank rows inserted:', len(scores))


def main():
    c = pymysql.connect(host='127.0.0.1', port=3306, user='root', password=PW,
                        database='gaokao_platform', charset='utf8mb4')
    cur = c.cursor()
    import_like_rank(cur)
    import_wenke(cur)
    c.commit()
    cur.execute("SELECT year, subject_type, COUNT(*) FROM score_rank GROUP BY year, subject_type ORDER BY year")
    for r in cur.fetchall():
        print('rank:', r)
    cur.execute("SELECT a.year, a.subject_type, COUNT(*) FROM admission_record a "
                "GROUP BY a.year, a.subject_type ORDER BY a.year, a.subject_type")
    for r in cur.fetchall():
        print('adm:', r)
    c.close()
    print('ALL_IMPORT_OK')


if __name__ == '__main__':
    main()
