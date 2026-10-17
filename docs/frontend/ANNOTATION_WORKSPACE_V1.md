# 单切片医生多边形工作区 v1

本轮实现独立的棋盘测试影像（非真实CT）产品闭环：绘制直线多边形、编辑顶点、保存、刷新恢复、修改新版本、撤回与恢复、查看历史。它使用新 SQLite 和 TEST_STORAGE，通过原 Session Gateway 和后端 User 身份认证，不修改原 64-only 面板、历史数据库、冻结模型或研究协议。

开发前 HEAD：`46b9d0e005b8016f8b9b233dde6d419b481b551c`；分支 `codex/epi-next-integration-20261009`。本轮最终完整提交 SHA 由本地版本化交付索引记录，避免文档自引用。仅本地提交，不推送。

## 范围和状态

- 数据仅来自 `qa.annotation_workspace.seed` 自行生成的 112×80 DICOM；无患者图像、真实医生审核或 AI 执行。
- Vue、Cornerstone Core/DICOM Loader/Tools 5.11.0 在 `annotation_workspace/` 独立安装和构建；不更改旧共享 node_modules/dist。
- 所有标注为 `UNREVIEWED`、`training_gt_eligible=false`，不自动成为训练 GT、完整感染参考或临床有效性证据。
- 单病例、单切片、单当前可编辑多边形；已存其他标注可从列表选择。没有 Brush、3D、多 Series、协同权限委派或正式 PostgreSQL 迁移。
- 自动测试、API 冒烟和总控实际浏览器闭环均已通过（范围见下方实际验收记录）；证书提示已由用户处理。冲突后点击“重新载入”时的原生 discard confirm 自动化未完成，保留为未完成子项，不能用组件 stub 测试替代该项。
- 医院受众展示、真实病例标注、最终三次演练、备用录屏和医院冻结均不由本轮批准。

## 本地运行和登录

```bash
cd annotation_workspace
npm ci --ignore-scripts --registry=https://registry.npmjs.org --no-audit --no-fund
npm test
npm run build
cd ..
PYTHONPATH=.:frontend/.local/mvp-20261011-browser-deps PYTHONDONTWRITEBYTECODE=1 \
  /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python \
  -m qa.annotation_workspace --run .local/annotation-workspace-<new-id>
```

`--run` 必须是当前工作树 `.local/` 内的全新目录；不可用旧 DB 或重用已有目录。子进程在挂载 DB 前核验合成种子 manifest、生成器/配置/CT SHA 和 0600 私有文件。运行时不读取研究数据、不安装依赖、不启动 Worker。

本次入口为 `https://localhost:57171/annotations/`，地址以本次 `.local/annotation-workspace-20261017-01/ready.json` 为准。所有监听均在 127.0.0.1。新入口必须使用 `localhost`，旧入口使用 `127.0.0.1`；Cookie 不按端口隔离，不能把新地址改写成旧主机名。

同运行目录 `private-config.json`（0600）提供 `accounts.synthetic-doctor` 的账号密码；`synthetic-observer` 不是病例所有者，应被拒绝读写。不要把凭据粘贴进报告、提交或日志。Cookie 为原 Gateway 的 HttpOnly/Secure/SameSite 严格模式；修改请求需 Origin 和 CSRF。浏览器不持有后端 bearer。证书为本机自签证书，工具不代替用户绕过证书提示。

## 实际操作验收步骤

以下步骤是实际验收记录对应的操作清单。真实 CT、医院受众和录屏仍不在本轮范围；合成棋盘 fixture 的结果见下方记录。

1. 用 owner 登录，确认“棋盘测试影像（非真实CT）已加载”；核对病例 `GENERATED_ANNOTATION_CASE`、切片 `GENERATED_SLICE`、112×80。初始棋盘影像由代码生成，不是患者 CT。**已通过。**
2. 选择“多边形 / 编辑顶点”，在影像内逐点单击至少三个顶点，点击起点闭合。检查顶点数和未保存状态；保存新版本，检查 v1、服务端作者和 CREATE 记录。
3. 打开坐标详情，核对原生像素中心与 LPS；本夹具 [10,10] 对应 [5,46,56] mm。调整缩放/平移后编辑顶点，确认保存坐标不随视图变化。
4. 浏览器刷新，确认从数据库恢复相同轮廓、类别、备注、作者、版本及坐标。拖动顶点、保存 v2，历史 v1 保留。
5. 撤回标注，确认新版本为 WITHDRAWN，画面不显示有效轮廓，历史仍在；“恢复为新版本”追加 RESTORE，不删除历史。
6. 两个标签页读取相同版本后分别编辑，先保存一页；后一页保存应 409，保留草稿，不能覆盖先保存的版本。明确选择“重新载入已保存标注”才放弃草稿。
7. 保存时若出现网络错误或 10 秒超时，页面保留 operation_id，禁用重复保存。使用“查询该操作收据”先对账；刷新后仍保留待对账记录。404/查询失败不能自动重发。现有 UI 对长期未提交操作没有自动清除入口，应交管理员核对，不清存储伪造成功。
8. 退出并重新登录，检查持久化恢复；observer 登录应不能访问该病例。确认原 64-only 入口及其会话继续可用。**已通过。**

## 实际浏览器验收记录

总控在用户处理本机证书提示后完成了棋盘 fixture 的真实浏览器闭环，收据为 `AUDIT/ANNOTATION_BROWSER_ACCEPTANCE_V1.json`，SHA256 `9faaff5d93e888a195f3c9d3dd04061c94c5354898e278387e44d62aed0ce665`。范围是技术产品验证，不是临床验收：

- owner 登录、棋盘测试影像渲染、4 顶点闭合并保存 v1、刷新恢复轮廓/备注/作者/坐标：**PASS**。
- 拖动首点保存 v2、撤回 v3 后轮廓隐藏、恢复 v4：**PASS**。
- 两标签页从 v4 竞争保存：首 tab 保存 v5，次 tab 收到 409 且草稿保留：**PASS**。
- 缩放、平移、重置、owner 退出、observer 403、owner 重登并恢复 v5、原生像素/LPS 详情：**PASS**。
- 只读数据库核验：1 annotation head、5 revisions、5 events，事件为 `CREATE/UPDATE/WITHDRAW/RESTORE/UPDATE`；`inference_jobs=0`、`worker_nodes=0`；CT SHA 不变；最大 LPS 误差 0 mm：**PASS**。
- 冲突后点击“重新载入”时的原生 discard confirm 自动化未完成；未丢失已提交数据，第二个合成草稿 tab 在保留冲突证据后关闭；无草稿时正常 reload：**PASS**。该 confirm 子项保留 **NOT COMPLETED**，不能宣称整项冲突后 reload 通过。

证据图片 `annotation-final-synthetic.png` SHA256 `cbbb7fe42a74002042500e891e86b934d26366f544461e7c973c9123e85a054c`，`annotation-conflict-synthetic.png` SHA256 `dc4f695ca7906cbfde3c0d62311d7c5a23e0284a7c995d4a3c928de9f80254c9`。这些是合成棋盘界面证据，不是真实 CT。

当前工程结论是 **PASS_SYNTHETIC_CHECKERBOARD_ONLY**。真实 CT 接入、患者级影像空间验证、真实模型结果、临床资格、医院展示、三次最终演练、备用录屏和医院版本冻结均为 **NOT RUN / NOT APPROVED**；合成结果不能替代这些证据。

真实医学目视、三次最终演练、录屏与回放应在分别批准后，由负责人指定操作者，在同一已批准数据/模型/构建配置上执行。每次从登录、原始 CT/热图检查、版本切换、刷新恢复、失败状态到回退完整记录；任一阻断故障则保留失败、停止最终冻结。三次记录和录屏实际文件/SHA 未齐全前保留 `NOT RUN`，不把本轮合成操作计入。

## 数据与 API 契约

所有新路由位于 `/api/v2/cases/{case_id}`；原 API、Worker、FrozenRunner、研究任务协议不改。

| 路由 | 行为 |
| --- | --- |
| GET `/annotation-context` | owner、READY、未过期、已注册切片的权威绑定和几何 |
| GET `/dicom` | TEST_STORAGE CT，返回前校验字节 SHA |
| GET `/annotations` | 每标注最新修订，含已撤回记录 |
| POST `/annotations` | 服务端认证作者、身份/几何/多边形验证、CAS 版本、原子修订+事件 |
| GET `/annotations/{id}/history` | 原始修订及审计事件，按版本排序 |
| GET `/annotation-operations/{operation_id}` | 已提交操作收据；未知事务先查询，无自动重试 |

POST 包含 `annotation_id`、`operation_id`、`expected_version`、`binding`、`vertices`、`category`、`state`、`note`。binding 精确包含 Case、slice、Study/Series/SOP/FrameOfReference UID、CT SHA、geometry SHA 和 `DICOM_NATIVE_CENTRES_LPS_V1` 版本。作者和世界坐标禁止客户端伪造。

坐标是原生像素**中心** `[x,y]`，允许区间 `[0,width-1]×[0,height-1]`。世界坐标由服务端计算：`IPP + x*PixelSpacing[1]*IOP[0:3] + y*PixelSpacing[0]*IOP[3:6]`。查看器在允许绘制前独立核对 CT SHA、原始尺寸和三个角点的 Cornerstone indexToWorld；不使用 CSS、canvas 或缩放后的坐标作为保存坐标。

Polygon 至少 3、最多 256 个有限顶点；服务端拒绝越界、重复、自交和小于 0.5 像素平方的退化轮廓。POST 实际流式读取上限 128 KiB，不接受缺 Content-Length、chunked、伪造长度。单病例最多 20 个标注，每标注最多 32 个修订，SQLite 原子触发器防止并发绕过；撤回不释放不可变历史额度。

修订以 UUID/version 唯一，operation_id 全局唯一。同作者、同请求 replay 返回原收据；不同请求重用 operation_id 返回 409。`expected_version` CAS 仅允许一个并发写者成功。修订包含作者、时间、上次修订 SHA、当前 SHA；数据库触发器拒绝修改/删除 plane/revision/event。此哈希链是技术可追溯机制，不是外部可信签章。

## 验证与限制

2026-10-17 实际：24 后端测试通过（3.01s），10 前端测试通过（0.598s），vue-tsc/Vite 构建通过。后端覆盖 auth/403、绑定错误、非法多边形、并发 CAS、并发额度、不可变历史、持久化、操作对账、CT 篡改、真实流长度和 Gateway CSRF/主机 Cookie 隔离；前端覆盖坐标、409 保留草稿、响应丢失、刷新对账、POST 成功后 GET 失败和超时解除 busy。前端组件测试 stub 了 Cornerstone 绘制组件，不能证明鼠标工具行为。

已知警告：Starlette TestClient anyio 别名弃用；Cornerstone 压缩解码器引用 fs/path/url 被 Vite 外置，且工具 chunk 大于 500 KiB。本轮生成影像为未压缩 Explicit VR Little Endian，未验收压缩编码、触控、低内存或跨浏览器兼容。输入、用户 token 在 8 小时后过期；恢复长期服务应另建受控运行，不擅改过期策略或替换旧服务。

API 冒烟：静态页 200、未认证 401、owner 登录 200、CT/绑定 SHA 匹配、无 CSRF 403、Job 入口 404；图形验收前新 DB 为 0 Job、0 Worker、0 annotation revision。首轮冒烟统计误查 `workers` 表，随后改查实际 `worker_nodes`；该错误没有产生标注写入，记录保留。

## 回退与保全

旧 `https://127.0.0.1:57592/mvp/` 一直保留。回退时切回该地址，不迁移/重绑旧候选、不覆盖原 DB/资产。当前旧候选 197 源码、23 runtime 引用、21 dist 文件与冻结绑定匹配，原 DB SHA 未变。

新父进程身份在运行目录 `parent.json`，子 PID 在 `ready.json`。本次为父 72850、子 72853/72854/72855；停止前核对 PID、启动时间、命令行和父子归属，只向匹配的新父进程发送 SIGTERM，其 finally 回收自有子进程。不要终止旧父 63601 或未知进程。新 DB、DICOM、配置、日志、待对账/历史和 exit.json 保留在私有运行目录；不提交这些文件。新旧服务当前均按总控要求保持运行。


## 2026-10-17 文案修正与图形验收进度

界面标题下、病例信息、查看器无障碍名称、加载中及就绪提示明确写“棋盘测试影像（非真实CT）”，避免将生成棋盘误认为患者 CT 或影像降质。只更新文案和静态构建；DICOM 技术合同、SYNTHETIC_ONLY scope、服务数据库、凭据和影像身份不变，未生成假解剖影像或接入真实医学资产。

总控在本轮委派中报告：实际鼠标绘制并保存 v1、刷新恢复、拖动编辑 v2、撤回 v3/恢复 v4、双标签页 v4→先保存 v5 后另一页 409 保留草稿、缩放/平移/重置、owner 退出/observer 403/owner 重登恢复 v5 均通过。冲突后原生 discard confirm 自动化未完成，已单独标为 NOT COMPLETED；本次文案修改不重复写标注或重做操作。
