#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""院校/专业组/2025河南专业组录取线入库. 来源: gk100转载河南省教育考试院2025录取数据."""
import os
import json
import re
import sys
import zlib

import pymysql

PW = os.environ.get('MYSQL_PASSWORD', '')
SRC = 'gk100.com转载河南省教育考试院2025河南专业组投档线'


def conn():
    return pymysql.connect(host='127.0.0.1', port=3306, user='root', password=PW,
                           database='gaokao_platform', charset='utf8mb4',
                           cursorclass=pymysql.cursors.DictCursor)


def sid(name):
    return zlib.crc32(name.encode('utf-8')) % 2000000000


def main():
    data = json.load(open('data/raw/gk100_2025_zyz.json'))
    rows = []
    for table in data:
        for r in table:
            if len(r) >= 5 and r[0] in ('物理', '历史'):
                rows.append(r)
    print('parsed rows:', len(rows))
    if len(rows) < 30:
        print('FATAL too few rows')
        sys.exit(1)

    c = conn()
    cur = c.cursor()
    schools = {}
    n_group = n_adm = 0
    for ketype, school, group, score, rank in rows:
        score = int(re.sub(r'\D', '', score) or 0)
        rank = int(re.sub(r'\D', '', rank) or 0)
        if not school or not score or not rank:
            continue
        if school not in schools:
            schools[school] = sid(school)
            cur.execute(
                "INSERT IGNORE INTO school (id,name,school_code,province_id,city,school_type,level,nature) "
                "VALUES (%s,%s,'',0,'','未知','本科','未知')",
                (schools[school], school))
        s_id = schools[school]
        g_code = re.sub(r'[^\w]', '', group)[:20] or 'G1'
        g_id = zlib.crc32(('%s|41|2025|%s' % (s_id, g_code)).encode()) % 9000000000000000000
        cur.execute(
            "INSERT IGNORE INTO major_group (id,school_id,province_id,year,group_code,group_name,batch,subject_type) "
            "VALUES (%s,%s,41,2025,%s,%s,'本科批',%s)",
            (g_id, s_id, g_code, group, ketype))
        n_group += cur.rowcount
        a_id = zlib.crc32(('adm|%s|2025' % g_id).encode()) % 9000000000000000000
        cur.execute(
            "INSERT IGNORE INTO admission_record (id,group_id,province_id,year,subject_type,"
            "min_score,min_rank,data_source,verify_status) "
            "VALUES (%s,%s,41,2025,%s,%s,%s,%s,2)",
            (a_id, g_id, ketype, score, rank, SRC))
        n_adm += cur.rowcount

    # 2025 批次线 (考试院公布)
    for i, (st, batch, line) in enumerate([
            ('物理', '特殊类型招生控制线', 535), ('物理', '本科批', 427),
            ('历史', '特殊类型招生控制线', 552), ('历史', '本科批', 471),
            ('物理', '专科批', 185), ('历史', '专科批', 185)], 10):
        cur.execute("INSERT IGNORE INTO batch_line (id,province_id,year,subject_type,batch,line_score) "
                    "VALUES (%s,41,2025,%s,%s,%s)", (i, st, batch, line))
    c.commit()
    cur.execute("SELECT COUNT(*) n FROM school")
    print('schools:', cur.fetchone()['n'])
    cur.execute("SELECT COUNT(*) n FROM major_group")
    print('major_groups:', cur.fetchone()['n'])
    cur.execute("SELECT COUNT(*) n FROM admission_record")
    print('admission_records:', cur.fetchone()['n'])
    c.close()


if __name__ == '__main__':
    main()
