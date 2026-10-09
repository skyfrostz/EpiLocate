# S0：总控专用 writer 与执行锁

本轮仅交工具；INTEGRATION不创建生产policy、不调用生产writer、不改总控state。起点 `8baec8b9260586bd6412a0656b559cbcea182a50`。使用方为现有总控，权限范围保持原状。

## 总控调用

固定 `epi_next/__init__.py`、`coordinator_writer.py`、`artifacts.py` 的提交及文件SHA到私有源码快照；用快照的父目录作为PYTHONPATH。不要动态导入仍在编辑的工作树。

policy由总控自行创建并保存SHA，不入Git。结构示例（示例不是生产授权）：

```json
{
  "writer_id": "CHIEF",
  "uid": 501,
  "state_path": "/absolute/approved/state.json",
  "allowed_pointers": ["/research_v2_wave1_lock"]
}
```

`uid`取总控实际OS UID；`state_path`必须明确匹配。pointer采用JSON Pointer。现有对象内叶子可替换，顶层非授权元数据可新增；中间父对象必须存在。patch示例：

```json
{
  "/research_v2_wave1_lock": {
    "path": "/absolute/immutable/research_v2_wave1_lock.json",
    "sha256": "SHA_OF_APPROVED_LOCK"
  }
}
```

总控在确认当前state及不可变授权证据后，使用实际SHA替换占位符再调用：

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/absolute/pinned-source \
  /absolute/approved/python -m epi_next.coordinator_writer update \
  --state /absolute/approved/state.json \
  --policy /absolute/private/writer-policy.json --policy-sha POLICY_SHA \
  --expected-revision 11 --expected-sha CURRENT_STATE_SHA \
  --writer-id CHIEF --task-key research-v2-wave1-publish \
  --reason 'publish existing immutable wave1 lock reference; permissions unchanged' \
  --patch /absolute/private/patch.json
```

revision 11是本轮开始时只读观察值，不能作为之后调用的硬编码事实。成功返回新revision/SHA/snapshot；所有陈旧/重复/权限或不明事务错误为非零退出。更新不会初始化state或读取旧快照自动恢复。事件及快照放在 `state.json.writer/`；临时state文件与目标在同一目录。PREPARED → 保存旧/新不可覆盖快照 → fsync临时文件 → replace及目录fsync → COMMITTED，全程同一flock临界区。

未知结果先执行（只读取state/事件，但会建立audit锁文件）：

```sh
PYTHONPATH=/absolute/pinned-source /absolute/approved/python \
  -m epi_next.coordinator_writer reconcile --state /absolute/approved/state.json
```

`APPLIED_PENDING_EVENT`、`NOT_APPLIED_RECONCILE_REQUIRED`、`EXTERNAL_STATE_CHANGE`均要求总控对账。工具不自动终结PREPARED、不重新提交、不回退revision。中断遗留临时文件和证据保留。需要未来恢复写入时应另交明确的对账决议/受测恢复路径，不能删journal绕过本门禁。

## 权限与完整性边界

锁内CAS比较当前原始字节SHA与整数revision；revision仅递增。task_key在该journal中唯一。policy SHA、writer_id、UID及目标路径核验；既有授权roots、data/budgets/resources、owner等字段不可改，嵌套新增/变更 permission/authorization/allowlist/approval/budget/grant 字段亦拒绝。仅总控的白名单非授权pointer可改。工具不会由算法PASS或数据存在推导展示、训练或数据许可。

这是同机合作式入口，不是跨会话安全认证。同一OS用户仍可直接写state、policy、journal或快照并绕过工具；哈希链亦不是外部签名。已开始采用journal后，直接覆盖导致下一次工具调用拒绝并报EXTERNAL_STATE_CHANGE；不能阻止已经发生的绕过写入。既有旧快照不会自动迁入journal。首次采用依赖总控精确选择当前合法state并固定expected SHA。

## 依赖与设备最小接缝

`epi_next.execution_lock.dependency_snapshot` 固定各实际模块/配置的repo、完整commit、文件字节SHA和声明的包版本，dirty文件必须显式锁字节；复制到不可覆盖收据目录。`verify_dependencies`拒绝snapshot、live源文件及package版本漂移。`load_locked_module`从已校验snapshot字节编译，不从另一个工作树直接加载。仅覆盖调用方声明的文件/依赖；调用方必须列齐实际加载模块及配置，未安装全局import拦截器。

`tracked_device_slot`复用现有CPU/MPS flock和ENCODER-only MPS限制，绑定job_id/task_key、PID/启动时间、资源上限与dependency SHA。持有slot后必须交SHA固定的同job终态收据；已注册Popen子进程未退出拒绝complete。没有终态的旧slot即使锁已释放或PID已消失也保持UNKNOWN，后续新slot拒绝，绝不按陈旧PID杀进程。未注册子进程和调用方真实性仍为合作式约束；旧入口未迁移，不声称所有现有运行器已采用新slot。预算为绑定记录，实际forward/backward及内存守卫仍由既有运行器执行。

## 根因排查及接续缺口

只读检查本工作树脚本/测试/ignored代码、主项目scripts/tests/.agents及当前相关进程；未定位两次旧rev4回退写源，根因UNKNOWN。总控明确提供的三个已结束脚本仅只读核查：freeze脚本只生成freeze文件，报告脚本只写报告；update_state_v9有锁外旧字节断言、临时写和replace，缺少同锁CAS，但无证据证明它造成此前事故。没有执行这些脚本或终止进程。

医院MVP仍需实际在线基础链路和有条件的端到端验收；已有三次资产读取不替代模型复验。新工具不解除LIVE_CASE运行器接入门禁、不扩大真实影像展示许可、不重算既有E1/E2/CTFM。医院默认null、最终展示审批与三次医院流程NOT RUN。10月14日冻结演示快照，科研继续。
