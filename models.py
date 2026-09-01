# -*- coding: utf-8 -*-
"""考研学习进度追踪 —— 数据模型层（多用户架构）

- User:    用户表（用户名 / 密码哈希 / 邮箱）
- Subject: 科目表（每个用户独立，注册时自动内置默认科目）
- Record:  记录表（日期、科目、学习时长、内容摘要、掌握度百分比）
- Diary:   日记表（每个用户一天一篇）
- Expense: 支出表（考研花销记账）

所有业务数据都通过 user_id 外键与用户关联，实现数据隔离。
"""
from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """用户表"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True, comment='用户名')
    password_hash = db.Column(db.String(255), nullable=False, comment='密码哈希')
    email = db.Column(db.String(120), nullable=True, comment='邮箱（可选）')
    created_at = db.Column(db.DateTime, default=datetime.now)
    # 退出登录时写入当前时间：签发时间早于它的旧会话 Cookie 一律失效
    tokens_invalid_before = db.Column(db.DateTime, nullable=True, comment='会话失效分界时间')

    subjects = db.relationship('Subject', backref='user', lazy=True, cascade='all, delete-orphan')
    records = db.relationship('Record', backref='user', lazy=True, cascade='all, delete-orphan')
    diaries = db.relationship('Diary', backref='user', lazy=True, cascade='all, delete-orphan')
    expenses = db.relationship('Expense', backref='user', lazy=True, cascade='all, delete-orphan')
    categories = db.relationship('Category', backref='user', lazy=True, cascade='all, delete-orphan')


class Subject(db.Model):
    """科目表（每个用户的科目相互独立）"""
    __tablename__ = 'subjects'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'name', name='uq_user_subject_name'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True, comment='所属用户')
    name = db.Column(db.String(50), nullable=False, comment='科目名称')
    sort_order = db.Column(db.Integer, nullable=False, default=0, comment='排序权重')
    created_at = db.Column(db.DateTime, default=datetime.now)

    # 删除科目时级联删除其下所有学习记录
    records = db.relationship(
        'Record',
        backref='subject',
        cascade='all, delete-orphan',
        lazy=True,
    )

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'record_count': len(self.records),
        }


class Record(db.Model):
    """记录表：每日学习打卡记录"""
    __tablename__ = 'records'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True, comment='所属用户')
    study_date = db.Column(db.Date, nullable=False, index=True, comment='学习日期')
    subject_id = db.Column(
        db.Integer, db.ForeignKey('subjects.id'), nullable=False, index=True, comment='科目ID'
    )
    minutes = db.Column(db.Integer, nullable=False, comment='学习时长（分钟）')
    summary = db.Column(db.Text, nullable=False, default='', comment='内容摘要')
    mastery = db.Column(db.Integer, nullable=False, default=0, comment='掌握度百分比 0-100')
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.study_date.isoformat(),
            'subject_id': self.subject_id,
            'subject': self.subject.name if self.subject else '',
            'minutes': self.minutes,
            'summary': self.summary,
            'mastery': self.mastery,
        }


class Diary(db.Model):
    """日记表：每个用户一天一篇学习日记"""
    __tablename__ = 'diaries'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'entry_date', name='uq_user_diary_date'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True, comment='所属用户')
    entry_date = db.Column(db.Date, nullable=False, index=True, comment='日记日期')
    title = db.Column(db.String(100), nullable=False, default='', comment='标题')
    content = db.Column(db.Text, nullable=False, comment='正文')
    mood = db.Column(db.String(20), nullable=False, default='', comment='心情标识（happy/calm/tired/anxious/motivated）')
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.entry_date.isoformat(),
            'title': self.title,
            'content': self.content,
            'mood': self.mood,
        }


class Category(db.Model):
    """收支类别表（每个用户自定义，注册时自动预置默认类别）"""
    __tablename__ = 'categories'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'name', 'type', name='uq_user_category_name_type'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True, comment='所属用户')
    name = db.Column(db.String(50), nullable=False, comment='类别名称')
    type = db.Column(db.String(10), nullable=False, index=True, comment='income（收入） / expense（支出）')
    is_default = db.Column(db.Boolean, nullable=False, default=False, comment='系统预置类别')
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'is_default': self.is_default,
        }


class Expense(db.Model):
    """收支记录表：收入与支出双向记账"""
    __tablename__ = 'expenses'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True, comment='所属用户')
    transaction_type = db.Column(db.String(10), nullable=False, index=True, comment='income / expense')
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False, index=True, comment='类别ID')
    amount = db.Column(db.Float, nullable=False, comment='金额（元）')
    description = db.Column(db.String(200), nullable=False, default='', comment='备注 / 用途描述')
    date = db.Column(db.Date, nullable=False, index=True, comment='收支日期')
    created_at = db.Column(db.DateTime, default=datetime.now)

    category = db.relationship('Category', backref='expenses', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat(),
            'transaction_type': self.transaction_type,
            'category_id': self.category_id,
            'category': self.category.name if self.category else '',
            'amount': self.amount,
            'description': self.description,
        }
