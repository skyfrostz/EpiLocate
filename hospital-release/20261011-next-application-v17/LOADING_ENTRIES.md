# 真实加载入口与明确依赖

本轮只开发和生成验收，未执行以下医学调用。现有RICORD DATA v3、固定三切片Prepared2DInput和原2D权重的授权SHA已交付，不等待DATA重交；医院展示授权也不是本轮纯开发的前置。

| 入口 | 具体加载/绑定 | 监督与计算 |
| --- | --- | --- |
| E2-Q首个应用执行 | `epilocate_next.e2_launch.run_existing_e2_job(config,binding,guard,output_root)` → build_existing_e2_runner → LOC first_real_e1_e2.consume_inputs → baseline_source.load_verified_resnet18 → DifferentiablePreparedModel → E2HandlerAdapter → run_prepared_e2 → 原Worker提交/保存 | caller先在既有supervisor准入并建立ChildGuard；begin_case/check/before_forward/before_backward/end_case；单计数，不额外预测/预热；每Job/request严格绑定，reuse只消费LOC验证stage1，不重复P1 |
| 独立selected fidelity 5F | `epilocate_next.e2_launch.run_existing_selected_fidelity(binding,guard,output_root)`复用同一加载器，再调用LOC selected_fidelity；仅原图、全Mask keep、peak keep、全Mask remove、peak remove五对象 | exact F5/B0/update0、case3、120秒上限、reuse canonical SHA、独立新scope；不进入优化，不加入E2-Q预算，输出selected-fidelity.json；已有输出拒绝重跑 |
| E2-Q结果应用回放 | E2PrecomputedAdapter+ReplayBinding读取完整科学结果，校验原源/模型/配置/core/preprocess/几何SHA | 新增F0/B0/update0；source PRECOMPUTED，原医学或SYNTHETIC类型保留；避免科研E2-Q结束后再为应用重复计算 |

ExistingE2Binding是应用单Job参数，不是第二份DATA allowlist。必须由总控填写完整ApplicationRequest及Job ID、prepared_delivery/preparation_config/scientific_request/loc_dependency_lock路径+SHA、原case_index、geometry/mapping QA、已验证stage1 reuse路径+SHA和bridge路径。接口默认不执行；从既有监督子进程调用上述函数，caller负责总预算/退出/ChildGuard.complete，函数不创建队列/锁/权限文档。Worker仍使用原认证/HTTPS接口；只有显式绑定的应用Worker领取ALGORITHM。单Job加载函数可调用，但E2-Q没有三例共享F/B/update/总时间的完整启动封装，工程状态ENGINEERING_NOT_READY。独立5F已发布固定执行binding及CLI，见下文。

已消费LOC正式source9ae67d74ca695bac12bf3f2e2f0007438f72c79f，handler SHA062eff4e476280f0f415380d4a0c2bf1e5a2598a31869c7374ba39dd34ff168b，dependency-lock SHA100ea6936572c610ef989fa53d025b09694395b8864b3199ba5a982fb3d767bc。E2-Q科学请求SHAa37d9b5585afb548753c64d6aee6ed41e7136a325b29db1dabe1b6d3f24f2b46，selected-fidelity请求SHAab7b2df246a7b9c9c46dddce9b10304686158884fcb33bad06b25000a14f6f1c。它们不是执行批准。

生成验证分开记录：跨线真实core只用生成函数，6/4/4合成计算；新加载器/5F入口用显式注入double，读取的仅生成metadata，5次逻辑guard回调，不算5次医学前向。原权重和准备数组均未打开。trace/stage/checkpoint/native原值以有界gzip保全，不改变算法数值；PNG为显示派生物。

目前E2-Q完整真实启动ENGINEERING_NOT_READY，具体缺口：三例共享全局130013F/130000B/130000update/7200秒的启动封装，以及总控新scope/dispatch；原已交付DATA不能替代新的执行批准；E2-Q应用模式还需同一科学scope中的新应用Job/Worker/model注册和精确输入绑定。优先PRECOMPUTED路径缺完整E2-Q结果路径/SHA，因为该新科学执行未运行。CTFM缺新训练head、完整volume resolver、ENC真实handler产物与对应批准；这不是INT既有加载器代码未写。医院冻结还独立缺approved demo allowlist、真实空间复核、医院配置三流程和备份录屏。

## 独立5F固定绑定（未派发）

`SELECTED_FIDELITY_BINDING_INDEX.json`给出私有binding路径/SHA、唯一task-key、Job ID、未创建的唯一输出目录和实际metadata argv。不可变科学/执行binding不包含批准文件引用。总控批准后另行提供外置dispatch及SHA；dispatch单向绑定binding SHA、18个源码SHA（包含CLI）、owner receipt和新准入决议。这样没有完整文件哈希自引用，不伪造收据。

CLI为`qa/next_selected_fidelity.py --binding <固定路径> --binding-sha <固定SHA> --dispatch <总控发布路径> --dispatch-sha <实际SHA> --execute`。Python/PYTHONPATH及既有ChildGuard环境见index；必须作为既有监督器获准子进程启动，仍由原execution_lock验证行政恢复/新scope。当前外置dispatch尚无，不可执行；默认metadata模式只打印scope，0医学调用/0队列观察。总控填入收据时无需改变binding或源码SHA。已有输出拒绝，先对账。

定向生成验证6 PASS/0.02s：完整单向链通过、binding/dispatch/source/owner四种篡改拒绝、无dispatch及已有输出拒绝。生成收据不具有实际批准效力。当前5F工程绑定已具体化，实际状态NOT RUN / WAITING_NEW_OWNER_ADMISSION_DISPATCH；这不表示E2-Q三例封装也已就绪。
