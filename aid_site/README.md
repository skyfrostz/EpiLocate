# 辅助诊断项目网站

这是 `aid.xbstu.com` 的独立展示站点。它只展示立项目标、三阶段技术路线、五个规划模块、评测指标与实施节点，不提供医学判断，也不接收或保存真实影像。旧 `project.xbstu.com` 的代码、账号、会话和数据不在本项目中使用。

## 本地启动

要求 Python 3.12+。在本目录执行：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export AID_DATABASE_PATH="$PWD/data/aid-site.sqlite3"
.venv/bin/python -m aid_site.admin create-or-reset admin
.venv/bin/uvicorn aid_site.main:app --host 127.0.0.1 --port 8766
```

Windows 上将 `.venv/bin/` 换为 `.venv\Scripts\`，并用 PowerShell 的 `$env:AID_DATABASE_PATH` 设置数据库路径。管理员工具交互式读取密码，最低 16 字符；命令参数和源码中均不传密码。重新运行同一命令可重置账号密码，并撤销该账号旧会话。

正式部署使用独立的 `aid-site` 系统账号、`/opt/aid-site` 代码、`/var/lib/aid-site` SQLite 数据库、`127.0.0.1:8766` 端口、独立 systemd 单元和独立 Nginx 站点文件。HTTPS 证书由 Let's Encrypt 为 `aid.xbstu.com` 单独签发。部署配置样例见 `deploy/`。

## 访问控制

- 全部内容页和 `/api/v1` 路由要求登录；只有登录页、静态资源和运行健康探针公开。
- Argon2id 存储密码哈希。会话令牌仅存 SHA-256 摘要，浏览器使用 `Secure`、`HttpOnly`、`SameSite=Strict` 的 `__Host-` Cookie。
- 登录、退出与修改类 API 请求校验 CSRF 令牌；Nginx 限制登录频率与请求体大小。
- 对接契约及占位状态详见 [API.md](API.md)。

## 验收方式

```bash
curl -I https://aid.xbstu.com/
curl -i https://aid.xbstu.com/api/v1/capabilities
curl -I https://project.xbstu.com/login
```

首次访问 `/` 应跳转 `/login`，未登录 API 应返回 `401`。登录后导航应显示完整六个内容页，能力查询返回各业务能力 `NOT_CONNECTED`；携带有效 CSRF 令牌调用占位业务路由应返回 `503` 与结构化 `NOT_CONNECTED`。真实影像上传不受理。无研究成果数据写入此站点。
