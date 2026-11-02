# W26 手机蓝牙音频联调

2026-11-02，分支 `codex/w26-phone-audio`。本轮保持 W26 音频配置；不写 Flash，不安装旧版 App。

手机现装 `cn.gowin.control` APK 已先导出：versionCode 18，`0.3.3-ble-lifecycle`，SHA256 `d3160a8e539cb357bd25bfe75c7a8defc84f84c84cf1b656299a2631008bf0af`，与 `origin/main` 的 `f1839911` 产物一致。W26 未接业务 GATT，App 的“查找工作站”不是本次 Classic 音频入口。

实际 Classic 设备名 `RTK_BT_4.1`，地址 `34:20:03:3D:8A:62`。手机完整 HCI 日志证明：板回复 NoInputNoOutput／NoBonding (`03 00 00`)，手机回复 DisplayYesNo／DedicatedBonding+MITM (`01 00 03`)，随后 Simple Pairing Complete 为 `05`；未进入认证、加密或 AVDTP。该请求触发固件对所有奇数 AuthReq 的拒绝分支。

修复仅允许 session-only 模式继续协商 Just Works；持久绑定模式保持原拒绝行为。仍要求 SSP 未认证组合密钥类型 4、认证成功、加密成功和有效密钥长度才开放 AVDTP；不宣称 MITM。新增真实请求及 AuthReq 1/3/5 回归，保留非法字段拒绝测试。

已完成：

- `run_ae350_security.py`：原生及 sanitizer 各 17,032 检查；worker session 各 2,577 检查；32 个变异均被拒绝。
- `test_current_workstation_sources.py`：17 项通过。
- 现有 W profile prepare／固件链接通过。ILM 使用 30,304/65,536 bytes，DLM 静态区 7,008 bytes、栈 16,384 bytes；未扩容、未启用 cache。

新整机候选 `custom138k-workstation-w-demo-v1-5458e8c6f51de94b` 已完成全量综合及原生功能／CDC／资源门。与 W26 同功能比较：FF 27,030、LUT 30,747、ALU 11,252、BSRAM 等效 192、SSRAM 177，全部增量为零；没有新增 CPU 存储、邮箱、队列、总线或 A2DP/SBC 成本。实际 runtime/MMIO 回归也通过。此次仅改固件配对策略及测试，没有新增业务迁移或退出 RTL 状态机。新物理身份 `D21102B2` 已完成完整 P&R（约 7 分钟），沿用 W26 的 CST／SDC 与同一 160-bit GAO。14 个时钟域 setup/hold 违例为零，最差 setup/hold/recovery/removal 为 +0.013/+0.092/+2.376/+0.281 ns；PLL 及必要实际 routed CDC 正向检查通过。物理功能资源 LUT 30,655、FF 27,030、BSRAM 218；GAO 单列增加 LUT 549、FF 872、BSRAM 9，总 BSRAM 227/340，与旧诊断候选一致。已 SRAM 下载并独立读回 `D21102B2`／`00022230`；新 FS SHA256 `1d5cce562eb2f7adfefcdca8a434259045bed13598feb471343ca44bb16f62dc`。CPU／蓝牙初始化正常，正在重测手机配对，尚未验收音频。

门禁复用已封存并验证的 `w26-audit-tools-v2`（封存 SHA256 `30bfa7ce102ab5f65d90069a6d567779e06e5bbd5f43709fe01065e277eb309b`），对新网表重新执行。当前 checkout 的旧检查器会误拒绝综合网表省略的 DFFRE INIT；v2 仅在 synthesis 映射绑定官方 primitive 的默认 INIT=0，routed 映射仍要求显式 INIT=0。未放宽电路或时序要求。

已有诊断候选 `D21102B1` 来自冻结 W26 网表，增加 160-bit GAO；完整 STA／PLL 门通过后 SRAM 下载。用户再次断电后已重新下载并独立读回 `D21102B1`／`00022230`。已观测 CPU 活跃、H5 快速模式／初始化／bootstrap 完成、无 fault/fence；这不是音频验收。

原始 APK、手机日志、GAO 捕获和新候选存于本机 `~/.cache/gw138k-phone-20261102/`，不提交包含用户信息的 bugreport。回退位流为冻结 W26 `D2110143`，SHA256 `4b76a2c5b991cbd268b2e72f2cc9f8538e7ad8ea23fbac677b82372e30b755af`。Flash 保持原样。

16:06 的手机 HCI 记录确认 Simple Pairing Complete=0、KeyType=4、Encryption Change V2 成功且密钥长度16；另有并发的 Authentication Complete=0x23，不能将该事件写成成功。手机发出一条 Information Request 和两条 SDP Connection Request，未收到任何板端 ACL 回复，尚未进入 L2CAP Configuration 或 A2DP。为定位这一个阻塞，W 固件复用现有 signature／heartbeat 寄存器报告实际 ACL 包头、处理结果、会话匹配及收包次数，不增加 RTL、队列或日志存储。完整 runtime 回归的11个 SBC 用例原生／sanitizer各3,758检查通过，15个runtime和9个PCM变异全部拒绝；17项来源测试及新整机prepare通过。新候选 `custom138k-workstation-w-demo-v1-ca738499987f6d7e` 的后续综合、P&R和板测独立记录，不改变冻结 B2 输入。

该候选已完成全量综合与必要门禁，资源相对 B2 仍全部零增量。物理 `D21102B4` 完成完整 P&R，14域零 setup/hold 违例，最差 setup/hold/recovery/removal 仍为 +0.013/+0.092/+2.376/+0.281 ns；PLL及四项实际 routed CDC 通过。功能资源仍为 LUT30,655／FF27,030／BSRAM218，原160-bit GAO另占9块BSRAM。已 SRAM 下载并独立读回 `D21102B4`／`00022230`，FS SHA256 `953295723ff4ac11127cb75e28af00018a190ec53042b63beb247022064cc346`。B3在放置前因综合网表将 `link_up` 改名为 `link_up_Z` 而拒绝，B4仅绑定已核实的新别名，未扩展GAO宽度或放宽门禁。板初始化完成、故障为零；音频仍待复测。

用户换为 vivo Y77（Android12）后，已先导出现装同版本／同SHA的APK。新手机在B2上的配对已由 AdapterService 确认成功，但A2DP仍未连接；不会将bond成功当作音频通过。旧手机已断开，其临时HCI日志／USB常亮设置仍待重连后还原，原值保留于本机缓存。

新手机在B4的两次配对均未收到板端IO Capability Response，Simple Pairing／Authentication Complete为0x18，实际ACL收包计数为零；因此本轮先处理SSP阶段，尚不能定位原始SDP无回复。固件修复IORequest早于LinkKeyRequest的合法顺序，重复IO请求保留原deadline且仅回复一次；session路径仍须真实type4新key、认证、加密和有效key size，durable路径仍等实际key lookup。首ACL前复用现有signature显示首次关闭上下文，无新增RTL／GAO／存储队列。完整security原生及sanitizer各17,904检查、W session各3,284检查和32变异通过；runtime各SBC用例3,759检查及15+9变异通过，来源17项通过。证据为本机缓存`io-order-security-final`及`io-order-runtime`；新候选随后独立综合、P&R和上板，不继承B4音频验收。

顺序修复整机候选`custom138k-workstation-w-demo-v1-dc79a470bb3e8135`已完成全量综合及必要功能／CDC／资源门；staged相对B4仅`firmware/boot.mem`改变。资源仍为FF27,030／LUT30,747／ALU11,252／BSRAM等效192／SSRAM177，全部零增量；ILM30,816 bytes、DLM静态7,024 bytes及栈16,384 bytes，未启用cache或扩容。本批仍为现有CPU业务互操作修复，无新增RTL业务卸载；P&R与新手机音频复测尚待完成。
