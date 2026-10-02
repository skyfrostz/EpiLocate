# 被动会话复核：保留布局与隐私遮蔽

## 范围与依据

基线`c565b7f3a323fc583faac13dac8aeb497c11f24b`，独立分支`dot/passive-session-layout-20261002`。已有Mac固定viewport正常硬件Chrome的合成focus（isTrusted=false）、受控约5秒鉴权延迟记录显示：旧App display:none使stage从正常尺寸变0再恢复，overlay归零再恢复；主CT canvas尺寸保持，未记录longtask，worker数量为2。此证据不是原生focus复现，不证明camera或主CT canvas重置，也不能确立其他卡顿的根因。

## 最小安全改动

- 初次未知session及明确失效仍使用原`!auth.loaded`硬加载边界。
- 仅被动`auth.verifying`时保留workspace的DOM、实例与布局，立即设置祖先opacity:0、inert、aria-hidden及pointer-events:none；不使用display:none、延迟遮蔽或淡出。
- 外置fixed、不透明、无正常文档流占位的核验层覆盖旧内容。祖先opacity不能被移动sidebar的visibility:visible覆盖。
- AppShell全局导航keydown在verifying时提前返回；inert不能阻止window级监听器，避免Escape/Tab修改隐藏菜单状态。核验结束恢复既有键盘行为。
- session.ts、sessionSync.ts、API客户端、CSRF/epoch/服务器复核、未决响应门控均不修改。真实账号/CSRF变化与401清理仍由既有逻辑执行。
- 未修改Cornerstone viewer、module init、ResizeObserver、像素映射、模型/算法/Worker。没有减少服务器检查。

严格身份未知边界仍需要暂时遮蔽旧内容。这个补丁移除已证实的布局折叠与整页login替换，不承诺零视觉转换或所有卡顿消失。当前没有teleport/modal/toast逃离workspace的用法；将来新增此类UI时需单独审查遮蔽边界。

## 新验证

- 强化/新增DOM期望在旧App呈现上4项失败；隐藏菜单Escape用例在旧window监听器上失败，补guard后通过。
- 全量120/120（16spec），TypeScript及`VITE_PUBLIC_BASE=/mvp/ npm run build`通过。原codec/bundle警告保留，无独立lint配置。
- DOM测试覆盖初始未知、同session实例/输入/幂等键保留、立即不可见与inert/aria-hidden、显式visible移动菜单、隐藏菜单Escape/ShiftTab、揭幕后Escape/焦点恢复、账号/CSRF变化、401/503；既有请求门控、超时与过期测试继续通过。
- 使用附着到document.body的jsdom fixture。初次detached fixture在移除祖先inline opacity后返回过时computed opacity，改为正常附着fixture复验，未修改生产遮蔽逻辑以迎合该缓存。
- 扩展现有合成浏览器脚本：受控focus至少5秒，记录实际trigger-to-release时长，逐样本比较stage/overlay尺寸、滚动位置、遮蔽/可访问状态，再核对恢复尺寸和相同DOM；手机打开菜单时验证隐藏键盘行为及恢复。仅语法检查通过，尚未在此补丁上运行真实浏览器，不用jsdom声称尺寸不归零已实际验证。

独立源码安全审查无发现阻断。仍需Mac对本新提交复验，特别是实际尺寸、可访问性、正常硬件条件；不沿用基线浏览器结果。未push、主线merge或部署。交付包含相对c565b7f补丁、自包含bundle及新验证日志，并做私有持久化。
