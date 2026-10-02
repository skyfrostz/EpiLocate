# 第二轮医学影像工作台重构

日期：2026-10-02；分支 `feature/frontend-redesign-phase5`；起点 `a97a34688d5e5057681ecdcc38340adf1be3cd05`。

## 实现

- Login 桌面介绍/表单双栏、移动单栏，保留原登录与密码清理行为。
- 全局中文工作台导航、跳转主要内容、44 px 控件、清晰焦点及移动菜单键盘循环/Escape。进入平板宽度自动关闭移动菜单并解除主区 inert。
- 首页独立读取 Case API 第一页 6 条记录，保持服务端顺序，不假设时间排序；有加载/空/失败/刷新，不计算全局统计。请求与会话/页面版本核对，离开时取消，不污染病例中心分页。
- Case 状态中文化，按输入、影像浏览、启动分析分区；Job 提供关联病例导航，保留查询与失败恢复。
- Result CT 优先 DOM；桌面主画布和分类/独立热图侧栏；平板按实际容器宽度重排，手机单列；Case/Job/Slice 上下文可追溯，模型来源默认折叠。
- 统一字号、颜色、边框、恢复提示及操作尺寸；扩大 CT 画布，使用容器查询避免放大显示时挤压影像。保留尺度/图层/透明度/缩放/重置及原几何门控。

没有新增 API、服务端类型、窗宽窗位、多切片或双指缩放。未修改 Backend、Gateway、Worker、Landing、算法、数据库或冻结资产。展示效果来自工作流程与信息层次，没有内置伪造结果。

## 验收

- 原始 81 项基础上增加首页 3 项、移动菜单尺寸变化 1 项，共 **85 项 / 15 spec**；本机 Node 24.19.0 测试通过，TypeScript/Vite build 通过。
- 本地 Edge 合成 API 浏览器 **18 场景、19 截图、0 page error**，保留所有第一轮流程/会话/缓存验收，新增 1440/1100/768/390/360 px、200% CSS 放大、键盘折叠、Escape 焦点及手机菜单打开后放大窗口验收。CSS 放大用于布局压力测试，不声称逐一模拟所有浏览器原生 zoom 行为。
- geometry harness 采用新 Result 画布样式，非方形/旋转/不同间距影像 6 组各测 5 marker，最大误差 **0.3222 CSS px**，低于 1 px。窗口变化时实际画布宽度由 1060 变为 860 px；core/NATURALIZED 缓存清理继续通过。
- 桌面、手机、平板、放大页面截图视觉复核通过。最初放大页面双栏挤压影像，改为容器查询重排后复验通过；最初移动菜单跨断点保留 inert，新增 matchMedia 清理与测试。
- 原有 codec 外部化及 bundle 大小警告保留，不作为新修复结论。根目录文档门禁及 diff 检查纳入提交前检查。

合成数据与实际 Cornerstone 解码/渲染用于本地验收，没有真实账号/患者资料或 GPU 推理。测试产物在本机交付目录 `frontend-round2/`。

## 发布方式与剩余事项

用户已选择全页面完成即发布：验证与敏感信息检查后普通推送指定分支，从固定提交导出前端源码传到独立服务器目录，服务器锁定安装/测试及 `/mvp/` build；仅切换前端 Nginx root，保留旧目录与配置备份。发布后核对首页/静态资源及真实未登录桌面/手机浏览器。

2026-10-02 已完成发布，应用源码为 `988328f53c44a1542e95707951163a14d7b9eb05`，GitHub 指定分支已普通推送并核对。真实账号登录后操作与 GPU 恢复后的推理 E2E 仍未验收；临床定位、多切片及 CPU/GPU 数值门槛不属于本轮。仓库目录迁移和清理继续推迟，不作为本次视觉发布的一部分。


## 实际发布记录

- 完整 Git closure 扫描 673 objects / 507 blobs，新增 16 blobs，无阻断发现；固定提交 frontend 归档 SHA256 `db4d8d3089d1a1c26da1a286653b64c6af611713851424f8eb39437359720081`，服务器核对一致。
- 服务器 Node 24.21.0 锁定安装、**85/85 测试、15 spec、build PASS**。新目录 `/opt/epilocate-mvp/frontend-releases/988328f53c44a1542e95707951163a14d7b9eb05`；仅切换前端静态 root，保留旧目录和新目录下 `nginx-before.conf`。旧 hashed assets 保留供已开页面使用。
- Nginx 配置检查与重载通过，实际首页与 2 个入口 JS/CSS 字节核对一致。Backend/Gateway/Sweeper/MinIO active；控制平面 current 仍是原 `4e38fd32765e7c69ae0b7389cb91fe057c938472` release。
- 发布后 HTTPS `/mvp/` 200，无 Cookie `/auth/session` 与 `/api/v2/cases` 401，`/welcome/` 200；另外观测 `/review/` 307、`/review` 401，与上一轮记录的 303 不同，未据此宣称 Review 完整功能通过，也未修改该应用。
- 外部 Edge 检查真实未登录桌面 1440 px / 手机 390 px：新版登录布局、受保护 Case 重定向、键盘焦点及无水平溢出 PASS；0 page error、0 静态资源失败。通过已核实 IP 映射访问域名，保持 TLS 验证。
- 初次服务器准备脚本存在 CRLF 导致 shell 在开始时退出；修正为 LF 后完整运行通过，该失败发生在前端切换之前。
- 本机证据：`round2-publication-scan.json`、`round2-server-activation.json`、`round2-live-frontend-acceptance.json`、`frontend-round2/` 截图。文档补录提交不改变线上应用 SHA。
