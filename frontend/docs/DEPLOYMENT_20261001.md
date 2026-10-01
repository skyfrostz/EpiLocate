# 第一轮前端发布记录

日期：2026-10-01（Asia/Shanghai）。本次用户明确授权推送 GitHub 与上传发布服务器。

## 已发布

- GitHub：`skyfrostz/EpiLocate` 的 `feature/frontend-redesign-phase5`，应用提交 `3ad9fbc0d8dba4b16585c94dd16f5375be276f98`；普通 push 成功，随后 SSH ls-remote 核对一致。
- 入口：<https://project.xbstu.com/mvp/>。
- 前端目录：`/opt/epilocate-mvp/frontend-releases/3ad9fbc0d8dba4b16585c94dd16f5375be276f98/mvp/`。
- 本次仅切换 Nginx `/mvp/` 静态根路径。Backend/Gateway/Sweeper/MinIO 仍为 active，控制平面 `current` 仍指向原 `4e38fd32765e7c69ae0b7389cb91fe057c938472` release；Landing 和 Review 未切换。

服务器 GitHub HTTPS 连接超时，因此从本机已推送的固定 Git 提交使用 `git archive HEAD frontend` 导出并传输。未传 GitHub 私钥、环境文件、模型权重或影像。归档 SHA-256：`04fa6a662e7fb39d2ae2b64c090011945e2bdbe0596ea641ebaf4c4da9eff1ad`；服务器解包前校验通过，写入内部 SOURCE_COMMIT。

## 验证

1. 发布前完整 Git closure 扫描：636 objects，488 blobs，3 DOCX/61 内部成员；53 个候选均分类为非阻断。唯一 DICOM 与已批准合成样本一致；无新增二进制影像、实际凭证或患者标识。脱敏记录：交付目录 `publication-scan.json`。
2. 服务器 Node 24.21.0；锁定安装 314 packages；81/81 测试、14 spec 文件通过；`VITE_PUBLIC_BASE=/mvp/ npm run build` 通过。原有 codec 浏览器外部化及包体积警告仍在。
3. Nginx 配置检查通过、reload 完成；实际 HTTPS 首页字节与新构建一致，2 个首页入口 JS/CSS 内容与文件字节一致。入口 HTML SHA-256：`7b9bb380dc49cfb68042abc373946dbd44506767c6692d8cce85fcf8a815bf52`。
4. 发布后 `/mvp/` 200；无 Cookie `/auth/session` 与 `/api/v2/cases` 均 401；`/welcome/` 200，Review 根入口 303，与发布前一致。
5. 外部 Edge 桌面与移动浏览器：真实 `/mvp/cases` 跳转至 `/mvp/login?next=/cases`；登录 UI、键盘焦点及移动无水平溢出通过，0 page error、0 静态资源失败。首次默认 DNS 浏览器导航超时，第二次将已知域名映射至服务器 IP，保留 HTTPS 域名与证书校验后通过。没有提交账号密码或进行真实推理。
6. 本地合成浏览器 15 场景、几何 6 组验收仍有效；它们与本次线上未登录检查是不同证据范围。

交付目录包含 `server-frontend-activation.json`、`live-frontend-acceptance.json`、`frontend-qa/live-login-desktop.png` 与 `live-login-mobile.png`。服务器完整构建日志保留于 `/tmp/epilocate-prepare-frontend-3ad9fbc.log`。

## 切换与回滚

第一次 reload 后立即读取到了旧 worker 提供的首页，内容校验失败触发自动回滚。确认响应哈希与旧首页完全一致后，增加最长 10 秒的重复校验，再次激活成功。没有将首次切换记为通过。

旧前端仍位于原 release；配置备份为新前端 release 下的 `nginx-before.conf`。新目录保留旧 content-addressed assets，便于已打开的标签页继续读取旧资源。若需回滚，恢复该备份至 `/etc/nginx/snippets/epilocate-mvp.conf`，先 `nginx -t`，再 reload；不切换控制平面 `current`。

## 完成程度

**已完成：** 第一轮计划中的稳定性修复、页面审计、接口缺口清单、下一轮草图、自动化回归与构建；根工程文档门禁；指定分支推送；服务器前端发布及未登录浏览器检查。

**未完成：** 授权真实测试账号登录后的上传、任务/结果操作验收；GPU 重新提供后的真实推理 E2E。当前没有这两项通过证据，不能声称完整线上链路全部验收完成。

整体视觉重构是下一轮工作。CPU/GPU 固定数值一致性、临床定位评测及生产成熟度不由此次前端发布证明。

本次发布后的记录提交仅补充文档；线上前端应用源码仍固定于上述应用提交。
