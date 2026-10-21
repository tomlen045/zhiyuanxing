#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复广东导入的学校名脏前缀 ('育X大学'/'院X大学'/'教X大学').
剥前缀后归并到规范校名(已存在则重指向并删除脏行, 否则原地改名).
"""
import os
import re
import sys

import pymysql

PW = os.environ.get('MYSQL_PASSWORD', '')
DIRTY_PREFIX = ('育', '院', '教')
SUFFIX = ('大学', '学院', '学校')


def main():
    c = pymysql.connect(host='127.0.0.1', port=3306, user='root', password=os.environ.get('MYSQL_PASSWORD', ''),
                        database='gaokao_platform', charset='utf8mb4')
    cur = c.cursor()
    cur.execute("SELECT id, name FROM school WHERE name LIKE '育%%' OR name LIKE '院%%' OR name LIKE '教%%'")
    dirty = cur.fetchall()
    print('dirty schools:', len(dirty))
    remapped = renamed = deleted = 0
    for s_id, name in dirty:
        cleaned = name[1:].strip()
        # 校名主体(括号前部分)须以 大学/学院/学校 结尾, 括号内容(校区/培养方式)保留
        base = re.sub(r'[（(].*$', '', cleaned)
        if len(base) < 4 or not base.endswith(SUFFIX):
            print('SKIP suspicious:', repr(name))
            continue
        cur.execute("SELECT id FROM school WHERE name=%s AND id<>%s", (cleaned, s_id))
        got = cur.fetchone()
        if got:
            real_id = got[0]
            cur.execute("UPDATE major_group SET school_id=%s WHERE school_id=%s", (real_id, s_id))
            cur.execute("DELETE FROM school WHERE id=%s", (s_id,))
            deleted += 1
        else:
            cur.execute("UPDATE school SET name=%s WHERE id=%s", (cleaned, s_id))
            renamed += 1
        remapped += 1
    c.commit()
    print('cleaned:', remapped, '(renamed', renamed, '/ merged+deleted', deleted, ')')
    # 校验: 无残留
    cur.execute("SELECT COUNT(*) FROM school WHERE name LIKE '育%%' OR name LIKE '院%%' OR name LIKE '教%%'")
    left = cur.fetchone()[0]
    print('remaining dirty:', left, '(expect 0)')
    cur.execute("SELECT COUNT(*) FROM school")
    print('schools total:', cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM major_group WHERE province_id=44")
    print('gd groups:', cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM admission_record WHERE province_id=44")
    print('gd admissions:', cur.fetchone()[0])
    # 深圳大学历史轨迹应归一(2022/2023/2024物理曾为'育深圳大学')
    cur.execute("SELECT a.year, a.min_score, a.min_rank FROM admission_record a "
                "JOIN major_group g ON g.id=a.group_id JOIN school s ON s.id=g.school_id "
                "WHERE a.province_id=44 AND s.name='深圳大学' AND a.subject_type='物理' "
                "ORDER BY a.year LIMIT 12")
    for r in cur.fetchall():
        print('深大物理:', r)
    c.close()
    if left > 0:
        print('FAIL still dirty')
        sys.exit(1)
    print('REPAIR_OK')


if __name__ == '__main__':
    main()
