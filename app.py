#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高考志愿填报智能分析平台 · 志愿星
- 纯 stdlib HTTP 服务 + pymysql (唯一第三方依赖)
- 数据: gaokao_platform 库 (真实公开数据, 来源标注在数据行 data_source)
- 端到端自适应: 桌面/平板/手机 (CSS Grid + 媒体查询 + rem)
- 逻辑模块: 一分一段位次查询 / 录取概率(位次锚定) / 冲稳保推荐 / 提分规划
"""
import json
import os
import re
import threading

try:
    import pymysql
except ImportError:
    pymysql = None

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

HOST = os.environ.get('GAOKAO_HOST', '0.0.0.0')
PORT = int(os.environ.get('GAOKAO_PORT', '8504'))
DB_CONF = dict(
    host='127.0.0.1', port=3306, user='root', password=os.environ.get('MYSQL_PASSWORD', ''),
    database='gaokao_platform', charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor if pymysql else None,
)
_local = threading.local()


def db():
    if pymysql is None:
        raise RuntimeError('pymysql missing')
    conn = getattr(_local, 'conn', None)
    if conn is None:
        conn = pymysql.connect(**DB_CONF)
        _local.conn = conn
    try:
        conn.ping(reconnect=True)
    except Exception:
        conn = pymysql.connect(**DB_CONF)
        _local.conn = conn
    return conn


def q(sql, args=None):
    cur = db().cursor()
    cur.execute(sql, args or ())
    rows = cur.fetchall()
    cur.close()
    return rows


PROVINCE_NAME = {}


def load_provinces():
    PROVINCE_NAME.clear()
    for r in q("SELECT id,name FROM province WHERE visible=1"):
        PROVINCE_NAME[r['id']] = r['name']
    return PROVINCE_NAME


def get_pid(qs):
    """省份参数: 默认44(广东, 唯一可见省). 校验必须可见."""
    pid = int(qs.get('province', ['44'])[0]) if qs.get('province') else 44
    if pid not in PROVINCE_NAME:
        return None
    return pid


def rank_of(province_id, year, subject_type, score):
    """分数 -> 全省累计位次"""
    rows = q("SELECT cum_count FROM score_rank WHERE province_id=%s AND year=%s "
             "AND subject_type=%s AND score=%s LIMIT 1",
             (province_id, year, subject_type, score))
    return rows[0]['cum_count'] if rows else None


def score_at_rank(province_id, year, subject_type, rank_target):
    """位次 -> 等位分 (一分一段反查): 找累计人数>=rank的最小分数"""
    rows = q("SELECT score FROM score_rank WHERE province_id=%s AND year=%s AND subject_type=%s "
             "AND cum_count>=%s ORDER BY score ASC LIMIT 1",
             (province_id, year, subject_type, rank_target))
    return rows[0]['score'] if rows else None


def api_meta():
    provs = load_provinces()
    years = q("SELECT DISTINCT year FROM score_rank ORDER BY year DESC")
    n_rank = q("SELECT COUNT(*) n FROM score_rank")[0]['n']
    n_adm = q("SELECT COUNT(*) n FROM admission_record")[0]['n']
    return {'provinces': [{'id': k, 'name': v} for k, v in provs.items()],
            'years': [r['year'] for r in years],
            'score_rank_rows': n_rank, 'admission_rows': n_adm,
            'data_note': '数据来源: 各省教育考试院官方公布数据, 仅供参考'}


def api_rank(pid, year, subject, score):
    rk = rank_of(pid, year, subject, score)
    return {'year': year, 'subject': subject, 'score': score, 'rank': rk,
            'note': '位次=该分数及以上累计人数' if rk else '该年份/科类无此分数记录'}


def api_exam_total(pid, year):
    """该年普通类考生总数(官方分数段表最低分累计人数口径, 含加分)."""
    rows = q("SELECT subject_type, MAX(cum_count) total FROM score_rank "
             "WHERE province_id=%s AND year=%s GROUP BY subject_type", (pid, year))
    if not rows:
        return {'year': year, 'subjects': {}, 'total': 0}
    subjects = {r['subject_type']: r['total'] for r in rows}
    return {'year': year, 'subjects': subjects, 'total': sum(subjects.values()),
            'note': '口径: 省考试院分数段统计表普通类考生数(含政策性加分)'}


def api_batch_lines(pid):
    return q("SELECT year,subject_type,batch,line_score FROM batch_line WHERE province_id=%s "
             "ORDER BY year DESC, subject_type, batch", (pid,))


def api_admissions(pid, q_kw=None, limit=300):
    sql = ("SELECT a.year,a.subject_type,a.min_score,a.min_rank,s.name school_name,"
           "s.is_985,s.is_211,s.is_double_first_class,g.group_name,a.data_source "
           "FROM admission_record a "
           "JOIN major_group g ON g.id=a.group_id "
           "JOIN school s ON s.id=g.school_id WHERE a.province_id=%s")
    args = [pid]
    if q_kw:
        sql += " AND s.name LIKE %s"
        args.append('%' + q_kw + '%')
    sql += " ORDER BY a.year DESC, a.min_score DESC LIMIT %s"
    args.append(min(int(limit), 1000))
    return q(sql, args)


PROB_BANDS = [(0.97, '保', '#0F6E56'), (0.85, '稳', '#185FA5'),
              (0.65, '稳', '#185FA5'), (0.30, '冲', '#854F0B'), (0.0, '冲', '#A32D2D')]


def prob_of(d, sigma):
    """位次距离 → 录取概率 (logistic 映射, 锚点按志愿填报通行经验校准):
    d=-0.5(位次优势50%)≈98% | d=-0.25≈90% | d=0(压线)≈60% | d=+0.25≈21% | d=+0.4≈8% | d≥0.6≈2%
    真实校验: 2026广东物理650分(位次4041)被南科大(门槛656/2680, d=0.37→10%)录取, 低概率冲成功属正常事件.
    sigma 仅用于分层展示, 不进指数(高分段位次天然波动大, 会过度压缩概率)."""
    import math
    return 1.0 / (1.0 + math.exp(7.0 * (d - 0.06)))


def api_recommend(pid, year, subject, score, prefer=None, rank_input=None):
    rk = rank_input if rank_input else rank_of(pid, year, subject, score)
    if not rk:
        return {'error': 'no_rank_for_score',
                'hint': '该年份科类暂无一分一段数据, 可直接填入全省位次'}
    # 跨年位次锚定: 同省同科类历年位次同口径可比, 聚合全部年份
    # 匹配口径: 优先用「所选年份」的投档数据(考生直觉: 我今年多少位次能上哪些学校);
    # 所选年份无该年招生的学校, 回退用其最近年数据(前端标注年份)
    rows = q("SELECT a.min_rank,a.min_score,a.year,a.id adm_id,g.school_id,s.name school_name,"
             "s.is_985,s.is_211,s.is_double_first_class,s.school_type,s.city "
             "FROM admission_record a "
             "JOIN major_group g ON g.id=a.group_id "
             "JOIN school s ON s.id=g.school_id "
             "WHERE a.province_id=%s AND a.subject_type=%s AND a.min_rank IS NOT NULL "
             "AND (a.year=%s OR a.year=(SELECT MAX(a2.year) FROM admission_record a2 "
             "     JOIN major_group g2 ON g2.id=a2.group_id WHERE a2.province_id=%s AND a2.subject_type=%s)) "
             "AND a.min_rank BETWEEN %s AND %s",
             (pid, subject, year, pid, subject, int(rk * 0.45), int(rk * 2.2)))
    cands = {}
    for r in rows:
        key = r['school_id']
        cands.setdefault(key, []).append(r)
    items = []
    for sid, recs in cands.items():
        # 优先所选年份的组(取位次靠前=门槛低的那组); 无则用数据里最新年的组
        by_year = {}
        for x in recs:
            if x['year'] not in by_year or x['min_rank'] < by_year[x['year']]['min_rank']:
                by_year[x['year']] = x
        latest = by_year.get(year) or by_year[max(by_year)]
        # 锚定只算所选年份(有则单年锚定, 更贴近当年现实); 无所选年时用该年已有的全部年份数据
        if year in by_year:
            ranks = {year: by_year[year]['min_rank']}
            # 若同校还有前后一年数据, 一并锚定(最多3年)以平滑大小年
            for dy in (-1, 1):
                y2 = year + dy
                if y2 in by_year:
                    ranks[y2] = by_year[y2]['min_rank']
        else:
            ranks = {y: v['min_rank'] for y, v in by_year.items()}
        avg_rank = sum(ranks.values()) / len(ranks)
        d = (rk - avg_rank) / max(avg_rank, 1)
        spread = (max(ranks.values()) - min(ranks.values())) / max(avg_rank, 1) if len(ranks) > 1 else 0.08
        p = prob_of(d, max(spread, 0.08))
        tier, tier_color = ('保', '#0F6E56') if p >= 0.95 else (
            ('稳', '#185FA5') if p >= 0.65 else ('冲', '#854F0B' if p >= 0.30 else '#A32D2D'))
        reason = build_reason(latest, rk, avg_rank, p, d, tier,
                              PROVINCE_NAME.get(pid, '广东'))
        reason = ('近%d年数据锚定。' % len(ranks)) + reason
        trend = sorted(ranks.items())
        items.append({
            'school': latest['school_name'], 'school_type': latest['school_type'], 'city': latest['city'],
            'min_score': latest['min_score'], 'min_rank': latest['min_rank'],
            'min_rank_year': latest['year'],
            'my_rank': rk, 'prob': round(p * 100, 1), 'tier': tier, 'tier_color': tier_color,
            'is_985': latest['is_985'], 'is_211': latest['is_211'], 'is_dfc': latest['is_double_first_class'],
            'history': [[y, r] for y, r in trend],
            'years_covered': len(ranks),
            'reason': reason, '_p': p,
        })
    items.sort(key=lambda x: (-x['_p'], -x['years_covered']))
    chong = [x for x in items if x['tier'] == '冲']
    wen = [x for x in items if x['tier'] == '稳']
    bao = [x for x in items if x['tier'] == '保']
    # 结构: 3冲3稳3保主推 + 每档备选池(前端折叠展示"更多选择")
    pick = (chong[:3] if prefer != 'bao' else []) + wen[:3] + bao[:3]
    if len(pick) < 9:
        pool = sorted(items, key=lambda x: -x['_p'])
        for x in pool:
            if x not in pick and len(pick) < 9:
                pick.append(x)
    extra = {
        'chong': [x for x in chong if x not in pick[:9]][:6],
        'wen': [x for x in wen if x not in pick[:9]][:6],
        'bao': [x for x in bao if x not in pick[:9]][:6],
    }
    return {'my': {'score': score, 'rank': rk, 'year': year, 'subject': subject},
            'list': pick[:9], 'total_candidates': len(items), 'extra': extra}


def build_reason(r, my_rank, avg_rank, p, d, tier, prov='广东'):
    diff = int(avg_rank - my_rank)
    fmt = lambda x: f"{int(x):,}"
    words = []
    if d >= 0.03:
        words.append('该校近年在%s录取位次约%s名, 比您的位次%s名靠前%s名, 属于冲一冲档位' % (
            prov, fmt(avg_rank), fmt(my_rank), fmt(abs(diff))))
    elif d > -0.03:
        words.append('该校近年在%s录取位次约%s名, 与您的位次%s名基本持平, 匹配度高' % (
            prov, fmt(avg_rank), fmt(my_rank)))
    else:
        lead = '优势明显' if p >= 0.95 else ('有一定优势但需注意大小年波动' if p >= 0.65 else '优势不大, 属于稳中带冲的机会档')
        words.append('该校近年在%s录取位次约%s名, 您的位次%s名在其之后(更优), %s' % (
            prov, fmt(avg_rank), fmt(my_rank), lead))
    tags = []
    if r['is_985']:
        tags.append('985')
    if r['is_211']:
        tags.append('211')
    if r['is_double_first_class']:
        tags.append('双一流')
    if tags:
        words.append('院校层次: ' + '/'.join(tags))
    words.append('录取概率约%d%%, %s' % (round(p * 100), '仅供参考, 不构成录取承诺'))
    return '。'.join(words) + '。'


CURVE = {  # 单科提分边际成本(小时/分), 经验值冷启动, 后续按用户反馈校准
    '语文': [(0, 1.2), (100, 2.2), (115, 3.5), (125, 5.0), (130, 6.0), (140, 8.0)],
    '数学': [(0, 1.0), (90, 1.8), (105, 2.5), (120, 4.0), (130, 6.0), (140, 9.0)],
    '英语': [(0, 1.1), (95, 1.9), (110, 2.8), (125, 4.5), (135, 7.0), (142, 9.0)],
    '物理': [(0, 1.4), (60, 2.0), (75, 3.0), (85, 4.5), (95, 6.5)],
    '历史': [(0, 1.3), (60, 2.0), (75, 3.2), (85, 5.0), (95, 7.0)],
    '化学': [(0, 1.3), (60, 2.0), (75, 3.0), (85, 4.5), (95, 6.5)],
    '生物': [(0, 1.1), (60, 1.6), (75, 2.5), (85, 4.0), (95, 6.0)],
    '地理': [(0, 1.2), (60, 1.8), (75, 2.8), (85, 4.2), (95, 6.0)],
    '政治': [(0, 1.2), (60, 1.8), (75, 2.8), (85, 4.2), (95, 6.0)],
}
TOPICS = {
    '数学': [('导数综合应用', 22, 58), ('解析几何联立', 18, 52), ('数列递推与求和', 15, 63),
             ('立体几何建系', 14, 71), ('概率统计大题', 12, 66)],
    '语文': [('文言文实词虚词', 15, 62), ('诗歌鉴赏答题模板', 12, 55), ('现代文阅读信息筛选', 18, 64),
             ('作文结构升格', 20, 60)],
    '英语': [('完形填空语境词', 15, 60), ('阅读理解主旨题', 20, 63), ('七选五逻辑链', 10, 58),
             ('应用文模板句', 10, 75)],
    '物理': [('电磁学综合', 20, 55), ('力学受力分析', 18, 62), ('实验题设计', 12, 58)],
    '历史': [('材料解析题信息提取', 25, 60), ('阶段特征时序', 20, 65), ('小论文论证结构', 18, 55)],
    '化学': [('化学反应原理', 22, 56), ('有机推断', 18, 58), ('实验综合', 14, 60), ('元素周期律应用', 12, 66)],
    '生物': [('遗传规律应用', 24, 57), ('稳态与调节', 18, 63), ('生态与能量流动', 14, 68), ('实验设计', 12, 58)],
    '地理': [('大气环流与气候', 20, 60), ('区域产业分析', 18, 64), ('地球运动计算', 12, 52), ('地形与地貌', 14, 65)],
    '政治': [('经济生活计算', 18, 62), ('政治生活主体', 20, 66), ('哲学原理运用', 22, 55), ('法律与逻辑', 12, 58)],
}


def api_school_lookup(pid, kw, year=None, subject=None):
    """按校名搜索 → 返回带 admission_record.id 的精确目标(供提分规划选目标院校)."""
    if not kw:
        return []
    sql = ("SELECT a.id, s.name school_name, g.group_name, g.group_code, a.year, "
           "a.subject_type, a.min_score, a.min_rank "
           "FROM admission_record a "
           "JOIN major_group g ON g.id=a.group_id "
           "JOIN school s ON s.id=g.school_id "
           "WHERE a.province_id=%s AND s.name LIKE %s")
    args = [pid, '%' + kw + '%']
    if year:
        sql += " AND a.year=%s"
        args.append(year)
    if subject:
        sql += " AND a.subject_type=%s"
        args.append(subject)
    sql += " ORDER BY a.year DESC, a.min_score DESC LIMIT 30"
    return q(sql, args)


def api_score_plan(subject_type, scores, target_group_id=None, pid=44):
    """提分规划: 差距 -> 各科潜力 -> 专题建议"""
    total = sum(v for v in scores.values() if v)
    target_score = None
    target_name = None
    if target_group_id:
        rows = q("SELECT a.min_score,s.name school_name FROM admission_record a "
                 "JOIN major_group g ON g.id=a.group_id "
                 "JOIN school s ON s.id=g.school_id WHERE a.id=%s AND a.province_id=%s",
                 (target_group_id, pid))
        if rows and rows[0]['min_score']:
            target_score = rows[0]['min_score']
            target_name = rows[0]['school_name']
    if target_score is None:
        target_score = min(total + 30, 700)
        target_name = target_name or '按总分+30估算'
    gap = target_score - total
    plan = {'current_total': total, 'target_score': target_score, 'target_name': target_name,
            'gap': max(gap, 0), 'subjects': [], 'disclaimer': '提分测算为经验模型推演, 仅供参考'}
    if gap <= 0:
        plan['verdict'] = '当前总分已达到目标门槛, 重点转向志愿方案优化'
        return plan
    capacity = {}
    for subj, sc in scores.items():
        if not sc:
            continue
        full = 150 if subj in ('语文', '数学', '英语') else 100
        if subject_type == '历史' and subj == '物理':
            continue
        if subject_type == '物理' and subj == '历史':
            continue
        cap = full - sc
        if cap <= 0:
            continue
        curve = CURVE.get(subj, [(0, 2.5)])
        cost = 2.5
        for b, c in curve:
            if sc >= b:
                cost = c
        hours_budget = 260  # 到高考剩余有效学习时长假设
        gain = min(cap, max(int(hours_budget / cost / 3), 0), 25)
        capacity[subj] = {'now': sc, 'cap': cap, 'cost_per_point': cost,
                          'expected_gain': gain}
    ranked = sorted(capacity.items(), key=lambda kv: -(kv[1]['expected_gain'] / kv[1]['cost_per_point']))
    need = gap
    for subj, info in ranked:
        use = min(info['expected_gain'], max(need, 0))
        need -= use
        entry = {'subject': subj, 'now': info['now'], 'to': info['now'] + use,
                 'gain': use, 'cost_per_point': info['cost_per_point'],
                 'topics': [{'name': n, 'weight': w, 'score_rate': s}
                            for n, w, s in TOPICS.get(subj, [])[:3]]}
        plan['subjects'].append(entry)
    plan['verdict'] = ('预计可提升%s分, %s目标差距%s分' % (
        sum(s['gain'] for s in plan['subjects']), target_name, gap))
    return plan


def api_career(kw=None, disc=None):
    """就业百科: 专业→薪资/满意度/对口职业/典型雇主. 数据源=麦可思公开报告数字."""
    where, args = [], []
    if kw:
        where.append("m.name LIKE %s")
        args.append('%' + kw + '%')
    if disc and disc != '全部':
        where.append("m.discipline=%s")
        args.append(disc)
    cond = ('WHERE ' + ' AND '.join(where)) if where else ''
    majors = q("SELECT * FROM career_major m " + cond +
               " ORDER BY (m.salary_2025 IS NULL), m.salary_2025 DESC, m.name LIMIT 80", args)
    if kw and majors:
        target = majors[0]['name']
    elif not kw and majors:
        target = majors[0]['name']  # 默认展示榜首专业的就业出口
    else:
        target = None
    paths = q("SELECT * FROM career_path WHERE major_name=%s ORDER BY hot DESC",
              (target,)) if target else []
    refs = q("SELECT kind,label,value,report_year FROM career_ref ORDER BY kind,report_year DESC,value DESC")
    return {'majors': majors, 'paths': paths, 'refs': refs}


PAGE = None


class Handler(BaseHTTPRequestHandler):
    server_version = 'ZhiYuanXing/1.0'

    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        qs = parse_qs(parsed.query)
        try:
            if path == '/' or path == '/index.html':
                return self._html()
            if path == '/api/meta':
                return self._json(api_meta())
            if path == '/api/years':
                pid = get_pid(qs)
                if pid is None:
                    return self._json({'error': 'province_not_available'}, 403)
                adm = [r['year'] for r in q(
                    "SELECT DISTINCT year FROM admission_record WHERE province_id=%s ORDER BY year DESC", (pid,))]
                rk = [r['year'] for r in q(
                    "SELECT DISTINCT year FROM score_rank WHERE province_id=%s ORDER BY year DESC", (pid,))]
                return self._json({'admission_years': adm, 'rank_years': rk})
            if path == '/api/exam_total':
                pid = get_pid(qs)
                if pid is None:
                    return self._json({'error': 'province_not_available'}, 403)
                return self._json(api_exam_total(pid, int(qs['year'][0])))
            if path == '/api/rank':
                pid = get_pid(qs)
                if pid is None:
                    return self._json({'error': 'province_not_available'}, 403)
                return self._json(api_rank(pid, int(qs['year'][0]), qs['subject'][0], int(qs['score'][0])))
            if path == '/api/batch_lines':
                pid = get_pid(qs)
                if pid is None:
                    return self._json({'error': 'province_not_available'}, 403)
                return self._json(api_batch_lines(pid))
            if path == '/api/admissions':
                pid = get_pid(qs)
                if pid is None:
                    return self._json({'error': 'province_not_available'}, 403)
                return self._json(api_admissions(pid, qs.get('q', [None])[0], qs.get('limit', [300])[0]))
            if path == '/api/school_lookup':
                pid = get_pid(qs)
                if pid is None:
                    return self._json({'error': 'province_not_available'}, 403)
                return self._json(api_school_lookup(pid, qs.get('q', [''])[0], year=int(qs['year'][0]) if qs.get('year') else None, subject=qs.get('subject', [None])[0]))
            if path == '/api/recommend':
                pid = get_pid(qs)
                if pid is None:
                    return self._json({'error': 'province_not_available'}, 403)
                rk_in = int(qs['rank'][0]) if qs.get('rank') and qs['rank'][0].isdigit() else None
                return self._json(api_recommend(
                    pid, int(qs['year'][0]), qs['subject'][0], int(qs['score'][0]),
                    qs.get('prefer', [None])[0], rk_in))
            if path == '/api/score_plan':
                pid = get_pid(qs)
                if pid is None:
                    return self._json({'error': 'province_not_available'}, 403)
                scores = {}
                for k in ('语文', '数学', '英语', '物理', '历史', '化学', '生物', '地理', '政治'):
                    v = qs.get(k, [''])[0]
                    scores[k] = int(v) if v.isdigit() else None
                return self._json(api_score_plan(qs['subject'][0], scores,
                                                 int(qs['target'][0]) if qs.get('target') else None, pid))
            if path == '/api/career':
                kw = qs.get('q', [''])[0].strip()
                disc = qs.get('disc', ['全部'])[0]
                return self._json(api_career(kw or None, disc))
            return self._json({'error': 'not_found'}, 404)
        except Exception as e:
            return self._json({'error': str(e)}, 500)

    def _html(self):
        body = PAGE.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    global PAGE
    PAGE = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'index.html'),
                encoding='utf-8').read()
    load_provinces()
    print('provinces loaded:', list(PROVINCE_NAME.values()))
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print('ZhiYuanXing serving on http://%s:%s' % (HOST, PORT))
    srv.serve_forever()


if __name__ == '__main__':
    main()
