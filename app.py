# -*- coding: utf-8 -*-
"""考研学习进度追踪 —— Flask 应用入口（多用户架构）

本地启动方式：
    pip install -r requirements.txt
    python app.py
默认监听 0.0.0.0:5000，局域网内其他设备可通过 http://<本机IP>:5000 访问。

部署到 Render：
    Build Command:  pip install -r requirements.txt
    Start Command:  gunicorn app:app   （平台自动注入 PORT 并接管端口绑定）

数据库默认位于项目根下的 instance/data.db；
可通过环境变量 DATABASE_PATH 覆盖（如 Render 持久磁盘 /var/data/data.db）。

认证：Flask-Login 多用户系统，所有业务路由需登录；
注册 /register，登录 /login（勾选“记住我”有效期 30 天），退出 /logout。
"""
import json
import os
import secrets
import sys
import time
from datetime import date, datetime, timedelta

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_login import (LoginManager, current_user, login_required,
                         login_user, logout_user)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 兼容便携版 Python（embeddable）等不自动加入脚本目录的情况
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def load_dotenv(path):
    """极简 .env 加载器（零依赖）：支持 KEY=VALUE 与 # 注释，
    不覆盖已存在的环境变量（Render 注入的变量优先）。"""
    if not os.path.exists(path):
        return
    with open(path, 'r', encoding='utf-8-sig') as f:  # utf-8-sig 兼容带 BOM 的文件
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


# 本地开发环境变量（DATABASE_PATH 等）来自项目根下的 .env 文件
load_dotenv(os.path.join(BASE_DIR, '.env'))

from models import Subject, Record, Diary, Expense, User, db
from sqlalchemy import extract
from sqlalchemy.exc import IntegrityError

# 数据库文件：默认放在项目根下的 instance/ 目录（Render 部署时该目录可写）；
# 可通过环境变量 DATABASE_PATH 覆盖（例如 Render 挂载持久磁盘后指向 /var/data/data.db）
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
os.makedirs(INSTANCE_DIR, exist_ok=True)
DB_PATH = os.path.abspath(os.environ.get('DATABASE_PATH', os.path.join(INSTANCE_DIR, 'data.db')))

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + DB_PATH
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 会话密钥：优先环境变量（Render 中设置，保证重部署后登录态不失效）；
# 本地无环境变量时持久化到 instance/.secret_key，避免每次重启都丢失登录状态
if not os.environ.get('SECRET_KEY'):
    SECRET_KEY_FILE = os.path.join(INSTANCE_DIR, '.secret_key')
    if os.path.exists(SECRET_KEY_FILE):
        with open(SECRET_KEY_FILE, 'r', encoding='utf-8') as f:
            app.config['SECRET_KEY'] = f.read().strip()
    else:
        app.config['SECRET_KEY'] = secrets.token_hex(24)
        with open(SECRET_KEY_FILE, 'w', encoding='utf-8') as f:
            f.write(app.config['SECRET_KEY'])
else:
    app.config['SECRET_KEY'] = os.environ['SECRET_KEY']

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)   # 勾选“记住我”后 30 天免登录

# 让 jsonify 直接输出中文，而不是 \uXXXX 转义
try:
    app.json.ensure_ascii = False          # Flask 2.3+
except AttributeError:
    app.config['JSON_AS_ASCII'] = False    # Flask 2.2 及以下兼容

db.init_app(app)

# ---------------------------------------------------------------- 认证（Flask-Login）

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'      # 未登录自动跳转 /login，并携带 next 参数
login_manager.login_message = None      # 不使用 flash 消息


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@app.before_request
def check_session_revoked():
    """按用户注销：退出登录后，该用户此前签发的所有旧 Cookie 立即失效"""
    if current_user.is_authenticated:
        invalid_before = current_user.tokens_invalid_before
        login_at = float(session.get('login_at', 0))
        if invalid_before is not None and login_at < invalid_before.timestamp():
            logout_user()
            session.clear()
    return None


DEFAULT_SUBJECTS = ['政治', '英语', '数学', '专业课']
WEEKDAY_NAMES = ['一', '二', '三', '四', '五', '六', '日']
EXPENSE_CATEGORIES = ['餐饮', '资料费', '文具', '住宿', '交通', '娱乐', '其他']


def init_db():
    """建表；检测旧版单用户数据库并提示重置"""
    db.create_all()
    try:
        cols = [row[1] for row in db.session.execute(db.text('PRAGMA table_info(subjects)'))]
        if cols and 'user_id' not in cols:
            print('=' * 56)
            print('  [!] 检测到旧版单用户数据库（subjects 缺少 user_id 列）')
            print('  多用户架构需要重建表结构。')
            print('  1) 备份数据：复制 instance/data.db 保存到别处')
            print('  2) 执行重置：python reset_db.py')
            print('=' * 56)
    except Exception:
        pass


def create_default_subjects(user):
    """为新注册用户创建默认科目"""
    for i, name in enumerate(DEFAULT_SUBJECTS):
        db.session.add(Subject(user_id=user.id, name=name, sort_order=i))


with app.app_context():
    init_db()


# ---------------------------------------------------------------- 工具函数

def error(message, code=400):
    return jsonify({'error': message}), code


def parse_date(value):
    """把字符串解析为 date，失败返回 (None, 错误信息)"""
    if not value:
        return None, '日期不能为空'
    try:
        return date.fromisoformat(str(value)), None
    except (TypeError, ValueError):
        return None, '日期格式不正确（应为 YYYY-MM-DD）'


def _parse_period_param(value, lo, hi):
    """解析年/月参数：None 或空串 → 'all'（全部），非法值 → 'invalid'，否则返回整数"""
    if value is None or str(value).strip() == '':
        return 'all'
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return 'invalid'
    if not lo <= n <= hi:
        return 'invalid'
    return n


def validate_record_payload(data):
    """校验并清洗记录表单数据（含科目归属校验），返回 (payload, 错误信息)"""
    d, err = parse_date(data.get('date'))
    if err:
        return None, err

    try:
        subject_id = int(data.get('subject_id'))
    except (TypeError, ValueError):
        return None, '请选择有效的科目'
    subject = db.session.get(Subject, subject_id)
    if subject is None or subject.user_id != current_user.id:
        return None, '请选择有效的科目'

    try:
        minutes = int(data.get('minutes'))
    except (TypeError, ValueError):
        return None, '学习时长必须是整数（分钟）'
    if minutes <= 0:
        return None, '学习时长必须大于 0'
    if minutes > 24 * 60:
        return None, '学习时长不能超过一天（1440 分钟）'

    try:
        mastery = int(data.get('mastery', 0))
    except (TypeError, ValueError):
        return None, '掌握度必须是 0-100 的整数'
    if not 0 <= mastery <= 100:
        return None, '掌握度必须在 0-100 之间'

    summary = str(data.get('summary') or '').strip()
    return {
        'study_date': d,
        'subject_id': subject_id,
        'minutes': minutes,
        'mastery': mastery,
        'summary': summary,
    }, None


def validate_diary_payload(data):
    """校验并清洗日记表单数据，返回 (payload, 错误信息)"""
    d, err = parse_date(data.get('date'))
    if err:
        return None, err

    content = str(data.get('content') or '').strip()
    if not content:
        return None, '日记内容不能为空'

    title = str(data.get('title') or '').strip()[:100]
    mood = str(data.get('mood') or '').strip()[:20]
    return {
        'entry_date': d,
        'title': title,
        'content': content,
        'mood': mood,
    }, None


def diary_streak(user_id):
    """某用户连续写日记天数：从今天（或昨天）往前连续计算"""
    dates = {
        row[0] for row in db.session.query(Diary.entry_date)
        .filter(Diary.user_id == user_id).all()
    }
    if not dates:
        return 0
    today = date.today()
    cursor = today if today in dates else today - timedelta(days=1)
    streak = 0
    while cursor in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


# ---------------------------------------------------------------- 认证路由

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = str(request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        confirm = request.form.get('confirm_password') or ''
        email = str(request.form.get('email') or '').strip() or None

        if not (2 <= len(username) <= 20):
            error = '用户名长度需在 2-20 个字符之间'
        elif password != confirm:
            error = '两次输入的密码不一致'
        elif len(password) < 6:
            error = '密码至少 6 位'
        elif email and ('@' not in email or len(email) > 120):
            error = '邮箱格式不正确'
        elif User.query.filter_by(username=username).first():
            error = '用户名已被占用'
        else:
            user = User(username=username, email=email,
                        password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.flush()           # 先拿到 user.id
            create_default_subjects(user)
            db.session.commit()
            login_user(user, remember=False)
            session['login_at'] = time.time()
            return redirect(url_for('index'))
    return render_template('register.html', error=error)


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    next_url = request.values.get('next') or '/'
    # 防开放重定向：只允许站内相对路径
    if not next_url.startswith('/') or next_url.startswith('//'):
        next_url = '/'

    if request.method == 'POST':
        username = str(request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        remember = request.form.get('remember') == 'on'
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=remember)   # remember=True → 30 天免登录
            session['login_at'] = time.time()
            return redirect(next_url)
        error = '用户名或密码错误'

    return render_template('login.html', error=error, next=next_url)


@app.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    # 记录注销时间，使该用户此前签发的所有会话立即失效
    current_user.tokens_invalid_before = datetime.now()
    db.session.commit()
    logout_user()
    session.clear()
    return redirect(url_for('login'))


# ---------------------------------------------------------------- 页面

@app.get('/healthz')
def healthz():
    """健康检查端点（公开，不依赖登录与数据库），供 Render 探活使用"""
    return jsonify({'status': 'ok'})


@app.get('/')
@login_required
def index():
    return render_template('index.html')


# ---------------------------------------------------------------- 仪表盘

@app.get('/api/dashboard')
@login_required
def api_dashboard():
    uid = current_user.id
    today = date.today()

    # 近 7 天（含今天）每日总时长
    trend = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        minutes = (
            db.session.query(db.func.coalesce(db.func.sum(Record.minutes), 0))
            .filter(Record.user_id == uid, Record.study_date == d)
            .scalar()
        )
        trend.append({
            'date': d.isoformat(),
            'label': f"{d.month}/{d.day} 周{WEEKDAY_NAMES[d.weekday()]}",
            'minutes': int(minutes),
        })

    total_minutes = int(
        db.session.query(db.func.coalesce(db.func.sum(Record.minutes), 0))
        .filter(Record.user_id == uid).scalar()
    )
    total_days = int(
        db.session.query(db.func.count(db.func.distinct(Record.study_date)))
        .filter(Record.user_id == uid).scalar()
    )
    today_minutes = int(
        db.session.query(db.func.coalesce(db.func.sum(Record.minutes), 0))
        .filter(Record.user_id == uid, Record.study_date == today).scalar()
    )

    # 各科掌握度 = 该用户该科最近一条记录的掌握度
    subjects = []
    for s in Subject.query.filter_by(user_id=uid).order_by(Subject.sort_order, Subject.id).all():
        last = (
            Record.query.filter_by(user_id=uid, subject_id=s.id)
            .order_by(Record.study_date.desc(), Record.id.desc())
            .first()
        )
        subjects.append({
            'id': s.id,
            'name': s.name,
            'mastery': last.mastery if last else 0,
        })

    # 近 7 天花费（记账模块）
    expense_days = []
    expense_total = 0.0
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        amt = float(
            db.session.query(db.func.coalesce(db.func.sum(Expense.amount), 0.0))
            .filter(Expense.user_id == uid, Expense.date == d)
            .scalar()
        )
        expense_total += amt
        expense_days.append({
            'date': d.isoformat(),
            'label': f"{d.month}/{d.day}",
            'amount': round(amt, 2),
        })

    record_count = int(
        db.session.query(db.func.count(Record.id)).filter(Record.user_id == uid).scalar()
    )
    diary_count = int(
        db.session.query(db.func.count(Diary.id)).filter(Diary.user_id == uid).scalar()
    )
    expense_count = int(
        db.session.query(db.func.count(Expense.id)).filter(Expense.user_id == uid).scalar()
    )

    return jsonify({
        'total_days': total_days,
        'total_minutes': total_minutes,
        'today_minutes': today_minutes,
        'diary_streak': diary_streak(uid),
        'record_count': record_count,
        'diary_count': diary_count,
        'expense_count': expense_count,
        'expense7': {
            'total': round(expense_total, 2),
            'days': expense_days,
        },
        'trend': trend,
        'subjects': subjects,
    })


# ---------------------------------------------------------------- 科目管理

@app.get('/api/subjects')
@login_required
def api_subjects():
    subjects = Subject.query.filter_by(user_id=current_user.id) \
        .order_by(Subject.sort_order, Subject.id).all()
    return jsonify([s.to_dict() for s in subjects])


@app.post('/api/subjects')
@login_required
def api_add_subject():
    data = request.get_json(silent=True) or {}
    name = str(data.get('name') or '').strip()
    if not name:
        return error('科目名称不能为空')
    if len(name) > 50:
        return error('科目名称过长（最多 50 字）')
    if Subject.query.filter_by(user_id=current_user.id, name=name).first():
        return error(f'科目「{name}」已存在')

    max_order = db.session.query(db.func.max(Subject.sort_order)) \
        .filter(Subject.user_id == current_user.id).scalar() or 0
    subject = Subject(user_id=current_user.id, name=name, sort_order=max_order + 1)
    db.session.add(subject)
    db.session.commit()
    return jsonify(subject.to_dict()), 201


@app.delete('/api/subjects/<int:sid>')
@login_required
def api_delete_subject(sid):
    subject = db.session.get(Subject, sid)
    if subject is None or subject.user_id != current_user.id:
        return error('科目不存在', 404)
    db.session.delete(subject)  # 级联删除该科目下所有记录
    db.session.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------- 学习记录

@app.get('/api/records')
@login_required
def api_records():
    query = Record.query.filter_by(user_id=current_user.id)

    date_str = request.args.get('date')
    subject_id = request.args.get('subject_id')

    if date_str:
        d, err = parse_date(date_str)
        if err:
            return error(err)
        query = query.filter(Record.study_date == d)

    if subject_id:
        try:
            query = query.filter(Record.subject_id == int(subject_id))
        except ValueError:
            return error('科目参数不正确')

    records = query.order_by(Record.study_date.desc(), Record.id.desc()).all()
    return jsonify([r.to_dict() for r in records])


@app.post('/api/records')
@login_required
def api_add_record():
    payload, err = validate_record_payload(request.get_json(silent=True) or {})
    if err:
        return error(err)
    record = Record(user_id=current_user.id, **payload)
    db.session.add(record)
    db.session.commit()
    return jsonify(record.to_dict()), 201


@app.put('/api/records/<int:rid>')
@login_required
def api_update_record(rid):
    record = db.session.get(Record, rid)
    if record is None or record.user_id != current_user.id:
        return error('记录不存在', 404)
    payload, err = validate_record_payload(request.get_json(silent=True) or {})
    if err:
        return error(err)
    for key, value in payload.items():
        setattr(record, key, value)
    db.session.commit()
    return jsonify(record.to_dict())


@app.delete('/api/records/<int:rid>')
@login_required
def api_delete_record(rid):
    record = db.session.get(Record, rid)
    if record is None or record.user_id != current_user.id:
        return error('记录不存在', 404)
    db.session.delete(record)
    db.session.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------- 学习日记

@app.get('/api/diaries')
@login_required
def api_diaries():
    query = Diary.query.filter_by(user_id=current_user.id)

    month = (request.args.get('month') or '').strip()   # 形如 2025-08
    keyword = (request.args.get('keyword') or '').strip()

    if month:
        try:
            year, mon = month.split('-')
            start = date(int(year), int(mon), 1)
            # 下个月 1 号（右开区间终点）
            end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        except (ValueError, TypeError):
            return error('月份格式不正确（应为 YYYY-MM）')
        query = query.filter(Diary.entry_date >= start, Diary.entry_date < end)

    if keyword:
        like = f'%{keyword}%'
        query = query.filter(db.or_(Diary.title.like(like), Diary.content.like(like)))

    diaries = query.order_by(Diary.entry_date.desc(), Diary.id.desc()).all()
    return jsonify([d.to_dict() for d in diaries])


@app.post('/api/diaries')
@login_required
def api_add_diary():
    payload, err = validate_diary_payload(request.get_json(silent=True) or {})
    if err:
        return error(err)

    # 每个用户一天一篇：同日期已有日记则覆盖更新
    existing = Diary.query.filter_by(
        user_id=current_user.id, entry_date=payload['entry_date']
    ).first()
    if existing:
        for key, value in payload.items():
            setattr(existing, key, value)
        db.session.commit()
        return jsonify({'created': False, 'entry': existing.to_dict()})

    diary = Diary(user_id=current_user.id, **payload)
    db.session.add(diary)
    db.session.commit()
    return jsonify({'created': True, 'entry': diary.to_dict()}), 201


@app.put('/api/diaries/<int:did>')
@login_required
def api_update_diary(did):
    diary = db.session.get(Diary, did)
    if diary is None or diary.user_id != current_user.id:
        return error('日记不存在', 404)

    payload, err = validate_diary_payload(request.get_json(silent=True) or {})
    if err:
        return error(err)

    conflict = Diary.query.filter(
        Diary.user_id == current_user.id,
        Diary.entry_date == payload['entry_date'],
        Diary.id != did,
    ).first()
    if conflict:
        return error('该日期已有日记，不能重复创建')

    for key, value in payload.items():
        setattr(diary, key, value)
    db.session.commit()
    return jsonify(diary.to_dict())


@app.delete('/api/diaries/<int:did>')
@login_required
def api_delete_diary(did):
    diary = db.session.get(Diary, did)
    if diary is None or diary.user_id != current_user.id:
        return error('日记不存在', 404)
    db.session.delete(diary)
    db.session.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------- 记账

@app.get('/expenses')
@login_required
def expenses_page():
    uid = current_user.id
    query = Expense.query.filter_by(user_id=uid)

    category = (request.args.get('category') or '').strip()
    start = (request.args.get('start') or '').strip()
    end = (request.args.get('end') or '').strip()

    # ---------- 年 / 月周期参数（首次进入默认当前年 + 当前月） ----------
    today = date.today()
    current_year, current_month = today.year, today.month
    year_raw = request.args.get('year')
    month_raw = request.args.get('month')

    if year_raw is None and month_raw is None:
        year, month = current_year, current_month
    else:
        year = _parse_period_param(year_raw, 1970, 2200)
        month = _parse_period_param(month_raw, 1, 12)
        if year == 'invalid':
            return error('年份格式不正确（应为 YYYY）')
        if month == 'invalid':
            return error('月份格式不正确（应为 1-12）')
        year = None if year == 'all' else year
        month = None if month == 'all' else month

    # 列表按所选周期过滤（选月份 → 该月；只选年份 → 该年；全部 → 不过滤）
    if year is not None:
        if month is not None:
            period_start = date(year, month, 1)
            period_end = (period_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        else:
            period_start = date(year, 1, 1)
            period_end = date(year + 1, 1, 1)
        query = query.filter(Expense.date >= period_start, Expense.date < period_end)

    # 年份下拉范围：该用户最早记录年份 → 当前年份（无记录时只有当前年份）
    earliest = db.session.query(db.func.min(Expense.date)) \
        .filter(Expense.user_id == uid).scalar()
    min_year = earliest.year if earliest else current_year
    years = list(range(current_year, min_year - 1, -1))

    # ---------- 聚合统计（extract + func.sum，按用户隔离） ----------
    # 年度统计
    if year is not None:
        year_total = float(db.session.query(
            db.func.coalesce(db.func.sum(Expense.amount), 0.0)
        ).filter(Expense.user_id == uid, extract('year', Expense.date) == year).scalar())
        year_label = f'{year} 年'
    else:
        year_total = float(db.session.query(
            db.func.coalesce(db.func.sum(Expense.amount), 0.0)
        ).filter(Expense.user_id == uid).scalar())
        year_label = '全部年份'

    # 月度统计
    if year is not None and month is not None:
        month_total = float(db.session.query(
            db.func.coalesce(db.func.sum(Expense.amount), 0.0)
        ).filter(Expense.user_id == uid,
                 extract('year', Expense.date) == year,
                 extract('month', Expense.date) == month).scalar())
        month_label = f'{year} 年 {month} 月'
    elif year is not None:
        month_total = year_total
        month_label = f'{year} 年全年'
    else:
        month_total = float(db.session.query(
            db.func.coalesce(db.func.sum(Expense.amount), 0.0)
        ).filter(Expense.user_id == uid,
                 extract('year', Expense.date) == current_year,
                 extract('month', Expense.date) == current_month).scalar())
        month_label = f'本月（{current_year} 年 {current_month} 月）'

    # ---------- 原有筛选（类别 / 日期范围） ----------
    filtered = False
    if category:
        if category not in EXPENSE_CATEGORIES:
            return error('类别不正确')
        query = query.filter(Expense.category == category)
        filtered = True
    if start:
        d, err = parse_date(start)
        if err:
            return error(err)
        query = query.filter(Expense.date >= d)
        filtered = True
    if end:
        d, err = parse_date(end)
        if err:
            return error(err)
        query = query.filter(Expense.date <= d)
        filtered = True
    # 周期偏离默认值也算“筛选”
    if not (year == current_year and month == current_month):
        filtered = True

    expenses = query.order_by(Expense.date.desc(), Expense.id.desc()).all()
    total = round(float(sum(e.amount for e in expenses)), 2)
    return render_template(
        'expenses.html',
        expenses=expenses,
        total=total,
        categories=EXPENSE_CATEGORIES,
        category=category,
        start=start,
        end=end,
        filtered=filtered,
        month_total=round(month_total, 2),
        month_label=month_label,
        year_total=round(year_total, 2),
        year_label=year_label,
        year=year,
        month=month,
        years=years,
    )


@app.get('/expense/add')
@login_required
def expense_add_page():
    return render_template(
        'expense_add.html',
        categories=EXPENSE_CATEGORIES,
        form={},
        error=None,
        today=date.today().isoformat(),
    )


@app.post('/expense/add')
@login_required
def expense_add_submit():
    form = request.form

    try:
        amount = float(str(form.get('amount') or '').strip())
    except (TypeError, ValueError):
        amount = 0.0
    if amount <= 0:
        return render_template('expense_add.html', categories=EXPENSE_CATEGORIES,
                               form=form, error='金额必须是大于 0 的数字', today=date.today().isoformat())
    if amount > 1000000:
        return render_template('expense_add.html', categories=EXPENSE_CATEGORIES,
                               form=form, error='金额过大', today=date.today().isoformat())

    category = str(form.get('category') or '').strip()
    if category not in EXPENSE_CATEGORIES:
        return render_template('expense_add.html', categories=EXPENSE_CATEGORIES,
                               form=form, error='请选择有效的支出类别', today=date.today().isoformat())

    d, err = parse_date(form.get('date'))
    if err:
        return render_template('expense_add.html', categories=EXPENSE_CATEGORIES,
                               form=form, error=err, today=date.today().isoformat())

    description = str(form.get('description') or '').strip()[:200]
    expense = Expense(user_id=current_user.id, amount=round(amount, 2),
                      category=category, date=d, description=description)
    db.session.add(expense)
    db.session.commit()
    return redirect('/expenses')


@app.post('/expense/delete/<int:eid>')
@login_required
def expense_delete(eid):
    expense = db.session.get(Expense, eid)
    if expense is None or expense.user_id != current_user.id:
        return error('记录不存在', 404)
    db.session.delete(expense)
    db.session.commit()
    return redirect('/expenses')


# ---------------------------------------------------------------- 启动

if __name__ == '__main__':
    # 本地开发服务器：从环境变量读取端口，绑定 0.0.0.0 供局域网访问。
    # 部署到 Render 时使用 gunicorn app:app，由平台注入 PORT 环境变量。
    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('PORT', 5000))

    print('=' * 52)
    print('  研途 · 考研学习进度追踪')
    print(f'  本机访问:   http://127.0.0.1:{PORT}')
    print(f'  局域网访问: http://<本机IP>:{PORT}  (ipconfig 查看 IPv4)')
    print(f'  数据库:     {DB_PATH}')
    print('=' * 52)
    app.run(host=HOST, port=PORT, debug=False)
