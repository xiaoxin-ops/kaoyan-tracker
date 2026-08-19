# -*- coding: utf-8 -*-
"""考研学习进度追踪 —— Flask 应用入口

本地启动方式：
    pip install -r requirements.txt
    python app.py
默认监听 0.0.0.0:5000，局域网内其他设备可通过 http://<本机IP>:5000 访问。

部署到 Render：
    Build Command:  pip install -r requirements.txt
    Start Command:  gunicorn app:app   （平台自动注入 PORT 并接管端口绑定）

数据库默认位于项目根下的 instance/data.db，首次启动自动创建并写入默认科目；
可通过环境变量 DATABASE_PATH 覆盖（如 Render 持久磁盘 /var/data/data.db）。
"""
import os
import secrets
import shutil
import sys
from datetime import date, timedelta

from flask import Flask, jsonify, render_template, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 兼容便携版 Python（embeddable）等不自动加入脚本目录的情况
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from models import Subject, Record, Diary, db
from sqlalchemy.exc import IntegrityError

# 数据库文件：默认放在项目根下的 instance/ 目录（Render 部署时该目录可写）；
# 可通过环境变量 DATABASE_PATH 覆盖（例如 Render 挂载持久磁盘后指向 /var/data/data.db）
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
os.makedirs(INSTANCE_DIR, exist_ok=True)
DB_PATH = os.path.abspath(os.environ.get('DATABASE_PATH', os.path.join(INSTANCE_DIR, 'data.db')))

# 兼容旧版本：旧版 study.db 存在而新位置还没有数据库时，自动迁移
LEGACY_DB = os.path.join(BASE_DIR, 'study.db')
if not os.path.exists(DB_PATH) and os.path.exists(LEGACY_DB):
    shutil.copyfile(LEGACY_DB, DB_PATH)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + DB_PATH
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(24)
# 让 jsonify 直接输出中文，而不是 \uXXXX 转义
try:
    app.json.ensure_ascii = False          # Flask 2.3+
except AttributeError:
    app.config['JSON_AS_ASCII'] = False    # Flask 2.2 及以下兼容

db.init_app(app)

DEFAULT_SUBJECTS = ['政治', '英语', '数学', '专业课']
WEEKDAY_NAMES = ['一', '二', '三', '四', '五', '六', '日']


def init_db():
    """建表 + 首次运行写入默认科目"""
    db.create_all()
    if Subject.query.count() == 0:
        try:
            for i, name in enumerate(DEFAULT_SUBJECTS):
                db.session.add(Subject(name=name, sort_order=i))
            db.session.commit()
        except IntegrityError:
            # 多进程（如 gunicorn 多 worker）并发启动时，另一进程已完成初始化
            db.session.rollback()


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


def validate_record_payload(data):
    """校验并清洗记录表单数据，返回 (payload, 错误信息)"""
    d, err = parse_date(data.get('date'))
    if err:
        return None, err

    try:
        subject_id = int(data.get('subject_id'))
    except (TypeError, ValueError):
        return None, '请选择有效的科目'
    if db.session.get(Subject, subject_id) is None:
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


def diary_streak():
    """连续写日记天数：从今天（或昨天）往前连续计算"""
    dates = {row[0] for row in db.session.query(Diary.entry_date).all()}
    if not dates:
        return 0
    today = date.today()
    cursor = today if today in dates else today - timedelta(days=1)
    streak = 0
    while cursor in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


# ---------------------------------------------------------------- 页面

@app.get('/')
def index():
    return render_template('index.html')


# ---------------------------------------------------------------- 仪表盘

@app.get('/api/dashboard')
def api_dashboard():
    today = date.today()

    # 近 7 天（含今天）每日总时长
    trend = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        minutes = (
            db.session.query(db.func.coalesce(db.func.sum(Record.minutes), 0))
            .filter(Record.study_date == d)
            .scalar()
        )
        trend.append({
            'date': d.isoformat(),
            'label': f"{d.month}/{d.day} 周{WEEKDAY_NAMES[d.weekday()]}",
            'minutes': int(minutes),
        })

    total_minutes = int(
        db.session.query(db.func.coalesce(db.func.sum(Record.minutes), 0)).scalar()
    )
    total_days = int(
        db.session.query(db.func.count(db.func.distinct(Record.study_date))).scalar()
    )
    today_minutes = int(
        db.session.query(db.func.coalesce(db.func.sum(Record.minutes), 0))
        .filter(Record.study_date == today)
        .scalar()
    )

    # 各科掌握度 = 该科最近一条记录的掌握度
    subjects = []
    for s in Subject.query.order_by(Subject.sort_order, Subject.id).all():
        last = (
            Record.query.filter_by(subject_id=s.id)
            .order_by(Record.study_date.desc(), Record.id.desc())
            .first()
        )
        subjects.append({
            'id': s.id,
            'name': s.name,
            'mastery': last.mastery if last else 0,
        })

    return jsonify({
        'total_days': total_days,
        'total_minutes': total_minutes,
        'today_minutes': today_minutes,
        'diary_streak': diary_streak(),
        'trend': trend,
        'subjects': subjects,
    })


# ---------------------------------------------------------------- 科目管理

@app.get('/api/subjects')
def api_subjects():
    subjects = Subject.query.order_by(Subject.sort_order, Subject.id).all()
    return jsonify([s.to_dict() for s in subjects])


@app.post('/api/subjects')
def api_add_subject():
    data = request.get_json(silent=True) or {}
    name = str(data.get('name') or '').strip()
    if not name:
        return error('科目名称不能为空')
    if len(name) > 50:
        return error('科目名称过长（最多 50 字）')
    if Subject.query.filter_by(name=name).first():
        return error(f'科目「{name}」已存在')

    max_order = db.session.query(db.func.max(Subject.sort_order)).scalar() or 0
    subject = Subject(name=name, sort_order=max_order + 1)
    db.session.add(subject)
    db.session.commit()
    return jsonify(subject.to_dict()), 201


@app.delete('/api/subjects/<int:sid>')
def api_delete_subject(sid):
    subject = db.session.get(Subject, sid)
    if subject is None:
        return error('科目不存在', 404)
    db.session.delete(subject)  # 级联删除该科目下所有记录
    db.session.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------- 学习记录

@app.get('/api/records')
def api_records():
    query = Record.query

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
def api_add_record():
    payload, err = validate_record_payload(request.get_json(silent=True) or {})
    if err:
        return error(err)
    record = Record(**payload)
    db.session.add(record)
    db.session.commit()
    return jsonify(record.to_dict()), 201


@app.put('/api/records/<int:rid>')
def api_update_record(rid):
    record = db.session.get(Record, rid)
    if record is None:
        return error('记录不存在', 404)
    payload, err = validate_record_payload(request.get_json(silent=True) or {})
    if err:
        return error(err)
    for key, value in payload.items():
        setattr(record, key, value)
    db.session.commit()
    return jsonify(record.to_dict())


@app.delete('/api/records/<int:rid>')
def api_delete_record(rid):
    record = db.session.get(Record, rid)
    if record is None:
        return error('记录不存在', 404)
    db.session.delete(record)
    db.session.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------- 学习日记

@app.get('/api/diaries')
def api_diaries():
    query = Diary.query

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
def api_add_diary():
    payload, err = validate_diary_payload(request.get_json(silent=True) or {})
    if err:
        return error(err)

    # 一天一篇：同日期已有日记则覆盖更新
    existing = Diary.query.filter_by(entry_date=payload['entry_date']).first()
    if existing:
        for key, value in payload.items():
            setattr(existing, key, value)
        db.session.commit()
        return jsonify({'created': False, 'entry': existing.to_dict()})

    diary = Diary(**payload)
    db.session.add(diary)
    db.session.commit()
    return jsonify({'created': True, 'entry': diary.to_dict()}), 201


@app.put('/api/diaries/<int:did>')
def api_update_diary(did):
    diary = db.session.get(Diary, did)
    if diary is None:
        return error('日记不存在', 404)

    payload, err = validate_diary_payload(request.get_json(silent=True) or {})
    if err:
        return error(err)

    conflict = Diary.query.filter(
        Diary.entry_date == payload['entry_date'], Diary.id != did
    ).first()
    if conflict:
        return error('该日期已有日记，不能重复创建')

    for key, value in payload.items():
        setattr(diary, key, value)
    db.session.commit()
    return jsonify(diary.to_dict())


@app.delete('/api/diaries/<int:did>')
def api_delete_diary(did):
    diary = db.session.get(Diary, did)
    if diary is None:
        return error('日记不存在', 404)
    db.session.delete(diary)
    db.session.commit()
    return jsonify({'ok': True})


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
