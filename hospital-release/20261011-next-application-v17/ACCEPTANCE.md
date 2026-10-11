# 实际验收范围

开始HEAD cad49f20d7f5d77027ca955e4a609abebb6fe58e；分支codex/epi-next-integration-20261009，原指定工作树。代码提交见manifest。Python3.11既有环境，CPU生成2D函数；没有真实权重、患者读取、GPU/远程3090/队列操作。

| 实际检查 | 结果与范围 |
| --- | --- |
| 后端/Worker | 78 PASS / 4.49s；独立ALGORITHM提交、6终态、保存GET刷新、SHA、丢失响应只查询receipt、同request换UUID不重建、同Job不重算、旧Worker隔离、旧API/认证/幂等回归 |
| 实际LOC跨线 | 正式source9ae67d74ca695bac12bf3f2e2f0007438f72c79f与dependency lock一致；handler→core→native图层→multipart→存储→GET刷新；6/4/4合成F/B/update，实际NO_RELIABLE_RESPONSE，不降低阈值造Mask |
| 零模型回放 | 上述生成结果以PRECOMPUTED保存；新增F/B/update0，原证据SYNTHETIC/源SHA/原成本保留；同原生图层并刷新一致 |
| SQLite迁移 | 包含在78项中；生成旧表/旧Prediction行升级，索引/FK/其他check保持；存在ALGORITHM时拒绝破坏性downgrade。未迁移原M0/真实DB；PostgreSQL部署NOT RUN |
| 前端 | 19 files /164 PASS /1.83s；包含新证据类型、partial叠加关闭、源身份、研究数组入口、资产篡改、选择恢复及原功能回归。JSDOM提示scrollTo未实现，不当作真实浏览器验收 |
| 类型/构建 | vue-tsc exit0；Vite build exit0/424ms，35构建文件SHA，独立next-application-v4-dist；M0 dist不覆盖。既有codec path/fs外部化与大chunk警告保留 |
| 空间/医院gate | 34 PASS/0.24s，生成方向/切片排序/斜位world往返/crop/resize/resample/源SOP和拒绝未验收算法；生成锁守卫，不初始化MPS或观察真实队列 |
| 历史保全 | 16个原v15/v16文件逐字MATCH；A/B/C、GT-v1、FrozenBaseline/预处理/研究协议代码无差分 |

76项套件首次汇总75 PASS/1 FAIL：新隔离fixture缺既有X-Request-ID，已补齐并使用全新生成目录，最终78 PASS（补2项加载入口测试）。旧失败receipt保留在忽略目录。早期fixture的Blob API、int/float canonical digest及迁移FK反射顺序修正均仅为测试/工程兼容；没有放宽算法阈值。

| 医院八项 | 当前状态 |
| --- | --- |
| 原始脱敏CT正确显示 | M0旧开发单SOP有历史证据；医院配置NOT RUN |
| 模型真实可追溯 | M0旧链已完成；新E2/CTFM真实应用NOT RUN |
| 热图与原CT空间正确 | 生成native gate PASS；新算法真实六项Series空间验收NOT RUN |
| 保存刷新恢复 | 生成新链PASS；医院真实新链NOT RUN |
| 失败清晰 | 六状态生成PASS；真实失败/partial演示NOT RUN |
| 旧版回退 | 代码/生成gate PASS；医院冻结回退演练NOT RUN |
| 连续三次真实演示 | M0三开发流程已完成；医院冻结配置三次NOT RUN |
| 真实预计算与备用录屏 | M0开发预计算保全；医院批准备份及录屏NOT RUN |

当前RICORD DATA v3/Prepared2DInput已交付，旧M0完成，不将其重新标为数据阻断。新E2-Q真实应用NOT RUN，等待新的执行批准及完整科学产物/三例共享全局预算启动封装；CTFM等待新训练head和volume handler。新医院allowlist仍未冻结，医院冻结NOT RUN；这些不阻断纯工程开发。E1/F0/F1研究sidecar不等于应用安装。

后续加载/5F入口补齐后仅追加3项定向生成测试PASS/2.72s，2项覆盖原加载入口，1项独立验证5次逻辑guard回调、B/update0、无模型文件读取；与78项套件有重叠，不累加成81项独立测试。不做额外全量重跑。具体函数及剩余真实argv绑定见LOADING_ENTRIES.md。

独立5F绑定后追加6项定向生成chain测试PASS/0.02s；外置dispatch单向绑定科学binding，无哈希自引用。metadata-only CLI exit0、输出目录未创建；实际owner/admission/dispatch均未创建。E2-Q函数不代表三例全局预算封装，工程状态ENGINEERING_NOT_READY。
