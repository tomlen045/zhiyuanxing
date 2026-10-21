#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""河南2025一分一段(物理类/历史类) 入库. 来源: 河南省教育考试院2025-06-25发布, 教育在线转载."""
import os
import re
import subprocess
import sys

PW = os.environ.get('MYSQL_PASSWORD', '')
def run_sql(sql):
    cmd = ['docker', 'exec', '-i', 'gaokao-mysql', 'mysql', '-uroot', '-p' + PW,
           'gaokao_platform', '-e', sql]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print('SQL_ERROR:', r.stderr.strip()[:400])
        sys.exit(1)
    return r.stdout


def parse(html):
    trs = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S)
    seg = []
    for tr in trs:
        tds = [re.sub(r'<[^>]+>', '', c).strip()
               for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S)]
        m = re.match(r'^(\d{3})', tds[0])
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


def main():
    import urllib.request

    def fetch(url):
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        return urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'ignore')

    jobs = [
        (2025, '物理', 'https://gaokao.eol.cn/he_nan/dongtai/202506/t20250625_2676859.shtml',
         '河南省教育考试院2025分数段统计表(物理类), 教育在线转载'),
        (2025, '历史', 'https://gaokao.eol.cn/he_nan/dongtai/202506/t20250625_2676858.shtml',
         '河南省教育考试院2025分数段统计表(历史类), 教育在线转载'),
    ]
    next_id = 960000
    for year, st, url, src in jobs:
        try:
            html = open(url.split('/')[-1].replace('.shtml', '') .join(['data/raw/', ''])
                        if False else 'data/raw/henan2025_wuli.html',
                        encoding='utf-8', errors='ignore').read()
        except OSError:
            html = fetch(url)
        if st == '历史':
            html = fetch(url)
        seg = parse(html)
        print(year, st, 'rows=', len(seg))
        if len(seg) < 100:
            print('FATAL too few for', st)
            sys.exit(1)
        chk = {'物理': (427, 348358), '历史': (471, 90174)}[st]
        line, total = chk
        d = dict((s, c) for s, n, c in seg)
        got = d.get(line)
        print('  cum@%d=' % line, got, 'expect', total)
        if got is None or abs(got - total) > 200:
            print('FATAL cross-check failed for', st)
            sys.exit(1)
        vals = []
        prev = 0
        for i, (sc, cnt, cum) in enumerate(seg, 1):
            same = max(cum - prev, 0)
            prev = cum
            vals.append("({},{},{},'{}',{},{},{})".format(next_id + i, year, 41, st, sc, same, cum))
        run_sql("INSERT IGNORE INTO score_rank (id,province_id,year,subject_type,score,same_count,cum_count) VALUES "
                + ','.join(vals) + ';')
        print('  imported', len(vals))
        next_id += 1000

    print(run_sql("SELECT year,subject_type,COUNT(*) n,MAX(score) hi FROM score_rank "
                  "WHERE province_id=41 GROUP BY year,subject_type").strip())


if __name__ == '__main__':
    main()
