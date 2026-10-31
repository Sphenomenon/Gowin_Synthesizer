# M／W DEMO 第一阶段：实际源码与离线闭环

日期：2026-10-31；工作树为 `/Users/sphenicidition/.codex/worktrees/dual-138k-workstation/Gowin_Synthesizer`，分支 `codex/dual-138k-workstation`。本阶段确认维护源码、显式配置和离线闭环；整机 P&R、可部署位流、实板声画和手机无线验收尚未完成，T2-D1／D2 保持未勾选。

## 来源和保全

从双板已提交起点 `ee822b4` 合入单板已提交终点 `bb0da7f193de3aa7a940850c0525ee49d75577d7`，包括 `dc37783`、`46f26f2`、`32e7353`、`bf5efd0`、`bb0da7f`。复用 E8 oscillator、音频复位／CDC、DDR 分 lane、显示有效性和切率修复。没有复制单板工作树的未提交 `task.md` 或其后新增的其他未提交实现，没有更改其分支、进程或源码。原 profile JSON 与 `bb0da7f` 的字节一致，本轮只新增两份 DEMO 锁，不以刷新历史配置掩盖维护源码漂移。

生产入口继续是 `usb_a/build.py --prepare-custom-board --workstation-profile <name> --netlist-dir <locked-netlists> --custom-board-output <new-dir>`。两份 DEMO 通过已有 builder 和维护 `rtl/workstation/` 装配，没有复制工程、修改冻结 baseline／vendor，或引入另一编号生产 builder。新配置锁住实际维护源；缺少 include、哈希变化或错误约束仍拒绝。

| 配置 | 实际装配 | 本阶段差异／后续 |
|---|---|---|
| `custom138k-workstation-m-demo-v1` | 普通 A/B/C、vector、32 声部及 ADSR、完整效果、双率 I2S／最终 PCM、USB Host／Push／25K、TF、完整 HDMI 分析与绘图 | BLE／录音、本地短录音和 cue 退出。基础 revision 暂不含 CNN；后续以独立身份恢复 CNN／指导，并复验资源及实板功能 |
| `custom138k-workstation-w-demo-v1` | 真实 AE350 Classic／SBC→PCM owner→同一完整效果链→I2S／最终观测→完整 HDMI；USB Host／25K；唯一 BLE raw DDR 录音对象 | 普通／vector／声部引擎、TF／CNN、Push 专属、R00 后端、本地短录音／cue 退出。保留真实 Host 和 25K 必要反馈；旧后端 APB 拒绝访问 |

W 使用明确的 `ae350_worker_session_classic_runtime_v1`。配对为 NoBonding 会话策略，经过真实认证、加密与 key size 门后才开放媒体，断开清除会话 key；默认持久 GeneralBonding 仍 fail closed。没有伪造持久 key store 或写 Flash。持续 PCM 接口只在 D-only 角色启用；其长期 SRC 离线验证与无线、吞吐、routed 时序和硬件验收分开记录。

## 已通过的离线证据

- 维护音频：D-only 2292 个 native render 帧；48k／44.1k dry 逐位、Crush／Drive／Send 与完整七种效果组合、USB lifecycle 后恢复。退休接口 27 次读和 27 次写均拒绝，FFT 128 bin 与上下文保留。默认完整效果 14 项、Delay 13 项通过。
- 持续 PCM：`sim/test_ae350_pcm_owner.py` 8 项通过。48k／44.1k × ±2000 ppm 各 576000 帧，独立双声道插值参考、jitter 与 0／1／2 帧消费步进；日志在本机 cache `pcm-owner-long-drift-v1.log`。这是离线持续实现验证，不是实测蓝牙延迟或吞吐。
- USB：W 三项、原 GW25K／Push／generic／hotplug、PL 指导 85 events、固件 stage 七项通过。W RV32I Host 固件 19204 bytes，保留 HS／合法 FS、枚举和 PL 线规；Push 专属分支由 W 显式退出。
- 安全与媒体：默认安全 15624 checks、会话策略 1175 checks，native＋ASAN／UBSAN 和 30 个变异负控；Classic runtime 11 组真实 SBC 向量，native＋ASAN 各 3467 checks，15 个变异负控。证据目录 `/tmp/dual138k-classic-security-session-v2`、`/tmp/dual138k-classic-runtime-session-v1`。
- HCI 会话策略：[定向报告](DUAL138K_HCI_SESSION_POLICY_20261031.md) 记录实际邮箱／H5 路径默认和 W 各 1293 例（40636／40666 checks），exact ClassOfDevice／scan3 只在 W 允许，5 个行为变异拒绝；原 native 集成 268 checks、11 负控及 lint 通过。后者使用 `skip-uart/skip-prior`，不增加 UART 或硬件验收范围。
- CPU／BLE 唯一录音：[独立报告](WORKER_SINGLE_RECORDING_20261031.md) 和随仓库摘要记录 1765 checks、136 条 wire 全等、15 负控，STOP 等待实际 native DDR 提交；不是两个后端之间复制录音。
- HDMI／实际参数：[真值报告](DUAL138K_HDMI_UI_TRUTH_20261031.md)。只读 `0x1b8 EFFECT_STATE` 反馈真实顺序／count／master，不挤占旧 options／pitch；实际采样率从唯一时钟服务读取。M／W 数字 glyph、越界和撕裂、PANIC、48k／44.1k、分析区不覆盖及 ASAN 通过。完整 runtime 回归同时得到 1078 个物理序列帧、1077 个显示元组、384 FFT bins、1082 APB 事务；默认服务 1112 事务通过。
- 来源与门禁：`test_current_workstation_sources.py` 17 项；新退休约束策略 4 项；DEMO 审计 9 项与既有物理实现工具 22 项通过。退休只移除角色不存在的端点，混合查询保留全部活端点；综合审核再证明退休 selector 为零匹配。可见活 selector 必须全部解析，加密 DDR 内部另等真实 routed VO／STA。
- 手机端：[App 构建报告](../../../../../clients/android/docs/DEMO_D1_20261031.md)。新增 SAF 真实文件／MediaPlayer／实际 A2DP 路由、进度和前台播放；可与 BLE 参数、录音下载并行，退出到后台／丢焦／路由失效则暂停。73 项执行通过、2 项真实硬件测试跳过，APK 构建和 lint 通过；模拟器与真实手机无线另验。

## 固定候选和真实综合状态

候选输出均位于本机 `/Users/sphenicidition/.cache/gw138k-dual-20261031/`。`integration_inputs.json`、`workstation_profile.json`、固件 ELF／ROM 和所有 stage 输入 hash 固定每个候选；失败目录保留，不能在原目录改输入后继续沿用身份。

| 输出目录 | 固定候选身份 | 状态 |
|---|---|---|
| `m-demo-base-v3` | `custom138k-workstation-m-demo-v1-46e85b925c30374a` | 较早完整综合完成：LUT 51763、ALU 12621、FF 45982、综合 BSRAM equivalent 195、SSRAM 141；DSP 分类 MULTALU27X18=34、MULT12X12=4、MULT27X36=42。旧 SDC 尚有已退休 BLE／cue 端点，门禁拒绝；不改写它，也不作为可部署身份 |
| `m-demo-base-v5` | `custom138k-workstation-m-demo-v1-47d2966d7ee9ccb8` | 全量综合及严格网表门禁通过：LUT 51765、ALU 12621、FF 45983、综合 BSRAM equivalent 195、SSRAM 141；完整 32 声部真存储、声画／效果／USB／TF 保留。已用 UserCode `D2103101` 启动独立 P&R，尚无 routed 结论 |
| `w-demo-d-v2` | `custom138k-workstation-w-demo-v1-21f03c6e6af42daf` | prepare 通过；真实综合发现 ClassOfDevice 检查访问第六字节而旧 header cache 仅五字节，拒绝为失败。维护源码已扩为六字节并新建 v3；不把日志里的 finish 字样当成功 |
| `w-demo-d-v3` | `custom138k-workstation-w-demo-v1-37ec22429e9621d2` | 已修 header cache，全量综合完成：LUT 59927、ALU 20119、FF 43811、综合 BSRAM equivalent 257、SSRAM 307；MULTALU27X18=9、MULT12X12=2、MULT27X36=29。严格网表门禁进行中，尚无 P&R／位流结论 |

M v5 ROM SHA256 `9114a7d51b6511ed4bd778401796b590fd746103753669414302abd2e9e6d0e0`；W v2 ROM SHA256 `34beeb9e54a6df99505aed8123b6a51242f0b9d905359b7fc16893b5feaab985`。W 实际 UI ROM 构建 93600 bytes、ILM 52064、DLM 静态 7616、完整回调保守峰栈 2176／16384；166 个 actual JALR 与四个审计负控。机器站点按实际 compiler SHA 选择，未放宽默认历史审核。

W v3 之后的定向 HCI 回归另发现 Icarus 对函数隐式读取 header／length 的连续赋值依赖更新问题，维护实现改为显式输入参数；后续新候选重建，不修改 v3 stage，也不沿用其身份。上述数字都是实际综合测量，不是物理 BSRAM 数、时序闭合或预记的资源收益。

W v3 网表核对还发现旧 Classic PCM SDC 的 generate 层级与实际 Gowin 网表不一致，以及已退出的 Push／playlist／settled 查询。门禁据实拒绝进入 P&R；下一候选须显式修正真实 D PCM 的 held／session／reset 约束并证明退休查询零端点，不能删除必要 D 路径或忽略缺失。W 25K 的 112 个实际参数反馈位、邮箱身份／audio→USB 时钟和 req／ack 已核实，未消费的 Push valid 状态单列退休。

W 唯一录音仍受原 16384 帧／65536 bytes（48k 约 0.341 s）容量限制，长录音和 44.1k 格式还未实现。没有将其记为最终录音下载交付。CAM／YOLO 无新模型／实测，不阻塞首批声画。

## 物理操作与下一阶段

本轮已只读确认 Mac FT2232 channel0／USB location 8257，ID `0x0001081B`，读取型号 `GW5AST-138C`、UserCode `0xC11028E5`、status `0x00022020`。8258 是同一 USB 设备的另一个接口，读回全 `FFFFFFFF`；不是第二块已连接 FPGA。当前没有执行 SRAM 下载、没有生成已接受的新位流，也没有写 Flash。

下一阶段按真实综合网表逐项验证资源、32 声部与专属模块保留／退出，再以独立 UserCode 完成 P&R、routed STA／CDC／PLL 和功能门禁。随后利用已授权 SRAM 操作验证同一完整候选的真实 USB／25K、HDMI 与 DAC；手机必须以真实 A2DP 连接 W，连续流经 D 和效果链，并与唯一对象录音／BLE 下载共存。单板分时与双板并发分列，未通过项不预勾。
