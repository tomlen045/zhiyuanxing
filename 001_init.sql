-- ============================================================
-- 高考志愿填报智能分析平台 · 数据库 DDL (MySQL 8.0+)
-- 版本: V1.0  决策: 全国31省 / 精确再选科目匹配 / 免费就业数据
-- 生成日期: 2026-10-16
-- ============================================================

CREATE DATABASE IF NOT EXISTS gaokao_platform
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;
USE gaokao_platform;

-- ------------------------------------------------------------
-- 1. 基础维度表
-- ------------------------------------------------------------

-- 省份表
CREATE TABLE province (
  id          TINYINT UNSIGNED PRIMARY KEY,
  name        VARCHAR(20)  NOT NULL COMMENT '省级行政区名称',
  region      VARCHAR(10)  NOT NULL COMMENT '大区: 华北/华东/华南/华中/西南/西北/东北',
  exam_mode   VARCHAR(10)  NOT NULL COMMENT '高考模式: 3+3 / 3+1+2 / 老文理(仅历史数据)',
  batch_count TINYINT UNSIGNED DEFAULT 3 COMMENT '当前批次数(用于校验)',
  UNIQUE KEY uk_name (name)
) COMMENT '省份';

-- 院校表
CREATE TABLE school (
  id           INT UNSIGNED PRIMARY KEY,
  name         VARCHAR(60)  NOT NULL,
  short_name   VARCHAR(30),
  school_code  VARCHAR(10)  NOT NULL COMMENT '教育部院校代码(5位)',
  province_id  TINYINT UNSIGNED NOT NULL,
  city         VARCHAR(30)  NOT NULL,
  is_985       TINYINT(1)   DEFAULT 0,
  is_211       TINYINT(1)   DEFAULT 0,
  is_double_first_class TINYINT(1) DEFAULT 0 COMMENT '双一流',
  school_type  VARCHAR(20)  NOT NULL COMMENT '综合/理工/师范/财经/医药/农林/政法/语言/艺术/体育/军事/民族',
  level        VARCHAR(10)  NOT NULL COMMENT '本科/专科',
  nature       VARCHAR(10)  NOT NULL COMMENT '公办/民办/中外合作',
  found_year   SMALLINT UNSIGNED,
  tags         VARCHAR(200) COMMENT '标签, 逗号分隔: 强基计划,保研率高,行业特色',
  homepage     VARCHAR(200),
  INDEX idx_province (province_id),
  INDEX idx_type (school_type),
  INDEX idx_name (name)
) COMMENT '院校';

-- 专业表 (教育部专业目录)
CREATE TABLE major (
  id             INT UNSIGNED PRIMARY KEY,
  major_code     VARCHAR(8)   NOT NULL COMMENT '教育部专业代码(8位, 含大类)',
  name           VARCHAR(60)  NOT NULL,
  category_code  VARCHAR(4)   NOT NULL COMMENT '专业类代码',
  discipline     VARCHAR(20)  NOT NULL COMMENT '学科门类: 哲学/经济学/法学/教育学/文学/历史学/理学/工学/农学/医学/管理学/艺术学/交叉工程',
  is_broad       TINYINT(1)   DEFAULT 0 COMMENT '是否按大类招生',
  parent_id      INT UNSIGNED COMMENT '大类-具体专业归属',
  degree_type    VARCHAR(10)  COMMENT '学位类型',
  duration_years DECIMAL(2,1) DEFAULT 4.0,
  intro          TEXT         COMMENT '专业简介(自建百科)',
  UNIQUE KEY uk_code (major_code),
  INDEX idx_name (name),
  INDEX idx_discipline (discipline)
) COMMENT '专业(本科专业目录2024版约816个含大类)';

-- ------------------------------------------------------------
-- 2. 招生计划与专业组
-- ------------------------------------------------------------

-- 院校专业组 / 院校专业列表
CREATE TABLE major_group (
  id                BIGINT UNSIGNED PRIMARY KEY,
  school_id         INT UNSIGNED NOT NULL,
  province_id       TINYINT UNSIGNED NOT NULL COMMENT '在哪个省招生',
  year              SMALLINT UNSIGNED NOT NULL,
  group_code        VARCHAR(20)  NOT NULL COMMENT '专业组代码(各省编排不同)',
  group_name        VARCHAR(100) COMMENT '如: 计算机类(物理+化学)',
  batch             VARCHAR(30)  NOT NULL COMMENT '批次: 本科提前批/本科批/专科提前批/专科批',
  subject_type      VARCHAR(10)  NOT NULL COMMENT '科类: 物理/历史/综合(3+3)/文/理(历史数据)',
  require_subject_1 VARCHAR(20)  NOT NULL DEFAULT '' COMMENT '首选科目要求: 物理/历史/无',
  require_subject_2 VARCHAR(40)  NOT NULL DEFAULT '' COMMENT '再选科目要求, 逗号分隔: 化学,生物 / 化学|生物(或) / 空=不限',
  require_type_2    VARCHAR(10)  NOT NULL DEFAULT 'any' COMMENT '再选要求类型: any(任一即可)/all(均须选)/none(不限)',
  special_note      VARCHAR(200) COMMENT '特殊要求: 需面试/单科成绩要求/男女比例',
  UNIQUE KEY uk_group (school_id, province_id, year, group_code),
  INDEX idx_query (province_id, year, subject_type),
  INDEX idx_subject_req (require_subject_1, require_type_2)
) COMMENT '院校专业组(新高考) / 院校专业分类(老高考)';

-- 专业组内专业明细
CREATE TABLE group_major (
  id           BIGINT UNSIGNED PRIMARY KEY,
  group_id     BIGINT UNSIGNED NOT NULL,
  major_id     INT UNSIGNED NOT NULL,
  planned_num  SMALLINT UNSIGNED COMMENT '计划数',
  tuition      INT UNSIGNED COMMENT '学费(元/年)',
  FOREIGN KEY (group_id) REFERENCES major_group(id),
  INDEX idx_major (major_id)
) COMMENT '专业组内专业';

-- ------------------------------------------------------------
-- 3. 分数线体系
-- ------------------------------------------------------------

-- 一分一段表
CREATE TABLE score_rank (
  id           BIGINT UNSIGNED PRIMARY KEY,
  province_id  TINYINT UNSIGNED NOT NULL,
  year         SMALLINT UNSIGNED NOT NULL,
  subject_type VARCHAR(10)  NOT NULL COMMENT '物理/历史/综合/文/理',
  score        SMALLINT UNSIGNED NOT NULL,
  same_count   INT UNSIGNED NOT NULL COMMENT '本分数人数',
  cum_count    INT UNSIGNED NOT NULL COMMENT '累计人数=位次',
  UNIQUE KEY uk_prs (province_id, year, subject_type, score),
  INDEX idx_rank (province_id, year, subject_type, cum_count)
) COMMENT '一分一段表';

-- 院校专业组投档/录取数据 (核心事实表)
CREATE TABLE admission_record (
  id             BIGINT UNSIGNED PRIMARY KEY,
  group_id       BIGINT UNSIGNED NOT NULL,
  province_id    TINYINT UNSIGNED NOT NULL,
  year           SMALLINT UNSIGNED NOT NULL,
  subject_type   VARCHAR(10)  NOT NULL,
  planned_num    SMALLINT UNSIGNED,
  enrolled_num   SMALLINT UNSIGNED,
  min_score      SMALLINT UNSIGNED COMMENT '最低投档/录取分',
  min_rank       INT UNSIGNED COMMENT '最低位次',
  avg_score      SMALLINT UNSIGNED COMMENT '平均分(部分省公布)',
  max_score      SMALLINT UNSIGNED,
  data_source    VARCHAR(120) NOT NULL COMMENT '来源URL/文件, 用于溯源',
  verify_status  TINYINT UNSIGNED DEFAULT 0 COMMENT '0待校验 1自动通过 2人工通过 3异常',
  UNIQUE KEY uk_adm (group_id, province_id, year),
  INDEX idx_query (province_id, year, subject_type, min_rank),
  INDEX idx_verify (verify_status)
) COMMENT '录取数据(近5年, 31省预计800万+条)';

-- 专业级录取明细 (部分省/校公布到专业)
CREATE TABLE major_admission (
  id           BIGINT UNSIGNED PRIMARY KEY,
  group_major_id BIGINT UNSIGNED NOT NULL,
  province_id  TINYINT UNSIGNED NOT NULL,
  year         SMALLINT UNSIGNED NOT NULL,
  min_score    SMALLINT UNSIGNED,
  min_rank     INT UNSIGNED,
  avg_score    SMALLINT UNSIGNED,
  data_source  VARCHAR(120) NOT NULL,
  UNIQUE KEY uk_ma (group_major_id, province_id, year),
  INDEX idx_query (province_id, year, min_rank)
) COMMENT '专业级录取明细(增量数据, 非全量有)';

-- 省控线 (批次线)
CREATE TABLE batch_line (
  id           BIGINT UNSIGNED PRIMARY KEY,
  province_id  TINYINT UNSIGNED NOT NULL,
  year         SMALLINT UNSIGNED NOT NULL,
  subject_type VARCHAR(10)  NOT NULL,
  batch        VARCHAR(30)  NOT NULL,
  line_score   SMALLINT UNSIGNED NOT NULL,
  UNIQUE KEY uk_bl (province_id, year, subject_type, batch)
) COMMENT '省控批次线';

-- ------------------------------------------------------------
-- 4. 就业数据 (免费公开口径)
-- ------------------------------------------------------------

-- 专业就业统计 (高校就业质量报告汇总+招聘平台公开薪酬)
CREATE TABLE employment_stat (
  id               BIGINT UNSIGNED PRIMARY KEY,
  major_id         INT UNSIGNED COMMENT '专业级(全国平均口径)',
  school_id        INT UNSIGNED COMMENT '院校级(有就业报告的院校), 与major_id二选一',
  report_year      SMALLINT UNSIGNED NOT NULL COMMENT '数据届别',
  source_type      VARCHAR(20)  NOT NULL COMMENT 'school_report/ Recruitment_public/moe_annual',
  employment_rate  DECIMAL(5,2) COMMENT '毕业去向落实率%',
  further_study_rate DECIMAL(5,2) COMMENT '深造率%(国内+出国)',
  avg_start_salary INT UNSIGNED COMMENT '应届平均起薪(元/月)',
  salary_5y_median INT UNSIGNED COMMENT '5年薪资中位数(元/月, 招聘平台口径)',
  top_industries   VARCHAR(200) COMMENT '主要行业TOP3',
  top_companies    VARCHAR(300) COMMENT '代表企业',
  top_cities       VARCHAR(120) COMMENT '主要就业城市',
  data_source      VARCHAR(200) NOT NULL,
  INDEX idx_major (major_id, report_year),
  INDEX idx_school (school_id, report_year)
) COMMENT '就业统计(免费公开数据)';

-- 专业-职业映射 (自建知识库)
CREATE TABLE major_career_map (
  id             BIGINT UNSIGNED PRIMARY KEY,
  major_id       INT UNSIGNED NOT NULL,
  career_dir     VARCHAR(60)  NOT NULL COMMENT '职业方向: 软件开发/金融分析/临床医疗...',
  typical_roles  VARCHAR(200) NOT NULL COMMENT '典型岗位: Java后端/算法工程师/数据开发',
  skill_req      VARCHAR(300) COMMENT '任职要求摘要',
  career_path    VARCHAR(300) COMMENT '发展路径: 初级→资深→架构/管理',
  salary_range_fresh  VARCHAR(30) COMMENT '应届薪资区间(元/月)',
  salary_range_5y     VARCHAR(30) COMMENT '5年薪资区间(元/月)',
  hot_level      TINYINT UNSIGNED DEFAULT 3 COMMENT '热度1-5',
  INDEX idx_major (major_id)
) COMMENT '专业-职业映射百科';

-- ------------------------------------------------------------
-- 5. 学习专题库 (决策6: 提分细化到专题)
-- ------------------------------------------------------------

-- 科目-知识点专题表
CREATE TABLE study_topic (
  id            INT UNSIGNED PRIMARY KEY,
  subject       VARCHAR(10)  NOT NULL COMMENT '语文/数学/英语/物理/化学/生物/历史/地理/政治',
  topic_name    VARCHAR(60)  NOT NULL COMMENT '如: 导数综合应用',
  module        VARCHAR(30)  NOT NULL COMMENT '模块: 函数与导数/解析几何/电磁学...',
  exam_weight   DECIMAL(4,1) COMMENT '高考占比%(该专题大约值多少分)',
  difficulty    TINYINT UNSIGNED DEFAULT 3 COMMENT '难度1-5',
  avg_score_rate DECIMAL(4,1) COMMENT '全国平均得分率%(反映好不好拿分)',
  score_band    VARCHAR(20)  DEFAULT '90-115' COMMENT '适用分数段',
  material_link VARCHAR(200) COMMENT '讲义/真题资源链接',
  UNIQUE KEY uk_topic (subject, module, topic_name)
) COMMENT '学习专题库(约400-600条, 9科×50-70专题)';

-- 单科提分难度曲线 (边际效应)
CREATE TABLE subject_score_curve (
  id          INT UNSIGNED PRIMARY KEY,
  subject     VARCHAR(10)  NOT NULL,
  band_start  SMALLINT UNSIGNED NOT NULL COMMENT '分数段起点',
  cost_per_point DECIMAL(3,1) NOT NULL COMMENT '每提1分所需有效学习时长(小时)',
  success_prob   DECIMAL(3,2) COMMENT '该段提分成功率(基于经验统计)',
  UNIQUE KEY uk_curve (subject, band_start)
) COMMENT '提分边际成本曲线(如语文130+:6.0h/分, 数学100:2.5h/分)';

-- ------------------------------------------------------------
-- 6. 用户与业务
-- ------------------------------------------------------------

CREATE TABLE user (
  id            BIGINT UNSIGNED PRIMARY KEY,
  phone         VARCHAR(20)  UNIQUE,
  password_hash VARCHAR(100) NOT NULL,
  nickname      VARCHAR(30),
  role          VARCHAR(10)  DEFAULT 'student' COMMENT 'student/admin',
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  status        TINYINT UNSIGNED DEFAULT 1
) COMMENT '用户(自用版手机号可选)';

CREATE TABLE user_profile (
  id             BIGINT UNSIGNED PRIMARY KEY,
  user_id        BIGINT UNSIGNED NOT NULL,
  province_id    TINYINT UNSIGNED NOT NULL,
  year           SMALLINT UNSIGNED NOT NULL COMMENT '高考年份',
  subject_type   VARCHAR(10)  NOT NULL COMMENT '物理/历史',
  elective_1     VARCHAR(10)  COMMENT '再选科目1(3+1+2省)',
  elective_2     VARCHAR(10)  COMMENT '再选科目2',
  chinese        SMALLINT UNSIGNED,
  math           SMALLINT UNSIGNED,
  english        SMALLINT UNSIGNED,
  physics        SMALLINT UNSIGNED,
  chemistry      SMALLINT UNSIGNED,
  biology        SMALLINT UNSIGNED,
  history_sub    SMALLINT UNSIGNED,
  geography      SMALLINT UNSIGNED,
  politics       SMALLINT UNSIGNED,
  total_score    SMALLINT UNSIGNED,
  total_rank     INT UNSIGNED COMMENT '全省位次(有则填, 无则用一分一段反查)',
  updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES user(id),
  INDEX idx_query (province_id, year, subject_type)
) COMMENT '考生画像(各科分数)';

CREATE TABLE recommend_log (
  id           BIGINT UNSIGNED PRIMARY KEY,
  user_id      BIGINT UNSIGNED NOT NULL,
  profile_id   BIGINT UNSIGNED NOT NULL,
  target_group_id BIGINT UNSIGNED COMMENT '提分场景的目标专业组',
  result_json  JSON COMMENT '推荐结果快照(5个推荐或提分方案)',
  feedback     TINYINT COMMENT '1满意 0一般 -1不满意(用于迭代)',
  created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user (user_id)
) COMMENT '推荐与提分报告记录';

-- ------------------------------------------------------------
-- 7. 数据质检与采集任务
-- ------------------------------------------------------------

CREATE TABLE crawl_task (
  id           BIGINT UNSIGNED PRIMARY KEY,
  province_id  TINYINT UNSIGNED NOT NULL,
  year         SMALLINT UNSIGNED NOT NULL,
  data_type    VARCHAR(20)  NOT NULL COMMENT 'admission/score_rank/plan/batch_line',
  status       VARCHAR(10)  DEFAULT 'pending' COMMENT 'pending/running/done/failed',
  record_count INT UNSIGNED DEFAULT 0,
  error_msg    TEXT,
  started_at   DATETIME,
  finished_at  DATETIME,
  INDEX idx_status (status)
) COMMENT '采集任务监控';

CREATE TABLE data_verify_log (
  id           BIGINT UNSIGNED PRIMARY KEY,
  target_table VARCHAR(30)  NOT NULL,
  target_id    BIGINT UNSIGNED NOT NULL,
  rule         VARCHAR(50)  NOT NULL COMMENT '触发规则: min_gt_avg等',
  detail       VARCHAR(300),
  handled      TINYINT DEFAULT 0,
  created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_handled (handled)
) COMMENT '数据异常日志';
