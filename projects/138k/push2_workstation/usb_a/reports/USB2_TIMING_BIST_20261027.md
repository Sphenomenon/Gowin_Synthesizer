# USB2 热插拔候选：DDR BIST 比较路径收敛（2026-10-27）

## 已知失败与本轮范围

上一轮独立物理候选 `custom138k-native-physical-C127E101` 的真实 P&R 返回 0，但 STA 不通过，不能部署。最差 setup 为 DDR UI 域 `u_video/u_bist/address_3_s1/Q` → `u_video/u_bist/failed_s0/CE`，−3.496 ns；音频包络、识别参考域 setup 和 DDR PHY hold 也有真实违例。原始证据和全部门禁见 [ULPI 物理报告](USB2_ULPI_PHYSICAL_20261027.md)。本轮不把已知失败改标为通过，不降低频率、不加宽 false path、不删功能。

读请求发出后，旧 BIST 在等待响应期间保持地址不变，但响应比较仍组合展开 256-bit 地址模式。新板显式选择版本化的 `rtl/memory/workstation_ddr_bist.v`，在接受读请求的同一拍保存预期数据，后续直接比较保存值；不增加请求／响应或完成周期，不改读回错误、首错地址、超时或饱和语义。旧父 BIST 原字节保留并禁止编译，替换关系与新源码绑定现有 `integration_inputs.json`；accepted／timing85／原 resource-timing profile 不切换。没有修改冻结网表、原始清单、DDR 地址分配或外部网表。

这是针对实际关键路径的结构变更，不凭 RTL 推断物理时序已经改善。新原生来源必须重新 prepare、综合与独立审计，使用新的离线物理身份，不复用 C127E101 的位流或通过字段。

## 针对性验证

`sim/test_workstation_ddr_bist.py` 直接重建锁定 resource 父输入，独立改名作为参考模块，与新模块共享同一组时钟、请求背压、延迟／损坏响应。逐拍比较全部公开输出，并用独立模式函数检查写数据：

- 两遍完整模式读写且无错误。
- 每个 lane 的错误注入与首错地址／错误计数。
- 32-bit 错误计数到最大值后不回绕。
- 命令持续背压超时、响应不返回超时。
- 在途读响应期间复位，随后完整重新开始。
- 完成后迟到响应不能重新发起请求或改写终态。

实际模块回归为 3 项通过，含 548 次逐拍输出比较、68 次请求时预期模式保存检查。Yosys 在 `async2sync` 后以复位对应的全零初始化和 4 步时序归纳，检查全部匹配状态／公开输出，并额外**证明而非假设**“READ_RESPONSE 状态下保存模式等于当前请求模式”的不变量；仅不匹配在非响应状态下本来无意义的内部 `mismatch` 线。BURSTS／TIMEOUT 的 1／1、2／2、8／31 以及实际生产默认参数均通过；将保存模式最低位故意翻转的负例被拒绝。未加强不变量的首次弱等价检查不能证明全部节点，不计入通过；实际强化脚本／日志在首轮证据的 `formal/strengthened.*`。

## 实际综合与映射选择

首轮保存模式但未分段的来源证据在 `~/.cache/fpga-usb2-bist/20261027-205605-registered-pattern/`：

- 原生 prepare／Gowin 综合／独立审计实际均返回 0，耗时 768 s，来源闭包 627 项；只为新板显式替换 BIST provider。
- 74 项 targeted 测试通过；完整 `test_workstation_custom_board*.py` 的 32 项实际通过，691.318 s，返回码 0，日志 SHA256 `58c057fd7897aad40adfae641b4e43d317c03b7e0b198a6c16bf0f2b644f44b0`。这些结果属于该轮原始来源，不改标为后续字节分段来源的完整回归。
- 原生清单 SHA256 `7b4fb9aea03e3c910a99af354be03e51160f13baa6c23b4c636eeac5e46f1603`，综合网表 `320f3ba449228c7a8eaa13f431561a329bd64d800f70bcffc735b3b8c774fea3`，审计 `02f0143d0aad0559d753ecc45195e3848c4585e84cf4ef24bcfe1215ac5db095`。
- 综合实际 Register 54219、Lut 73066、Alu 15543、BSRAM 等效 272、SSRAM 419、DSP 46／41／45；仍区分等效与物理 BSRAM。精确回归计数根据实际新来源更新，不放宽资源门禁。
- 实际网表失败寄存器 CE 输入锥不再含原来的 26 个地址寄存器源，改为 52 个保存模式寄存器源；但工具将整字比较映射成 **256 级 ALU 链**。因此不能仅凭增加寄存器宣称时序改善。
- 独立物理实验身份为 `custom138k-native-physical-C127E102`，UserCode `0xC127E102` 仅离线输入；CST 只增加此前审查的 12 个 ULPI `LVCMOS33`，全部位置、其它 CST 字节、SDC 和网表与该轮父输入逐字保持。实际 P&R 返回 0，耗时 1100.659 s，位流 SHA256 为 `a2af1f7d428225f47a9252511780168af7b604f5a64cf65980f6695c925e4818`；STA **仍失败且变差**，最差 setup −4.456 ns，来源为 DDR arbiter `response_data_0_s0/Q` → BIST `failed_s0/CE`，data delay 14.227 ns，hold −0.905 ns。未将此改动当作可用候选部署。固定原始检查器的实际结果为 timing 1、common CDC 0、routes 0、PLL 0；后三者仍只有此前声明的历史覆盖，不能替代完整 a26 门禁。

为避免凭经验继续尝试，另用相同器件 `GW5AST-LV138PG484AC2/I1`、相同头文件和实际 Gowin，分别综合只含 BIST 的四组明确源码；不是复制整机工程或生产输入，不进行部署。`byte-comparison-synthesis-v2/results.json` 记录四次实际综合均返回 0，失败使能输入锥的最长 ALU 级数：旧地址展开为 0、整字保存比较为 256、32 字节普通分段为 8、带 `syn_keep` 的分段也为 8。0 不表示旧路径 STA 为零，内部 LUT／路由仍有延迟；这只是映射结构比较。早期辅助解析未处理独立顶层 IBUF／GSR 的两次异常不计通过；修正后仅明确排除无组合数据输出的全局复位及由 canonical 解析透明处理的顶层 IO buffer，未忽略未知比较逻辑。

选择无需额外属性的普通 32×8-bit 分段。当前版本化源码 SHA256 为 `d3737f42447cae6ddcf3c6939ffe9f937f4a2d72854fe3fbe549b3667031fb5c`，逐字匹配上述实际综合的普通分段输入。公开功能仍是全部 256 位精确比较，单字节差异不会丢失；没有新增节拍、延时约束或 false path。整机综合回归同时检查实际 BIST 失败输入锥：无直接地址源、确有保存模式源、最长 ALU 级数不超过 8，防止再次生成整字链。

当前字节分段版本的独立证据根为 `~/.cache/fpga-usb2-bist/20261027-213432-byte-comparison/`：74 项 targeted 回归已实际通过，13.995 s，含上述全部功能／形式／负例；新 prepare、整机综合和独立审计均已实际返回 0，耗时 776 s。来源闭包 627 项；音频原生反馈源／目的域寄存器仍为 158／160 个，物理时序验收仍为 false。

| 当前字节分段来源／证据 | SHA256 |
| --- | --- |
| 原生 `integration_inputs.json` | `52d86eb6ed021f2ab94f4a7e4ca834ef3b7b731ae1da878387cff7d7b8d33c89` |
| 实际综合日志 | `21e9d06257fa4eac15345bb1ec732cf3286cfb958849495c962fe06ddb2aa066` |
| 实际综合网表 | `c3d0a433826a268895ae339f09f2a4f6acc02a0a701e9020937e7e79ae7a7f3f` |
| 独立综合审计 | `9258c5f5931234c8014e63fd071ac699349e2c4e2d8734d0e1a301c9f1d0f893` |

当前整机实际网表的 `bist-netlist-cone.json` 已确认：失败寄存器输入锥直接地址源 **0**、保存模式源 **52**、最长 ALU 链 **8**。`bist-fence-negative.json` 用真实 C127E102 网表确认 256 级反例不能通过同一检查；不是仅用模拟 fixture 验证门禁。当前综合实际 Register 54219、Lut 73127、Alu 15544、BSRAM 等效 272、SSRAM 419、DSP 46／41／45，完整综合回归保留对应的精确计数，不放宽上限。结构改善不等于路由后时序闭合。

独立物理身份 `custom138k-native-physical-C127E103`，UserCode `0xC127E103` 的实际 P&R 已于 **2026-10-27 23:36:07（UTC+8）**结束，退出 0，耗时 **3685.888 s**。物理准备与全部输入哈希、全部位置、CST 其它字节、SDC、网表保持检查通过；本轮完整 `test_workstation_custom_board*.py` 为 **32 项通过，620.289 s**，另有针对性回归 **74 项通过**。原始结果在本轮缓存的 `pnr-retry-20261027-223414/pnr-execution.json`、`custom-board-regression.log` 和 `targeted-regression.log`。实际 `.fs` SHA256 为 `ad88c5aa2ec808bbff54e62588517c8207e1d0860ebb82c86c7718077fb1a0d0`，未部署。

历史 common-CDC／routes／PLL 检查均返回 0；历史 timing 检查因 `tools/audit_workstation_timing.py` 的并行 API 扩展触发 dependency drift，在解析报告前失败，保留该失败，不修改冻结检查器。用当前解析器额外读取同一实际报告，`supplemental-current-timing.json` 记录 **setup −0.398 ns、hold −0.754 ns、recovery +2.644 ns、removal +0.250 ns**，`timing_closed=false`。当前最差 setup 在音频包络更新→包络寄存器，最差 hold 在 DDR PHY 初始化→wloadn，不再是旧 BIST 的长地址组合链；完整工作站时序仍未闭合。补充解析器 SHA256 为 `78b20977de69f63ee91eccc1978b49eb377e6b2569898537c6f8033b3f328a6f`，不把补充结果登记为历史门禁通过。

为避免后续 USB 热插拔调试每轮都等待整机，另有 [轻量 USB2 诊断配置](USB2_HOTPLUG_DIAGNOSTIC_20261028.md)：本机实际准备＋综合＋P&R 为 91.811 s，不含 DDR 或整机音频引擎；两种配置保持独立。

## 剩余条件与回退

音频／识别 setup、DDR PHY hold、完整原生反馈路由覆盖、ULPI 外部时序仍是独立待完成项。旁路电气唯一待实测仍为 USB3300 ULPI IO 是否确由 3V3 供电；实际测量和完整电气验收均为 false。没有板卡操作授权，不操作 JTAG、SRAM 或 Flash。新板部署／回退状态不因离线工具成功改变；此项代码回退仅须撤销新板 BIST 的显式 provider 选择，不改冻结文件或其它 profile。
