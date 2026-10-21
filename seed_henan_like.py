#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""河南2024一分一段(理科) PDF 采集入库.
来源: 锦宏高考镜像的河南省教育考试院 2024 分数段统计表(理科) PDF.
"""
import os
import re
import subprocess
import sys

PW = os.environ.get('MYSQL_PASSWORD', '')
PDF = 'data/raw/henan2024_like.pdf'
SRC = '河南省教育考试院《2024年河南省普通高招分数段统计表(理科)》pdf (jhgk.cn 镜像)'


def run_sql(sql):
    cmd = ['docker', 'exec', '-i', 'gaokao-mysql', 'mysql', '-uroot', '-p' + PW,
           'gaokao_platform', '-e', sql]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print('SQL_ERROR:', r.stderr.strip()[:400])
        sys.exit(1)
    return r.stdout


def main():
    import fitz  # pymupdf
    doc = fitz.open(PDF)
    pairs = []
    for page in doc:
        words = page.get_text('words')  # x0,y0,x1,y1,word,block,line,word_no
        rows = {}
        for w in words:
            x0, y0, x1, y1, txt = w[0], w[1], w[2], w[3], w[4]
            key = round(y0 / 6)
            rows.setdefault(key, []).append((x0, txt))
        for key in sorted(rows):
            cells = [t for _, t in sorted(rows[key])]
            nums = [c for c in cells if re.fullmatch(r'\d{1,3}%?', c)]
            if len(nums) >= 2:
                pairs.append(nums)
    doc.close()

    seg = []
    for cells in pairs:
        m = [c for c in cells if re.fullmatch(r'\d{3}', c)]
        n = [c for c in cells if re.fullmatch(r'\d{4,7}', c)]
        if len(m) >= 1 and len(n) >= 1:
            sc = int(m[0])
            cum = int(n[-1])
            if 100 <= sc <= 750 and cum > 0:
                seg.append((sc, cum))
    # 去重保留首个
    seen = {}
    for sc, cum in seg:
        if sc not in seen:
            seen[sc] = cum
    seg = sorted(seen.items(), key=lambda t: -t[0])
    print('parsed_score_points=', len(seg))
    if len(seg) < 100:
        print('FATAL too few rows; sample:', seg[:10])
        sys.exit(1)
    # 单调性修复: 分数降序时 cum 必须不减, 违例则丢弃
    fixed = []
    for sc, cum in seg:
        if fixed and cum <= fixed[-1][1]:
            continue
        fixed.append((sc, cum))
    print('monotone_rows=', len(fixed), 'range', fixed[0], '->', fixed[-1])
    # 黄金交叉校验: 600分累计=23638, 511分(一本线)累计=130195
    d = dict(fixed)
    chk1 = d.get(600)
    chk2 = d.get(511)
    print('cum@600=', chk1, '(expect 23638)', ' cum@511=', chk2, '(expect 130195)')
    ok1 = chk1 is not None and abs(chk1 - 23638) <= 60
    ok2 = chk2 is not None and abs(chk2 - 130195) <= 400
    if not (ok1 and ok2):
        print('FATAL cross-check failed')
        sys.exit(1)

    vals = []
    prev = 0
    for i, (sc, cum) in enumerate(fixed, 1):
        same = max(cum - prev, 0)
        prev = cum
        vals.append("({},41,2024,'理',{},{},{})".format(950000 + i, sc, same, cum))
    run_sql("INSERT IGNORE INTO score_rank (id,province_id,year,subject_type,score,same_count,cum_count) VALUES "
            + ','.join(vals) + ';')
    print('imported likeread rows:', len(vals))
    print(run_sql("SELECT subject_type,COUNT(*) n,MAX(score) hi FROM score_rank WHERE province_id=41 "
                  "AND year=2024 GROUP BY subject_type").strip())


if __name__ == '__main__':
    main()
