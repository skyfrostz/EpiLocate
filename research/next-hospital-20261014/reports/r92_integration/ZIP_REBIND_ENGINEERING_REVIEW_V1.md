# 原ZIP身份重绑定｜INT独立只读工程评审 V1

日期2026-10-15。INT基线1085db4de11f622398aaf63f5e8fe3a5db4ff700，原分支/工作树复用；DATA观测HEAD6c63685568a77da31febbf7d48b4d032d764da8e及原dirty保留，不写DATA。本评审只读源码，不stat/open/hash约11GB归档，不读标签/CT/权重，不执行源码、网络、模型、服务或医学页面。以下按时间保留早期快照；当前结论见文末“最终固定版本收口”。早期待修项不能单独当作最终版本结论。

## 当前源码事实

- `r92_label_read_entry.py:188–192`：先discover/HTTP并保存A结果，随后才读取原batch并调用open_bound_archive；`run_discovery`检查也在discover之后。归档身份异常不能撤回已发生的HTTP；旧结果需按实际阶段保留，不能改写为“整次零访问”。
- `a1_prepare.py:242–247`：lstat比较device/inode/mtime/size并校验小型provenance，返回Path而非稳定fd。
- `a1_prepare.py:77–87`：每个Member再按路径open(O_NOFOLLOW)，fstat校验同四元组。现有严格失败合理，**不能直接删除device比较或只更新device字段**。O_NOFOLLOW只保证末级组件，不能自动排除父目录symlink/替换；稳定fd也不阻止文件原地修改。
- `a0_acquire.py:210–218`：A0完整性收据记录完整bytes/MD5/SHA256；本评审没有读取该收据/归档，因此当前内容是否一致仍UNKNOWN，设备变化原因也UNKNOWN。

审查源SHA：r92_label_read_entry.py `641dbf9b61f609326d6a8d0ea3edfce676a3a1bca249d8e03cf682b02c22a8b7`；a1_prepare.py `b8382eda8f6d2e9e25a93873710a899358738db12812bff0e3ded2de60bda4d0`；a0_acquire.py `ff40674dbc6d8234ad0218416db17c9d8ef1c504f609dc2ed02a77656f7def5d`。行号仅对应这些字节。

## 最小安全重绑定要求

1. **内容证据必须锚定原A0。** DATA的新独立验证器在明确授权与有界预算内只读完整opaque ZIP，流式读到预定EOF，精确bytes及完整SHA256对照SHA固定的原A0完整性收据/原请求。路径、size、mtime、inode、抽样、中央目录、CRC、HTTP ETag都不能替代完整SHA。新算出来的digest不能自行成为新的“预期值”；只记录真实读取bytes、耗时、停止/错误和终态，不解压成员、不解析标签/CT。
2. **固定打开对象与路径。** 对批准的绝对路径拒绝symlink，使用只读/no-follow fd，普通文件检查；hash前后均fstat，至少保存dev/ino/size/mtime_ns/ctime_ns，并比较最终路径lstat与fd，拒绝路径换指、truncate、append或原地改写。要声明抗父目录竞态，则用dirfd逐级no-follow锚定父目录；resolve后再按原路径open不提供这项保证。成员消费应复用已验证的对象；若并发/dup共享offset，须用pread或独立offset管理，不能让读取对象回退成任意路径重开。
3. **明确跨进程证据寿命。** 一次完整hash证明的是该读取窗口，不证明日后重开的文件永远不变。新任务启动时仍需检查批准绑定、稳定fd与路径/metadata连续性；若验证器已退出、文件可写且不能证明连续性，就保持BLOCKED，或在新的精确批准预算内把重新核验与消费串联于同一对象。不能暗增第二次11GB扫描，也不能把旧fd编号写进JSON冒充存活fd。只读fd/共享advisory lock不是不可变快照，对原地写入仍须检测并保留限制。
4. **证据不自授权。** 单独identity-verification receipt只报告原A0内容是否MATCH及旧/新stat差异，必须显式不授予label/header/model/网络或A重试权限。设备变化原因不明时只写UNKNOWN。MATCH后仍由总控集中形成A重试/B—D恢复的新精确请求/确认与新准入，不因验证成功自行继续后续阶段。
5. **副作用前门禁与阶段隔离。** 新独立入口先核请求/源码/runtime/预算、scope/run_discovery标志、引用、归档身份及有效dispatch，再进行获准HTTP/成员读取。物理内容hash单独计预算，不藏入旧小IO额度。旧FAILED_STOP_NO_RETRY/原HTTP结果/计数/输出/slot原字节保全；新的有界重试须新授权身份、输出和slot，明确追溯旧失败，不能复用已消费slot或制造新task逃避额度。未知事务先对账，不自动重试。
6. **保持原科学边界。** 旧共享文件、R18/Ridge冻结及旧MVP不改。只验证opaque ZIP身份不构成标签许可/语义匹配、医学空间PASS、pixel access或模型额度。执行前重新核新源码闭包/生成测试/实际runtime、fresh path+SHA绑定、输出未消费、原队列独占release与资源停止门槛。

## DATA新实现收到后的必要生成检查

仅使用小型生成文件/伪网络，不使用真实归档或标签：完整SHA不符即拒绝；仅device变更且内容相同的重绑定证据；同size/mtime假相等但内容不同；末级/父目录symlink与lstat→open替换；hash中truncate/append/原地改写及hash后路径替换；fd/路径不一致；到EOF/bytes计费与时间/RSS停止；缺新确认/MATCH receipt不能自授权；身份门禁失败时HTTP/成员读取均0；旧失败/输出不覆盖、重试slot独立、unknown不重复提交。证明仅覆盖生成场景，真实归档完整SHA由DATA单独执行，INT不重复读取。

结论：**当前旧入口保持严格拒绝；新独立入口和生成回归按上述门禁审查。当前内容身份UNKNOWN，新实现待审，A/B—D均未由本评审批准或重跑。**


## DATA新模块开发快照补评（非最终版本）

只读快照 `archive_identity_v2.py` SHA `c63c8ef5217ea31e0235aab9aedeb4c7912d0e456eaf4797d13d72d3af9f8a32`（122行），测试源SHA `75128cf04eef20b892804b4bfbce9b0107d1030d2423958a3cf1aec18dcbf4a4`。已具备逐级dirfd/no-follow、普通文件检查、ctime/mode/nlink状态、流式SHA/EOF与扫描前后fd/namespace比较；这些比仅修改device正确。未运行其scan()或真实入口，DATA开发中变化须按最终SHA重新评审。

- **P1待最终入口闭合：独立A0锚点。** `reuse:106–114`仅比较receipt自身sha与expected_sha相等、bytes与expected_bytes相等，无原A0 expected SHA/bytes独立实参。生成不扫描探针构造自洽dummy receipt（SHA全0、与生成字节实际digest不同）仍被reuse接收，证明helper单独不保证A0身份。最终入口须先验证绑定收据SHA，再将其expected/actual完整SHA与bytes分别对照批准的原A0请求/收据，并核对receipt schema/成功状态；可在caller强制或给helper加入独立expected参数，不必重造科学平台。当前最终caller未提供，**这不是已证实最终A入口绕过**。
- **P1待最终入口闭合：fd传递与消费后复验。** scan:102已关闭fd，reuse:115重新打开，因此不能称扫描与后续任务从未换fd。reuse返回的fd必须一直用于后续所有成员读取，禁止传回旧Member按Path重开；消费前/阶段边界/发布前复验fstat和namespace，异常立即停止并保留partial。跨进程只证明stat/ctime/namespace连续性，不自动获得不可变快照保证，也不自动增加第二次扫描额度。
- **P2预算需精确：** scan:82每次读整chunk，文件并发增长时，拒绝前可能多读最多一个8MiB chunk；请求须明确EOF探针和最坏读入计费，或采用remaining+1收窄。scan:69–103保存handler而未保存旧ITIMER_REAL剩余值，若嵌在带总deadline的caller中会重置并清除该timer；最终入口应独立子进程且无ambient timer，或正确组合/恢复剩余总时限，不能称已保持父clock。

现测试覆盖内容不符、stat drift、两类symlink、扫描期改写、RSS/时间与空收据，但“forged receipt”仅测空dict；应补上独立A0错配/自洽假收据、消费期间/之后漂移、路径替换、外层HTTP前门禁，以及实际bytes/既有deadline分支。真实11GB扫描仍由DATA单独处理。

生成探针：`/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration/.local/zip-review-generated-20261015-01/reuse-contract-probe.json`，SHA `0424a3a917cc1f3afa16321a4a52c9b716867693c50e6fc88af4aea6991ffa8f`；源代码小快照保存在同目录。仅创建本机生成opaque字节并调用helper的secure_open/reuse，scan_calls=0，真实归档stat/open/read/hash=0，网络/标签/CT/权重/模型/队列写入=0；不修改DATA源码。**当前结论为开发快照有明确caller条件待闭合，最终新A入口待提供，未授予或执行A/B—D。**


## 新A/B入口开发快照跟进（待最终SHA）

`archive_bound_ab_v2.py` SHA `a8dad727dc5fd282bf831fdd9ec07676b7182abb8d8e83aaa42935c00d102767`（218行），测试源SHA `ff56b677b2828d3e3430635c0e79b9c1d4d1860d52155a5a2bce6a3c53e83b40`。

已在caller闭合前述两个P1条件：bound_identity:92–106将receipt的expected/actual SHA与bytes独立对照原anchor及原A0完整性字段；run:115先取得lease，才在135读缓存发现元数据及147读payload。SecureMember:24–74串行dup同一lease，未调用旧Path-reopen构造器，压缩读取前后/close/budget.check均复验fd/namespace。当前for循环只有一个活动Member，dup共享offset在此串行条件下可接受，不能扩展成并行解压。新入口没有discover/HTTP/scan调用，A来源只复用历史缓存，结果仍MAPPING_UNKNOWN/registry NOT_RUN。

**新增P1待修：check-only任意源码路径读取。** validate:79–81在run:112的无approval返回前，对request.source_bindings里的任意path调用无界prior.old.sha；source_bindings为空也通过。故不能仅凭CHECK_ONLY_NO_ARCHIVE_BODY_HTTP_OR_LABEL_ACCESS文案认为无归档正文读取：恶意或误填请求可把归档/标签列为源码，未获执行许可就发生hash读取。新模块应先检查精确已知源码闭包及单文件大小/文件类型，固定runtime对象；拒绝归档/标签/数据成员路径混入source_bindings，再做hash。最终正常请求正确填写列表不能取代该门禁。本评审未实际构造或执行这种真实数据请求。

最终绑定前还需核对：inventory与两个label member描述确实继承原锁定值；source/runtime闭包齐全；实际CLI+新job/task/output/supervisor目录与旧失败隔离，原slot拒绝重用；具体dispatch只释放新批准scope、原队列串行；scan字节/计时P2若由独立verifier限定则明确证明。源码测试已有独立A0错配、bytes错配、路径竞态失败保全、一次secure_open+两次dup、ZIP64及CRC/成员白名单用例，但当前未见真实main/dispatch/slot调用链的生成回归，不能只用entry.run测试宣称CLI已验收。

本节只是开发快照跟进，不否定已闭合项，也不提前批准最终版本。待总控提供最终源码/request/test证据SHA后，再对同一产物绑定结论；INT不改DATA、不扫描归档或重跑A/B—D。


## 最终固定版本收口｜2026-10-15

DATA commit `271b2203318602ea0839aa5e4f25a60fc8bae8a4`；entry/identity/test字节仍为上列a8dad727/c63c8ef5/ff56b677/75128cf0。固定新A请求SHA `2a776985783bbd3a9d8a1fdd9bc2a5f03f430b4a9ce807c0cfcad8ecedb8cd4f`；DATA最终索引SHA `719aea9231e26ecfa9229763886da3422c6790fac3ab74ccfac3ec8be385418f`。均通过本机实际文件核对，不依据会话口述升级结论。

**结论：固定请求的归档身份与成员读取接缝有范围工程通过（PASS_SCOPED_ENGINEERING_REVIEW），不是通用入口安全PASS、实际A执行PASS或批准。** 独立原R76/A0 expected/actual SHA与bytes关口、同一lease串行dup、memberfd/lease/path逐次复验和小成员ZIP64语义，前述两个caller P1已关闭；generic reuse只准在该entry强制原A0关口内使用。新entry无HTTP/全档scan分支。跨进程依据仍为已完成内容核验后的stat/ctime/namespace连续性，不能声称不可变快照。

INT实际只读核对：新请求与最终索引SHA MATCH；107个source_bindings中105个Python源码SHA/bytes MATCH，2个.so运行时未由INT重新hash；四份控制JSON（原R76请求1814362B、原A0收据、identity收据、cached discovery）SHA/bytes MATCH，独立原A0与receipt expected/actual SHA和bytes MATCH。请求source_bindings只含.py/.so，不含归档/标签/像素/权重。只检查新output/supervisor目录未创建，未创建目录或触碰真实queue/slot。原inventory及成员payload未读或hash，完整库存/运行时/共享依赖与fresh slot仍由总控最终准入核对。DATA报告18项生成测试PASS；INT已读对应测试源码，未重新运行DATA测试或真实entry。

**保留具体限制：** validate:79–81仍接受任意source_bindings并在无approval前hash；故任意新/被改写请求的check-only不能保证无数据正文读取，早期该finding没有被源码修复。对当前外部SHA固定且已核对仅含源码/运行时的请求，不把它误报为实际已读归档，也不作为原A0/FD修复未闭合。只允许总控围绕上述精确SHA形成后续批准；其他请求不能继承此结论，通用check-only仍需已知闭包/大小类型门禁。当前没有INT的main/dispatch/slot生成联测，不宣称CLI端到端已验收。scan的chunk/deadline意见不覆盖本新A（scan预算0），独立已完成扫描的证据由DATA/总控负责，INT未重扫。

新job `data-original-labels-ab-content-bound-02`，task `DATA-ORIGINAL-LABELS-AB-CONTENT-BOUND-02`，新output/supervisor目录均未创建；240秒、512MiB RSS、2MiB压缩输入、2105344B展开输入累计、1MiB输出，0F/0B、0新HTTP、0全档重扫。原失败/已消费slot与输出不重建；准入仍需新owner/dispatch及原队列释放检查。成功仅为AB_EVIDENCE_SAVED_MAPPING_UNKNOWN，不是标签语义匹配或医学空间通过。INT本轮真实归档stat/open/read/hash、标签/CT/权重读取、网络/模型/服务/医学浏览器/执行均0。
