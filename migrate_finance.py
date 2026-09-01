# -*- coding: utf-8 -*-
"""一次性迁移：旧版 expenses 表（category 字符串）→ 收支双向结构
- 保留旧账单数据（全部按「支出」类型迁移，类别名自动建为支出类别）
- 为已有账户补齐默认收支类别
- 幂等 / 可续跑：无论上次中断在哪一步都能安全重跑
"""
import sys

sys.path.insert(0, '.')
from sqlalchemy import text

from app import app, db, create_default_categories
from models import Category, Expense, User

with app.app_context():
    def table_exists(name):
        row = db.session.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=:n"
        ), {'n': name}).first()
        return row is not None

    legacy_rows = []
    if table_exists('expenses_legacy'):
        legacy_rows = db.session.execute(text(
            'SELECT user_id, amount, category, description, date FROM expenses_legacy'
        )).fetchall()
        print(f'旧账单数据 {len(legacy_rows)} 条')

    # 1. 清理旧索引（SQLite 索引名全局唯一，会与新建表索引冲突）
    for idx in ('ix_expenses_user_id', 'ix_expenses_date', 'ix_expenses_category',
                'ix_expenses_category_id', 'ix_expenses_transaction_type'):
        db.session.execute(text(f'DROP INDEX IF EXISTS {idx}'))
    db.session.commit()

    # 2. 删除 expenses 表（无论新旧/半成品），由 create_all 按新结构统一重建
    db.session.execute(text('DROP TABLE IF EXISTS expenses'))
    db.session.commit()
    db.create_all()
    print('expenses 表已按收支双向结构重建')

    # 3. 为已有账户补齐默认收支类别
    created = 0
    for u in User.query.all():
        if Category.query.filter_by(user_id=u.id).count() == 0:
            create_default_categories(u)
            created += 1
    db.session.commit()
    print(f'已为 {created} 个账户补齐默认类别（当前共 {User.query.count()} 个账户）')

    # 4. 迁移旧账单（旧版只有支出概念）
    migrated = 0
    for r in legacy_rows:
        name = (r.category or '').strip()
        if not name:
            continue
        cat = Category.query.filter_by(user_id=r.user_id, name=name, type='expense').first()
        if cat is None:
            cat = Category(user_id=r.user_id, name=name, type='expense')
            db.session.add(cat)
            db.session.flush()
        db.session.add(Expense(
            user_id=r.user_id, transaction_type='expense', category_id=cat.id,
            amount=r.amount, description=r.description or '', date=r.date,
        ))
        migrated += 1
    db.session.commit()
    print(f'迁移旧账单 {migrated} 条')

    # 5. 删除旧表
    if table_exists('expenses_legacy'):
        db.session.execute(text('DROP TABLE expenses_legacy'))
        db.session.commit()
        print('旧表已删除')

    print('迁移完成！账单模块已切换为收支双向结构')
