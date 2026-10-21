# -*- coding: utf-8 -*-
"""
静态版导出: 从MySQL导出数据 → site/data.js → wrangler pages deploy
用法: /usr/bin/python3 export_static.py   (数据更新后重跑即可, 线上1分钟内生效)
"""
import os
import pymysql, json, re, subprocess, sys

c = pymysql.connect(host='127.0.0.1', port=3306, user='root', password=os.environ.get('MYSQL_PASSWORD', ''),
                    database='gaokao_platform', charset='utf8mb4')
cur = c.cursor()
cur.execute("""SELECT a.year, a.subject_type, a.min_score, a.min_rank, s.name, g.group_name,
s.is_985, s.is_211, s.is_double_first_class
FROM admission_record a JOIN major_group g ON g.id=a.group_id JOIN school s ON s.id=g.school_id
WHERE a.province_id=44""")
adm = [[int(r[0]), r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]] for r in cur.fetchall()]
cur.execute("SELECT year, subject_type, score, cum_count FROM score_rank WHERE province_id=44")
rk = {}
for year, subj, score, cum in cur.fetchall():
    t = rk.setdefault(f"{year}_{subj}", [[], []])
    t[0].append(score); t[1].append(cum)
totals = {k: max(v[1]) for k, v in rk.items()}
cur.execute("SELECT year, subject_type, batch, line_score FROM batch_line WHERE province_id=44")
batch = [list(x) for x in cur.fetchall()]
c.close()

src = open('app.py', encoding='utf-8').read()
def extract(name):
    m = re.search(name + r' = (\{.*?\n\})', src, re.S)
    s = re.sub(r'\((\d+(?:\.\d+)?),\s*([0-9.]+)\)', r'[\1,\2]', m.group(1))
    s = re.sub(r"\('([^']+)',\s*(\d+),\s*(\d+)\)", r'["\1",\2,\3]', s)
    return re.sub(r'#[^\n]*\n', '', s)

js = "// 数据快照(自动生成, 勿手改) · 来源: 广东省教育考试院(eea.gd.gov.cn)\n"
js += "const CURVE=" + extract('CURVE') + ";\n"
js += "const TOPICS=" + extract('TOPICS') + ";\n"
js += "const TOTALS=" + json.dumps(totals, ensure_ascii=False) + ";\n"
js += "const BATCH=" + json.dumps(batch, ensure_ascii=False) + ";\n"
js += "const RANKS=" + json.dumps(rk, ensure_ascii=False, separators=(',', ':')) + ";\n"
js += "const ADM=" + json.dumps(adm, ensure_ascii=False, separators=(',', ':')) + ";\n"
open('site/data.js', 'w', encoding='utf-8').write(js)
print(f'adm={len(adm)} ranks={sum(len(v[0]) for v in rk.values())} batch={len(batch)}')

env = {'PATH': '/opt/homebrew/bin:/usr/bin:/bin', 'WRANGLER_SEND_METRICS': 'false', 'HOME': __import__('os').path.expanduser('~')}
r = subprocess.run(['npx', 'wrangler', 'pages', 'deploy', '.', '--project-name', 'zhiyuanxing',
                    '--branch', 'main', '--commit-dirty', 'true'],
                   capture_output=True, text=True, timeout=300, env=env, cwd='site')
out = r.stdout + r.stderr
print(out[-300:])
sys.exit(r.returncode)
