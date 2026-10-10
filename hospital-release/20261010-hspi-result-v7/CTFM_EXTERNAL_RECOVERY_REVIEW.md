# CTFM UNKNOWN槽：只读外部恢复审查方案

本文件不解锁、不写finished、不补旧child末样本、不启动GPU probe或新模型，不改Wave1失败状态或配额。恢复审查和新实验执行是两项独立批准。

## 当前已核对事实（2026-10-10 Asia/Shanghai）

- 权威state revision19，SHA `ac2dacaad2c9294cbd89f85e2c865cfaf1eed1331ecf9d56d80744d0082bc631`，记CTFM UNKNOWN_RECOVERY_RETAINED。
- 槽 `~/.codex/epi-next-device-queue/slots/ctfm-fov128-wave1-20261009-01` 的started SHA `e234b341273e88f4c723eb3d542d5c74a24b58e09fe3bb69bb5ac93557f94d70`，ENCODER owner、task_key CTFM-FULL-APPROVED-SERIES-FOV128-V2。记录的监督父PID66331/start Oct10 09:09:17，子PID/PGID/SID66338同启动时间。原device槽标mps不证明已进入MPS计算。
- 原监督收据路径 `/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-encoder/.local/ctfm-volume-wave1/supervisor/ctfm-fov128-wave1-20261009-01/supervisor-receipt.json`，SHA `20e2348ac436c0b1cccf5ee9d3d31dbd431744c750fb930edadc24c51abfa2c2`。BLOCKED/SWAP_GROWTH_PRESTOP；自有组KILL后exit=277222.561081、恢复null、slot_completed=false。CPU entered1/returned0，MPS0根据上游收口，不解释为MPS128失败。
- 原telemetry最后样本pid66338、mono277222.207147791、driver458752/tensor0、device_recovered=false；无runner-complete。该值是旧child非恢复末样本，不能充当同步/empty_cache完成证明。
- 本次ps逐PID只读查询66331/66338均exit1、无记录；相关命令/组列表未见原任务。只确认本次观察无这些PID，不推断其过去或同PID未来身份。
- 原slot没有finished.json。本次只在总控coordinator已有恢复命名入口、ENCODER本任务目录及其reports查找后续恢复收据，未发现；不全盘扫描其他用户/受保护资产。没有可接受后续证据就继续UNKNOWN，不把“没找到”说成不存在于任何位置。

## 可支持的外部恢复证据（须先单独批准采集范围）

1. 固定本次事故、started/监督/最后telemetry/counters/command/spec字节SHA和state引用；ENCODER确认原父子身份、PGID/SID、完整自有进程树及entered/returned/MPS计数，保留旧证据。
2. 只读OS身份观察：当前时间/boot-session或uptime、完整命令/start/UID/PPID/PGID/SID，对原自有任务及已注册后代进行核对。证明该任务当前无活成员；若PID复用以start/命令识别，不杀复用或身份不明进程。
3. 新的外部系统压力证据独立命名，来源memory_pressure -Q/sysctl vm.swapusage；用负责人批准的持续窗口与采样规则记录原值、缺测和间隔，明确swap基线/稳定或释放规则。不能因一次free恢复或swap页长期保留自行改旧阈值。
4. 若ENCODER已有合法的实际旧child同步/释放/最终driver+tensor证据，绑定PID/start/job与SHA后可纳入；本次已知并没有。外部管理级GPU进程/资源遥测或OS重新启动记录只能证明新的外部环境观察，不能冒充旧child恢复标记。无checkpoint/无新MPS初始化probe优先；如果要新GPU probe必须另批，本轮不执行。
5. 恢复结论由总控汇集ENCODER与负责人明确决定：外部证据是否足以解除调度阻断、还是继续UNKNOWN/按获准系统维护后复核。必须注明EXTERNAL_ADMINISTRATIVE_RECOVERY、观察局限和审核人，旧slot/收据继续UNKNOWN历史身份不覆盖。MPS旧末样本缺失事实永久保留。

## 总控应请求的独立批准项

- 批准仅此job的只读外部进程/系统压力/可用OS GPU管理遥测观察，以及精确采样窗口和判据；不扩到患者/标签/模型调用。
- 批准负责人/ENCODER确认的外部恢复判据：尤其没有旧child最终释放证据时是否允许管理性解除。不能默认“当前无进程=GPU已恢复”。必要系统维护/重启或任何新GPU probe另外明确批准，不由此提案自动执行。
- 批准一次独立、SHA绑定的恢复决议，以及未来最小受测的全局UNKNOWN闸门消费方式。现有v2 supervisor严格要求finished，未实现外部恢复决议消费；不能直接伪造finished、删slot、换queue或换job绕过。只有批准后另任务实现/fixture验证此恢复接缝，仍不改变旧证据。
- 新真实实验精确配置/成本另行审批，Wave1配额不恢复、不借恢复审批自动retry。

本轮结论：可提出上述外部审查，暂无后续合法恢复证据，槽仍UNKNOWN。S0旧状态回退根因亦不因本审查改变。10月14日MVP可保持既有合成/许可范围接缝，不依赖解锁或E2阳性。


## 精确待批准审阅配置（不执行）

仅原job ctfm-fov128-wave1-20261009-01及其已注册自有父子/后代：读取旧PID/start/UID/PPID/PGID/SID并比对当前ps，身份不明保持UNKNOWN，不发送信号。系统观察来源限memory_pressure -Q（System-wide memory free percentage原值）和sysctl vm.swapusage。建议从单调时间t0至t0+60秒，目标每1秒采一次，共61个含端点样本；保存目标/实际时间、间隔、命令退出码、原始值及解析值。允许间隔/端点偏差需批准时明确，未锁定或缺测不视为通过。

审阅必要条件：startup及每个样本free>=20%；每个样本swap_used(t)-swap_used(t0)<1GiB（严格小于）；每个样本命令成功且解析有效，无缺测；当前无原自有任务活成员，开始/结束各做一次身份核对。swap基线是新观察t0，不冒充旧计算启动基线，不抹掉旧SWAP_GROWTH_PRESTOP。即便61样本全满足，仍只是管理性恢复的必要非充分证据，不能证明旧child曾执行synchronize/empty_cache或GPU上下文完整释放。

总控将此精确观察配置单列待批准：采样范围/时间与允许偏差、必要非充分判据、管理性决议审核人；另批未来受测闸门消费机制（不伪造finished）。本轮不运行60秒采样、不修改槽/状态；新MPS probe、reboot、真实模型调用均排除。无新旧配额恢复。
