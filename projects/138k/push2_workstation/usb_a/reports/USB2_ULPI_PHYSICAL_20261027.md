# USB2 旁路 ULPI 离线物理收尾（2026-10-27）

## 起点与范围

上一轮真实生产 CPU／USB3300 模型／25K MIDI-PL RTL／合成 Push peer／原生 DSP＋FPC I2S 的 HS、FS 交替热插拔均已最终通过；原始日志、源码／ROM 身份和边界见 [混合音频报告](USB2_MIXED_AUDIO_20261027.md)。不能据此宣布实物热插拔完成。

本轮从当前工作树复核 `~/.cache/fpga-usb2-feedback-fence/20261027-184109-verified-inventory/native`：独立综合审计仍返回 0，反馈源／目的寄存器分别为音频域 158 个／USB 域 160 个；两个真实音频执行返回码均为 0。审计证据在该根目录的 `completion-review-193441/`。

实际物理输入存在明确缺口：12 个 ULPI 球位齐全，但没有显式 ULPI `IO_TYPE`；SDC 定义 60 MHz 外部时钟，却没有 ULPI 外部输入／输出延迟。CDC 与时钟审计的 `physical_timing_verified`／`native_constraints_complete`／`routed_timing_verified` 等门禁仍未通过，也没有该输入身份的 P&R 结果。物理收尾不能借用旧 HDMI 或旧 a26 实验的位流、时序、UserCode 或板测。

## 版本化实现

在既有 `tools/workstation_custom_board_implementation.py` 增加显式 `--ulpi-bypass-lvcmos33`，不新建编号 builder 或源码 CST：

- 必须先通过原生综合网表审计，并绑定完整 pinout 的 SHA256。
- 仅接受 U4／U5 同时 `not_fitted_short`、B 侧名义 3300 mV／指定供电节点／网络、空电气 findings，以及两个验收标志仍为 false。
- 精确核对 12 个已审计 ULPI `IO_LOC`，拒绝已存在的 IO 类型声明，追加且只追加 `LVCMOS33`；保持原 CST 前缀字节（含 CRLF）、所有其它端口与球位、综合网表和 SDC。
- 同时保存原生父输入哈希、实际物理输入哈希、父 pinout 副本和标准适配的 before／after 哈希；不得改写旧候选或来源清单来通过审计。
- 调用者的风险确认限定为离线物理实验，显式记录 `board_programming_authorized=false`；不表示用户授权 SRAM／Flash，不表示实际 3V3 供电已经测量。
- `actual_board_measured=false`、`full_electrical_acceptance=false`、`external_io_timing_complete=false` 及发布／部署／硬件门禁保持。

追加 5 个测试覆盖许可边界、实际准备与原字节／位置／SDC 保持、错误装配／供电／验收声明、球位漂移／已有 IO 类型、pinout 哈希漂移。与原生物理准备、引脚和 accepted 来源边界共 64 项测试通过，日志为 `~/.cache/fpga-usb2-physical/20261027-195054-ulpi33/targeted-tests.log`。

物理准备工具本身位于原生 source snapshot 闭包，修改后旧候选不能再充当当前全来源审计证据。本轮已重新 prepare、真实综合与独立审计，再创建独立物理身份；没有伪造旧 manifest。原先真实音频执行证据保留为其原始输入身份的成功记录，不擅自改标为新输入通过。

## 本轮实际来源与物理输入

独立证据根目录为 `~/.cache/fpga-usb2-physical/20261027-195054-ulpi33/`，原生开发配置仍为 `custom138k-native-integration-20261027-a26`，没有切换 accepted profile。实际 prepare、Gowin 综合和独立审计均返回 0；来源闭包包含 626 项。反馈音频源域 158 个／USB 目的域 160 个寄存器通过实际网表域核对，`physical_timing_verified=false` 不变。综合统计为 Register 54184、Lut 73423、Alu 15284、BSRAM 等效 272、SSRAM 419、DSP 46／41／45；BSRAM 等效值不是物理块数。

| 输入／证据 | SHA256 |
| --- | --- |
| 原生 `integration_inputs.json` | `07e5a262ec1a3bbaa37d0f0c7046aaeda53e222dfe34563ee828551300f57d46` |
| 实际综合日志 | `ff0e43e7dcbd0a1622cb72055c7dc269eebcb6d44fa1e83e5fc5af4396f598c5` |
| 实际综合网表 | `381d7cc846fb7d39a68978f862665ab1fc85ce327744ef6f23f9a7bdf0894f96` |
| 独立综合审计 | `7ca14a7aa3fbcb70f6bb7a3ba0fc63596981dbba80ace646fb55ed8fba969a21` |
| 物理 `physical_inputs.json` | `b7187563b221c62038498a1b3db9ee0ae75a64c2b6d79c82e9e340fb1a700a7c` |

对上一轮真实音频输入另做了严格比较：230 个启用项目输入、项目字节及顺序一致；414 个逻辑／ROM／约束输入仅 `native_bluetooth/patch_path.vh` 的候选绝对路径不同，两个被指向的 patch ROM 实际字节与 SHA256 一致；626 项来源快照只改变物理准备工具。两个原有真实音频 bench 的各 17 个直接源码哈希也与当前工作树一致。细项在 `logic-input-comparison.json`，这是来源比较而不是新执行的音频测试。新综合网表去掉整行注释后仍有差异，`synthesis-netlist-comparison.json` 明确记录为 false，不能宣称网表逐字相同或已做形式等价。

本次独立物理身份为 `custom138k-native-physical-C127E101`，UserCode `0xC127E101` 仅写入离线构建输入。`physical-input-verification.json` 独立核对了全部输入哈希、12 个 ULPI 位置、原 CST 的其它字节、SDC 和综合网表：物理 CST 精确等于原生 CST 加 12 行 `LVCMOS33`，没有其它变换。`board_programming_authorized=false`；没有将该身份写入实物。

## 验证与剩余门禁

本轮最终离线结果：

- `sim/test_workstation_pinout.py`：32 项通过，0.501 s。
- 完整 `test_workstation_custom_board*.py`：32 项通过，674.836 s。成功依据为实际完整 unittest 日志末尾的 `Ran 32 tests`／`OK`，进程已经退出；启动包装器的返回码没有另行重新捕获，不伪造该字段。
- 物理准备／引脚／accepted 来源边界的 targeted 回归：64 项通过，0.587 s；与上述测试存在重叠，不相加为独立测试总数。
- 实际 prepare／Gowin 综合／独立 `workstation_custom_board_audit.py` 均返回 0；最终再次核对当前 626 项来源哈希及全部物理输入哈希。
- 用锁定的三个外部网表独立生成纯 pinout，全部 101 个端口、retired ports、核心约束和其它端口与 HEAD 一致；CST 字节不变，SHA256 为 `282a251a97016aa774b14277ba534c1d29c57ca05b6b8a87bd9afd08bace352b`，没有给纯 pinout 渲染增加 ULPI `IO_TYPE`。配置变化仅旁路、电气依据及首项 implementation gap。
- 独立离线 P&R 实际返回 0，耗时 1234 s；位流 SHA256 为 `111cf566564a4817eca3ae36e89e2baf6936784496cdb47da999d1fe6d6c2f8e`。实际物理 BSRAM 为 **317／340**，不是综合等效 272；路由后报告中的 12 个 ULPI pad 均保留原球位并实际采用 `LVCMOS33`。

**该位流未通过时序，不能部署或用其宣称热插拔实物完成。** 原始物理输入、选项、位流与完整日志均在本证据根目录，没有降低频率、增加全域 false path 或删除功能。固定哈希、未经修改的历史检查器实际执行结果为 timing 1、common CDC 0、routes 0、PLL 0；后三者仅证明其既有覆盖。历史 routes 检查器的 DDR hold 专用分支仅匹配 a23，且没有覆盖本轮新的原生反馈路径，不能把跳过当作 a26 全部物理门禁通过。历史 timing 输出中的固定 `electrical_blocked=true` 属于旧检查器的保守元数据，不替代本轮 pinout 审计的名义电气状态。

实际 STA 最差 setup 为 **−3.496 ns**、hold 为 **−0.908 ns**；最差 recovery／removal 分别为 3.024／0.250 ns。主要失败端点：

| 检查／域 | 最差 slack | 实际端点 |
| --- | --- | --- |
| setup／DDR UI 100 MHz | −3.496 ns | `u_video/u_bist/address_3_s1/Q` → `u_video/u_bist/failed_s0/CE` |
| setup／audio 76.8 MHz | −3.478 ns | envelope attack ROM `DO[2]` → `envelope_level_q24[2]_9_s1/D` |
| setup／参考 50 MHz | −1.740 ns | `u_music/u_basic_pitch/state_0_s1/Q` → `dwell_count[7]_23_s1/D` |
| hold／DDR UI → 参考域 | −0.908 ns | DDR PHY `ddr_init_internal_r_s0/Q` → `wloadn_3_s0/D` |

参考／音频域 Fmax 分别为 45.997／60.609 MHz，未达到 50／76.8 MHz；不能以 ULPI 内部 Fmax 82.194 MHz 超过 60 MHz 来覆盖其它违例或冒充外部 IO 时序闭合。完整详细路径报告按既有上限输出，不能把报告条目数当作全部负端点总数。

最终机器证据为 `final-offline-validation.json`，SHA256 `b21f4666fb4ef29d2bf6eaed65c50d04a3bb6b1c101b0bc0cf5e268f4c8ef940`；其中 `timing_closed`／`physical_gates_passed`／`board_programming_authorized`／`hardware_tested`／`release_ready`／`deployment_allowed`／`sram_programmed`／`flash_programmed` 均为 false。下一步应分别在各 owning subsystem 处理上述真实时序路径，完善 a26 反馈与 DDR 的路由检查及 ULPI 外部时序输入，再按新候选身份重新验证；不以已有离线成功日志替代。

本旁路电气项唯一待实测仍是 USB3300 ULPI IO 是否确由 3V3 供电。完整 ULPI 外部时序、路由后端点与时序、实物 25K／Push 声画热插拔验收亦不能由本轮标准声明代替。本线程不操作板卡、JTAG、SRAM 或 Flash，现有部署与回退证据保持不变。本次没有部署，因此不需要板上回退，也没有新读回证据可重新断言当前板上身份；今后板测仍须用户单独明确授权。
