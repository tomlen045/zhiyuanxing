#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""广东省2022-2026本科投档线 xlsx 导入.
来源: 广东省教育考试院官网各年度本科批次正式投档公告(用户整理xlsx, 22812条).
同时: 新增省份44(广东), 河南置为隐藏(visible=0).
"""
import os
import re
import sys
import zlib

import openpyxl
import pymysql

PW = os.environ.get('MYSQL_PASSWORD', '')
XLSX = '广东省2022-2026年高考本科投档线 副本.xlsx'
SRC = '广东省教育考试院本科批次投档公告附件(2022-2026, eea.gd.gov.cn)'
SHEETS = ['2022物理', '2022历史', '2023物理', '2023历史', '2024物理', '2024历史',
          '2025物理', '2025历史', '2026物理', '2026历史']


def parse_score(v):
    """'651以上'->651(边界保守值), 689->689, '缺档'->None"""
    if v is None:
        return None, False
    if isinstance(v, (int, float)):
        return int(v), False
    s = str(v).strip()
    m = re.match(r'^(\d{3})以上$', s)
    if m:
        return int(m.group(1)), True
    m = re.match(r'^(\d{1,3})以内$', s)
    if m:
        return int(m.group(1)), True
    return None, False


def main():
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    c = pymysql.connect(host='127.0.0.1', port=3306, user='root', password=PW,
                        database='gaokao_platform', charset='utf8mb4')
    cur = c.cursor()
    # 省份: 广东新增, 河南隐藏
    cur.execute("INSERT IGNORE INTO province (id,name,region,exam_mode,batch_count) "
                "VALUES (44,'广东','华南','3+1+2',1)")
    cur.execute("SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema='gaokao_platform' AND table_name='province' AND column_name='visible'")
    if cur.fetchone()[0] == 0:
        cur.execute("ALTER TABLE province ADD COLUMN visible TINYINT(1) NOT NULL DEFAULT 1")
    cur.execute("UPDATE province SET visible=0 WHERE id=41")
    cur.execute("UPDATE province SET visible=1 WHERE id=44")
    c.commit()

    schools = {}
    n_adm = n_grp = n_skip = n_edge = 0
    per_sheet = {}
    for sh in SHEETS:
        ws = wb[sh]
        year = int(sh[:4])
        ke = '物理' if '物理' in sh else '历史'
        cnt = 0
        rows = ws.iter_rows(min_row=2, values_only=True)
        for r in rows:
            if not r or r[2] is None:
                continue
            _, _, g_code_d, sch_name, g_code, planned, enrolled, score_v, rank_v, _ = (list(r) + [None] * 10)[:10]
            sch_name = (sch_name or '').strip()
            if not sch_name:
                continue
            g_code = str(g_code).strip() if g_code is not None else ''
            if sch_name not in schools:
                cur.execute("SELECT id FROM school WHERE name=%s", (sch_name,))
                got = cur.fetchone()
                if got:
                    schools[sch_name] = got[0]
                else:
                    s_id = zlib.crc32(sch_name.encode('utf-8')) % 2000000000
                    cur.execute("INSERT IGNORE INTO school (id,name,school_code,province_id,city,school_type,level,nature) "
                                "VALUES (%s,%s,'',0,'','未知','本科','未知')", (s_id, sch_name))
                    schools[sch_name] = s_id
            s_id = schools[sch_name]
            # 专业组代码在物理/历史内独立编号, 存储 code+科类后缀 保证唯一键
            g_code_stored = g_code + ('P' if ke == '物理' else 'H')
            g_id = zlib.crc32(('%s|44|%d|%s' % (s_id, year, g_code_stored)).encode()) % 9000000000000000000
            cur.execute("INSERT IGNORE INTO major_group (id,school_id,province_id,year,group_code,group_name,batch,subject_type) "
                        "VALUES (%s,%s,44,%s,%s,%s,'本科批',%s)",
                        (g_id, s_id, year, g_code_stored, (g_code + '组') if g_code else None, ke))
            n_grp += cur.rowcount
            score, is_edge = parse_score(score_v)
            rank = int(rank_v) if isinstance(rank_v, (int, float)) else None
            if score is None or rank is None:
                n_skip += 1
                continue
            if is_edge:
                n_edge += 1
            a_id = zlib.crc32(('adm|%d|%d' % (g_id, year)).encode()) % 9000000000000000000
            cur.execute("INSERT IGNORE INTO admission_record (id,group_id,province_id,year,subject_type,"
                        "planned_num,enrolled_num,min_score,min_rank,data_source,verify_status) "
                        "VALUES (%s,%s,44,%s,%s,%s,%s,%s,%s,%s,2)",
                        (a_id, g_id, year, ke,
                         int(planned) if isinstance(planned, (int, float)) else None,
                         int(enrolled) if isinstance(enrolled, (int, float)) else None,
                         score, rank, SRC))
            n_adm += cur.rowcount
            cnt += 1
        per_sheet[sh] = cnt
    c.commit()
    print('per_sheet:', per_sheet)
    print('groups:', n_grp, 'admissions:', n_adm, 'skipped(缺档/无分):', n_skip, 'boundary(以上/以内):', n_edge)
    # 校验锚点(与sheet原始行一致): 2024物理 北京大学203组 689/85, 清华202组 692/53
    cur.execute("SELECT a.min_score,a.min_rank FROM admission_record a "
                "JOIN major_group g ON g.id=a.group_id JOIN school s ON s.id=g.school_id "
                "WHERE a.province_id=44 AND a.year=2024 AND a.subject_type='物理' "
                "AND s.name='北京大学' AND g.group_code='203P'")
    print('北大2024物理203组:', cur.fetchone(), 'expect (689,85)')
    cur.execute("SELECT a.min_score,a.min_rank FROM admission_record a "
                "JOIN major_group g ON g.id=a.group_id JOIN school s ON s.id=g.school_id "
                "WHERE a.province_id=44 AND a.year=2024 AND a.subject_type='物理' "
                "AND s.name='清华大学' AND g.group_code='202P'")
    print('清华2024物理202组:', cur.fetchone(), 'expect (692,53)')
    cur.execute("SELECT a.year, a.subject_type, COUNT(*) FROM admission_record a "
                "WHERE a.province_id=44 GROUP BY a.year, a.subject_type ORDER BY a.year, a.subject_type")
    for r in cur.fetchall():
        print('gd adm:', r)
    cur.execute("SELECT id,name,visible FROM province")
    for r in cur.fetchall():
        print('province:', r)
    cur.execute("SELECT COUNT(*) FROM school")
    print('schools total:', cur.fetchone()[0])
    c.close()
    wb.close()
    print('GD_IMPORT_OK')


if __name__ == '__main__':
    main()
