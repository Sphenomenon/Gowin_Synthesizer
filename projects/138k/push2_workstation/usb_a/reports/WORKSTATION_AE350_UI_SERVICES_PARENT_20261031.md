# C02 父级：实际分步服务、PANIC 与启动栈校验

维护 `services_main` 现实际调用有界服务循环：绘制每步两行，模型／touch／页身份在 job 内冻结，完整写入和屏障后只发布一次，等实际 frame ACK 才换 front；采集每步最多取一个 record，释放等待每轮取一次真实 voice snapshot。最新请求留给下一 job，取消和排空／等待预算明确。原音频、参数应用点、事件布局及协议不改。启动的 DDR／音频自检循环尚未分步，实际 CPU 周期及最长服务间隔仍待测量。

原作者阶段 `350e8c1` 的回归在父级重跑通过后，新增“触摸读取撕裂＋已有 PANIC＋排队释放完成”组合独立复现旧 Note On 风险。后续 `31e092a` 将 PANIC 观察移出 touch 稳定条件，并在音频整份快照的 sequence 检查之前处理原子 pitch 中的 PANIC 字段；其他模型字段仍须完整快照。touch／audio／两者同时撕裂均撤销排队 gate，取消部分绘制并使下次完整重画。两份作者报告与旧失败证据保留原身份。

一并接入 `7305337` 的严格栈分析支持：优先匹配真实 GCC `.part.0` 名称，所有未知间接调用继续拒绝。可选人工目标闭包须绑定完整固件输入、整份反汇编、每个实际调用位置／指令／caller／目标集合；目标全部计入栈上界。它不是任意函数指针许可，也未在本阶段启用 BLE 业务。父级仅去掉一个重复 `hashlib` import。启动测试改用当前显式 64 KiB 冷容量，原 16 KiB 越界负例保留于独立存储回归。

## 独立验证

- 真实 C 主循环原生／ASan＋UBSan 各 34867 checks／2889 steps／5 publications，12 个编译成功的行为突变全部拒绝。三种撕裂分别验证 PANIC revision、目标 epoch、清 gate 和部分页作废／完整重画；观测最大 33 MMIO／轮，仅为这些向量的观测值。
- 两组转录各在锁定实际 UI APB RTL 回放，通过 7252 reads／15 writes／5 commits／5 resets。它验证寄存器语义，不是 CPU、DDR 或显示扫描时序。
- callback 栈四项、启动十二项、固件十项、存储四项、accepted sources 十七项、ProfileSources 六项、带真实 prepare 的 runtime sources 十二项通过。clean baseline 二十三项通过，包含三条无私有 staging 的完整 prepare。五个 profile 来源锁均加载成功。
- 实际 xPack 新配置 `custom138k-workstation-r00-no-local-panel-ilm64k-boot64k-v1-011fdc9c6697df42`：600 staged／269 enabled，266 编译单元／298 modules／2 packages，prepare 后 verify 通过。冷镜像 16624 bytes，当前可达保守栈上界 1184／16384 bytes；实际 RV32 镜像执行 208413 条启动指令后抵达 ILM 的 `services_main`。该模型没有执行完整服务运行期，不当作硬核证据。
- ELF SHA256 `733da2fcfa2d0d7bf531ab4d8dd44f6d8c0e9a555f8ced3e60d59d06ed358d00`，BIN `e32da185c82d93b0f2ba24ee94adea3f40b5fafb62ab14111deb808c2455bf78`，ROM `944acfb1e3e2d88e1021813404c890e1a14c6a533102eb5595fcce9e75d818af`。
- 原存储 no-panel 也实际 prepare／verify：`custom138k-workstation-r00-no-local-panel-v1-3b7b10b7885ec9b9`，599 staged／269 enabled，16100／16384 bytes。它继续原存储策略，固件字节变化有独立身份。作者报告中的 Homebrew 结果与此 xPack 结果分别保留，不能混用容量数字。

机器记录：[ae350_ui_service_parent.json](workstation_task_20261030/ae350_ui_service_parent.json)。父级包 `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-ui-service-parent-v3` 封存 16 份源码与 2299 项外部输入／产物，`verify.py` 可只读核验；seal SHA256 `b25a2810db0fe0dabdee5de061b849f981d7e318e575ea22ca9e6a4e8268a78e`，receipt `4bfc879ccd1f933e77b99ae6f2ecac6254a570dfe9f5c55aa651754f898b0c3f`。初次 prepare／profile 因前阶段最终说明文档漏锁而拒绝，原日志保留，单独修正见 [C06 文档锁记录](WORKSTATION_AE350_BOOT64_DOC_LOCK_20261031.md)。

无综合、P&R、板卡、SRAM 或 Flash 操作。完整 CPU 服务期限、实际业务 owner 替换、Cache／DMA、同功能资源、物理门禁和硬件验收仍未完成；C02／C04 等整项不提前勾选。回退以 `e2b6b7f` 恢复本阶段源码／锁并重建新候选，保留固定旧证据。
