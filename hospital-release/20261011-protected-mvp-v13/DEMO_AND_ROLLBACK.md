# 演示与回退操作

本包当前NOT READY，不能执行真实MVP或当作医院冻结版本。批准的CPU96批开发scope与医院展示批准分别记录；真实执行须等数据、工程证据和总控dispatch。

资源窗口允许时，先执行受保护入口的独立生成测试，固定fresh目录；这是生成CT/FakeDelegate，医学调用0，不写真实设备队列：

```sh
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:frontend/.local/mvp-20261011-browser-deps /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python qa/hospital_mvp_protected.py --generated --run frontend/.local/mvp-protected-generated-20261011-attempt1 --dist frontend/.local/mvp-20261011-dist
```

失败目录与partial保留；不重用attempt目录。实际生成测试尚NOT RUN，不在P1占用期间执行。

正式ready必须消费DATA通过总控交来的原3 SOP派生ledger及逐图人工像素复核记录。数据SHA/像素/原生几何/版本核对通过后，绑定当前受保护生成browser-acceptance.json、owned-completion.json及源码closure。`qa/hospital_mvp_binding.py`只生成metadata fragment，status固定NOT READY，不能当dispatch。

chief发布`EPI_NEXT_MVP_LOCAL_DISPATCH_V1`，精确绑定ready/Data/owner/decision/source SHA、Python/cwd、新job_id及所有路径。为避免JSON自身SHA循环，`argv_without_dispatch_sha`保存完整命令去掉最后`--dispatch-sha <发布后SHA>`两项；发布后SHA必须由调用方作为最后两参数传入。首席算法工程师核验P1收据及恢复后唯一串行dispatch，INTEGRATION不自行制造dispatch或启动真实命令。

真实执行完成后，首先检查supervisor-receipt、runner-complete、owned-completion、各case-result及前向admitted/completed日志，再核对SQLite保存对象、三个Occlusion jobs/三个Result和资产SHA。未知提交先对账；任何UNKNOWN/BLOCKED/FAILED保留原始目录及槽，不自动再运行。无可靠响应不能解释成正常CT或造热图。

医院验收操作沿用[v1真实演示流程](../20261009-integration-v1/DEMO_AND_ROLLBACK.md)，核验原CT方向/顺序/世界坐标、crop/resize/resample六项实际检查。原生单切片MVP不能替代全Series或新算法空间验收。未验证结果移出医院候选。

旧版应用默认继续原FrozenBaseline，16/32/64按钮保留；研究算法选择和回退使用[v1算法对照入口](../20261009-integration-v1/README.md)，仅生成新的不可覆盖flag。flag接缝没有自动安装为生产endpoint。新算法未验收时拒绝医院选择；只可回退到已验收旧版或负责人批准的真实预计算资产。无合格备份则NO-GO。

10月13–14日按同一实际版本连续完成三次真实流程；保存所有失败和成功尝试。真实预计算/备用录屏须各有资产SHA和实际播放检查。10月14日总控汇总本地交付包、提交SHA、日志、验收摘要和缺口，由钟佳桦最终批准；不自动发送影像、上传云盘或部署医院服务。
