# 研途追踪 · 考研学习进度追踪

Flask + SQLite 的考研学习进度追踪应用：仪表盘（学习统计 / 掌握度进度条 / 近 7 天趋势图 / 日记连续天数）、学习记录（按日期与科目筛选的增删改查）、学习日记（一天一篇，心情打卡）、科目管理、账单记账（月度/年度统计）。全站密码保护（登录后 7 天内免密），莫兰迪护眼配色，Bootstrap 5 + Chart.js，移动端自适应。

## 本地运行

```bash
pip install -r requirements.txt   # Windows 会自动跳过 gunicorn（仅 Linux 需要）
python app.py                     # 默认 http://127.0.0.1:5000，局域网也可访问
```

首次启动自动创建 `instance/data.db` 并写入默认科目（政治/英语/数学/专业课）。

## 访问密码（全站保护）

除登录页与静态资源外，所有页面都需要输入密码才能访问。

| 变量 | 作用 | 本地 | Render |
|---|---|---|---|
| `SITE_PASSWORD` | 站点访问密码 | 写入项目根目录 `.env`（复制 `.env.example` 改名） | Dashboard → Environment 中添加 |
| `SECRET_KEY` | 会话签名密钥（重部署后保持登录态的关键） | 自动生成并持久化在 `instance/.secret_key` | Blueprint 自动生成；手动创建时请自行添加 |

- 若两处都没配 `SITE_PASSWORD`，启动时会在控制台打印一个临时随机密码（仅应急用）；
- 登录成功后 7 天内免密（会话 Cookie）；侧边栏底部「退出登录」可立即注销；
- 未登录访问任何页面会跳转 `/login?next=...`，登录后自动回到原页面。

## 部署到 Render（24 小时在线）

### 一、推送到 GitHub

```bash
# 在 GitHub 网页上新建一个空仓库（不要勾选 README/.gitignore），例如 kaoyan-tracker
git init
git add -A
git commit -m "考研学习进度追踪 v1.0"
git branch -M main
git remote add origin https://github.com/<你的用户名>/kaoyan-tracker.git
git push -u origin main
```

### 二、在 Render 创建 Web Service

打开 https://dashboard.render.com → `New +` → **Web Service** → 连接你的 GitHub 仓库（或 `New +` → **Blueprint** 用仓库里的 `render.yaml` 一键创建），填写：

| 配置项 | 值 |
|---|---|
| Language | Python |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn app:app` |
| Instance Type | Free（免费） |

### 三、Python 版本

仓库根目录的 `.python-version`（内容 `3.11`）会自动指定 Python 3.11 最新补丁版，无需手动设置。也可以在服务的 `Environment` 里用 `PYTHON_VERSION=3.11.11` 覆盖。

### 四、环境变量（Dashboard → 你的服务 → Environment）

| 变量 | 值 | 说明 |
|---|---|---|
| `SECRET_KEY` | 一串随机字符串 | 会话加密密钥（render.yaml 蓝图中会自动生成） |
| `SITE_PASSWORD` | 你的访问密码 | **必设**：站点登录密码，否则每次部署后密码随机变化 |
| `DATABASE_PATH` | `instance/data.db` | 数据库位置，默认即可 |

### 五、关于数据持久化（重要）

Render 免费实例的文件系统是临时的，**重新部署时 `instance/` 下的数据会被清空**。若要长期保存数据：

1. 在服务页面左侧 **Disks** → 添加一块免费 1GB **Render Disk**，挂载路径填 `/var/data`；
2. 把环境变量 `DATABASE_PATH` 改为 `/var/data/data.db`。

### 六、访问地址

部署成功后即可访问：

```
https://<服务名>.onrender.com        # 例如 https://yantu-tracker.onrender.com
```

每次 push 到 GitHub 会自动触发重新部署（约 2-5 分钟生效）。

### 七、免费版注意事项

- 免费实例闲置约 15 分钟后休眠，下次访问有 30-60 秒冷启动；
- 想保持 7×24 在线，可用 [UptimeRobot](https://uptimerobot.com) 等工具每 5 分钟 ping 一次你的地址防止休眠，或升级付费实例。

## 常见问题

- **端口**：Render 自动注入 `PORT` 环境变量，`gunicorn app:app` 由平台接管绑定，无需手动配置。
- **gunicorn 在 Windows 装不上？** 正常现象：gunicorn 仅支持 Linux，`requirements.txt` 里用环境标记让 Windows 自动跳过，本地开发用 `python app.py` 即可。
- **数据库重置**：删除 `instance/data.db` 后重启，应用会重建数据库并恢复默认科目。
