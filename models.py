# -*- coding: utf-8 -*-
"""考研学习进度追踪 —— 数据模型层

- Subject: 科目表（默认内置政治 / 英语 / 数学 / 专业课，支持增删）
- Record:  记录表（日期、科目、学习时长、内容摘要、掌握度百分比）
- Diary:   日记表（一天一篇：日期、心情、标题、正文）
- Expense: 支出表（考研花销记账：金额、类别、日期、备注）
"""
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Subject(db.Model):
    """科目表"""
    __tablename__ = 'subjects'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False, comment='科目名称')
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
    """日记表：一天一篇学习日记"""
    __tablename__ = 'diaries'

    id = db.Column(db.Integer, primary_key=True)
    entry_date = db.Column(db.Date, nullable=False, unique=True, index=True, comment='日记日期')
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


class Expense(db.Model):
    """支出表：考研花销记账"""
    __tablename__ = 'expenses'

    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False, comment='金额（元）')
    category = db.Column(db.String(50), nullable=False, index=True, comment='支出类别')
    description = db.Column(db.String(200), nullable=False, default='', comment='备注 / 用途描述')
    date = db.Column(db.Date, nullable=False, index=True, comment='支出日期')
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'amount': self.amount,
            'category': self.category,
            'description': self.description,
            'date': self.date.isoformat(),
        }
