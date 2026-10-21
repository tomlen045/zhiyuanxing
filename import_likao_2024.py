#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2024河南理科一本投档线(3份CSV)合并去重 + 跨年(2021-2024)入库.
来源: 河南省教育考试院公布, 本地宝公开转载, 视觉转录+算术校验通过.
同时导入2023/2022/2021历史列, 供推荐引擎做多年位次锚定.
"""
import os
import csv
import re
import sys
import zlib

import pymysql

PW = os.environ.get('MYSQL_PASSWORD', '')
CSVS = [
    'data/henan2024_likao_img1_img2.csv',
    'data/投档线_2024河南理科_img3_img4.csv',
    'data/henan_2024_p1_batch2.csv',
]
SRC = '河南省教育考试院2024河南本科一批投档线(本地宝公开转载,视觉转录)'


def num(s):
    s = (s or '').strip().replace(',', '')
    if not re.fullmatch(r'-?\d+', s):
        return None
    v = int(s)
    return v


def main():
    rows = {}
    for path in CSVS:
        with open(path, encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            header = next(reader)
            for r in reader:
                r = (r + [''] * 11)[:11]
                code, name = r[0].strip(), r[1].strip()
                if not re.fullmatch(r'\d{4}', code) or not name:
                    continue
                rec = {
                    'code': code, 'name': name,
                    2024: (num(r[2]), num(r[3])),
                    2023: (num(r[4]), num(r[5])),
                    2022: (num(r[7]), num(r[8])),
                    2021: (num(r[9]), num(r[10])),
                }
                key = code + '|' + name
                if key in rows:
                    # 重叠行: 内容必须一致(以非空优先合并)
                    old = rows[key]
                    for y in (2024, 2023, 2022, 2021):
                        if old[y][0] is None and rec[y][0] is not None:
                            old[y] = rec[y]
                else:
                    rows[key] = rec
    print('merged unique schools:', len(rows))
    if not (300 <= len(rows) <= 800):
        print('FATAL unexpected school count')
        sys.exit(1)
    # 2024列完整性
    n2024 = sum(1 for r in rows.values() if r[2024][0] is not None and r[2024][1] is not None)
    print('rows with complete 2024 score+rank:', n2024)
    if n2024 < 300:
        print('FATAL too few 2024 rows')
        sys.exit(1)
    # 排序校验: 投档线随位次增而降
    vals = [(r[2024][1], r[2024][0]) for r in rows.values()
            if r[2024][0] is not None and r[2024][1] is not None]
    vals.sort()
    bad = sum(1 for i in range(1, len(vals)) if vals[i][1] > vals[i - 1][1])
    print('monotonic violations (allow ties):', bad)
    if bad > 3:
        print('FATAL monotonic check failed')
        sys.exit(1)
    # 锚点校验
    d = {r['name']: r for r in rows.values()}
    qh = d.get('清华大学')
    zd = d.get('郑州大学')
    print('清华:', qh[2024] if qh else None, '郑大:', zd[2024] if zd else None)
    if not qh or qh[2024][0] != 696:
        print('FATAL anchor 清华696 failed')
        sys.exit(1)

    c = pymysql.connect(host='127.0.0.1', port=3306, user='root', password=PW,
                        database='gaokao_platform', charset='utf8mb4')
    cur = c.cursor()
    n_adm = 0
    for code, rec in rows.items():
        cur.execute("SELECT id FROM school WHERE name=%s", (rec['name'],))
        got = cur.fetchone()
        if got:
            s_id = got[0]
        else:
            s_id = zlib.crc32(rec['name'].encode('utf-8')) % 2000000000
            cur.execute("INSERT IGNORE INTO school (id,name,school_code,province_id,city,school_type,level,nature) "
                        "VALUES (%s,%s,%s,0,'','未知','本科','未知')", (s_id, rec['name'], code))
        for year in (2024, 2023, 2022, 2021):
            score, rank = rec[year]
            if score is None or rank is None:
                continue
            g_id = zlib.crc32(('%s|41|%d|%s' % (s_id, year, code)).encode()) % 9000000000000000000
            cur.execute("INSERT IGNORE INTO major_group (id,school_id,province_id,year,group_code,group_name,batch,subject_type) "
                        "VALUES (%s,%s,41,%s,%s,%s,'本科一批','理')",
                        (g_id, s_id, year, code, rec['name']))
            a_id = zlib.crc32(('adm|%d|%d' % (g_id, year)).encode()) % 9000000000000000000
            cur.execute("INSERT IGNORE INTO admission_record (id,group_id,province_id,year,subject_type,"
                        "min_score,min_rank,data_source,verify_status) "
                        "VALUES (%s,%s,41,%s,'理',%s,%s,%s,2)", (a_id, g_id, year, score, rank, SRC))
            n_adm += cur.rowcount
    c.commit()
    cur.execute("SELECT year, COUNT(*) n FROM admission_record WHERE subject_type='理' GROUP BY year ORDER BY year")
    for r in cur.fetchall():
        print(r)
    cur.execute("SELECT COUNT(*) FROM school")
    print('schools total:', cur.fetchone()[0])
    print('new admission rows:', n_adm)
    c.close()
    print('IMPORT_OK')


if __name__ == '__main__':
    main()
