# Revision86 C｜64-only 技术核验准备对账

原 INTEGRATION 工作树，分支 `codex/epi-next-integration-20261009`，核对起点 HEAD `246cdd1884a59bf9c0dcb1f872a26802378488de`。只消费实际文件与现有证据；不改总控状态或合并表，不重复已有生成测试。

权威状态 revision86 SHA `c24ca4f03d11084cfdbafbc1542f06bb1ef4dc884417a17618f1a47e47635782` 匹配。原请求 `.local/demo64-technical-request-v2.json` SHA `7398099e6ceffb2067e5e5566668c0957023e872d02c3615b6da5a651aa001cf` 匹配，继续复用，不创建第二份请求。候选 `.local/demo64-candidate-20261013/frozen-candidate-v1.json` SHA `191b47b46ac2710e1a1d2d08b6b7b5e67c5c137c22d0d9cb105fb7f76911d917` 不变；190 source、21 dist、23 runtime 引用经既有 `checked()` 实际核对通过，4项新 driver 和6项浏览器 runtime 逐项 MATCH。旧三 SOP/三 Result/九个64资产的 projection SHA `b0dcd6e69cb057e8be3b92ac6a052b8d3415442ee4042f6771efbf1b3c5b934a` 不变，不是新 allowlist。

新驱动绑定既有原生 decode/render 流程：当前 image/viewport、decoded尺寸、IMAGE_RENDERED/rendered状态、可见非零canvas、当前64资产实际draw与无错误共同构成 readiness；提示文字不作准入。每步原子保存，primary/cleanup失败独立记录。原11项生成验证复用 `246cdd1` 与总控已绑定工程索引；生成browser regression SHA `5beaf20750b1302f47d4959508a5f7f5ce328b3863dbce48c171cb61a87110b7` 仍 MATCH，不重测未变源码。

本轮实际执行仅 check-only：

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:frontend/.local/mvp-20261011-browser-deps \
 /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python qa/demo64_technical_v2.py \
 --request /Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration/.local/demo64-technical-request-v2.json \
 --request-sha 7398099e6ceffb2067e5e5566668c0957023e872d02c3615b6da5a651aa001cf
```

exit0：`CHECK_ONLY`、services_started=0、medical_arrays_read=0。无真实恢复、浏览器启动、影像/权重/模型/Worker/Job/slot、截图、录屏或外传；预定新输出 `.local/demo64-technical-20261013-02` 不存在。

## 授权与历史

revision86 将本项记作 `GENERATED_REGRESSION_PASS_REAL_CHECK_PENDING`，现有合并待决表明确下一次确认尚待 owner；请求仍 `PROPOSED_NOT_APPROVED`。未取得绑定此新驱动/请求的独立明确确认，不能把工作委派或旧单次批准当作第二次执行许可。原消息 `01a134e5-e172-76b3-83e4-7dc09f0bc7a6` 的一次性技术核验已结束/消费。

原 receipt `.local/demo64-technical-20261013-01/acceptance.json` SHA `884e5a8a971c34e70c2f5624c9c04a7d5dbd47968a41cd22eff2b7bbc58e7c89` 保留：`FAILED_OR_PARTIAL`，持久化services/login PASS，flows=[]。其后的三例/九层/刷新/真实直接API拒绝/实际独立空间核验未完成；hint hidden 根因 UNKNOWN。浏览器关闭、三自有服务退出、source_db_unchanged=true 为原收据证据；不额外重读源DB或患者资产。工程限制已有生成证据，不能据此填写真实 PASS。

| 项目 | 本轮状态 |
| --- | --- |
| 绑定与工程 readiness | DONE；静态 MATCH/check-only PASS，复用生成验证 |
| 新真实技术尝试 | BLOCKED_BY_NEW_CONFIRMATION / NOT_RUN |
| 后端真实直接访问限制、三Result刷新 | NOT_COMPLETED；生成拒绝证据保留 |
| 真实64独立空间映射 | NOT_RUN；原DICOM位置/IOP/spacing + 独立相机投影固定点，0.5 CSS px容差未改变 |
| 人工叠加/解剖目视 | NOT_RUN；见独立操作员清单 |
| 医院展示、最后三次演练、录屏/播放、最终冻结 | NOT_APPROVED / NOT_RUN；本次技术请求均不包含 |

## 下一次准确确认句

以下仅为原请求确认文本，不构成批准或新审批对象：

> 我批准64-only技术请求SHA `7398099e6ceffb2067e5e5566668c0957023e872d02c3615b6da5a651aa001cf`，仅按此请求绑定的原64-only候选及新验收驱动，允许一次原三SOP本机只读技术核验；不计最终演练，不包含医院受众展示、截图、录屏、外传或模型/Worker/Job。

收到直接负责人确认后沿原驱动消费新确认的path/SHA和新私有输出；overall180秒/browse140秒、retry0。失败停止并保存primary/cleanup证据，不重新提交。原v16与旧DB/对象/dist不动；仅终止此启动收据绑定的自有服务，禁止杀未知进程。普通网络允许、无独立GPU AI Node，不扩展场地/医院名称审批。
