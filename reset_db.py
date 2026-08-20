# -*- coding: utf-8 -*-
"""数据库重置脚本（多用户架构升级用，方案②）

用法：
    python reset_db.py

作用：删除所有表并按照最新的多用户架构重建（users / subjects / records /
      diaries / expenses，均含 user_id 外键）。

警告：会清空全部数据！执行前请先备份：
    - 本地：复制 instance/data.db 到别处（如 data.db.bak）
    - Render：在服务页 Shell 中先下载 /var/data/data.db（若挂了持久磁盘）

执行后启动应用，注册新账户即可使用（默认科目在注册时自动创建）。
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import app, db  # noqa: E402


def main():
    with app.app_context():
        db.drop_all()
        db.create_all()
    print('=' * 56)
    print('  数据库已重置：所有表已删除并按多用户架构重建')
    print('  新表结构：users / subjects / records / diaries / expenses')
    print('  启动应用后注册新账户即可使用（默认科目自动创建）')
    print('=' * 56)


if __name__ == '__main__':
    main()
