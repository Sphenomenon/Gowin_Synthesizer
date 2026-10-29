# F02 revision 2：固定输入布局布线与失败门禁

日期：2026-10-30（Asia/Shanghai）。固定 `3d4b3175d0f20d0b787b61b43e4543739b26bca1` 候选完成真实 P&R 并产生新 UserCode `0xC11030F2` 位流；**整机物理门禁失败，未成为可部署候选。** 全局 setup −1.867 ns、hold −0.910 ns；audio／USB 频率要求未满足；common CDC 通过，PLL／routes 门禁仍失败。本轮未操作硬件，未下载 SRAM，未写 Flash。

机器记录：[f02_physical.json](workstation_task_20261030/f02_physical.json)，保留全部 913 条详细负路径、各 checker 原始结果／退出码／失败文本、资源与证据哈希。此前 [F02 综合报告](WORKSTATION_F02_SYNTHESIS_20261030.md) 仅对应综合阶段；[采样率 DSP 审计](WORKSTATION_SAMPLE_RATE_DSP_AUDIT_20261030.md) 另列运行时 44.1 kHz 缺口。

## 固定来源与实现选项

使用 detached 干净克隆 `/Users/sphenicidition/.cache/gw138k-task-20261030/clean-rev2-3d4b317` 自身工具；审计结束 `git status --porcelain` 为空。父候选 `/Users/sphenicidition/.cache/gw138k-task-20261030/clean-rev2-profile-candidate` 是 profile revision 2，authoritative 身份 `custom138k-workstation-v1-f5b723250388add5`，底层 a26 装配身份仅为来源。本轮独立物理身份为 `custom138k-native-physical-C11030F2`，输出保存在 `/Users/sphenicidition/.cache/gw138k-task-20261030/f02-physical-C11030F2`。

通过现有 `tools.workstation_custom_board_implementation` 从已审计综合网表 prepare，参数为 `--user-code C11030F2 --acknowledge-electrical-risk --ulpi-bypass-lvcmos33`。首个命令缺少 PYTHONPATH、在 prepare 前失败；配置正确模块路径后正常执行，未绕过输入审计。

实际 `gw_sh run.tcl` 使用 Gowin **V1.9.12**，器件 `GW5AST-LV138PG484AC2/I1` version C、place=2、route=0、resource replication=0。开启 timing_driven、correct_hold_violation、text timing report、SDF、Verilog 仿真网表；MSPI／CPU pads 为 user GPIO；bit security／encryption／compression／secure 均关闭。保持原始 SDC、全部特性和实际时钟，不增加 false path 或放宽频率。04:38:18.516 至 04:53:26.738，wrapper 约 908.221 秒；工具报告实现 elapsed 871 秒、CPU 827 秒、峰值内存 2933 MB。运行全程持有 `/private/tmp/gw138k-build.lock`，结束后已验证释放。

唯一 CST 适配是 12 个已有 ULPI 端口的名义 `LVCMOS33` 声明，位置不变，范围仅对应 U4/U5 bypass 的 nominal 3V3 实验假设。原 CST SHA256 `13440c753db683b2bcab509068dd5b3d3ffe652f37befc9b9eaf30780ab70920`，适配后 `3dc6efebc9a004ef71566abb5e17b2d8c3c5d4869a26511b9e3dbf5972b8cb6a`；SDC 为 `bfcf675d98f07dbcb51eaedfa554b59e14b3f9efca0c2b66822e774ef5198354`。全部 physical 输入在运行后哈希不变。prepare 的风险确认只允许离线实验，不证明实际旁路电气或外部 IO timing 已验收。

| 产物 | SHA256 |
|---|---|
| 实际综合网表 | `27b30ac791323f05dc68cd5d9ea6ccaaf14d6a122c5fe2b978cb4714b7fdcf18` |
| physical_inputs.json | `34d82f780370c2e7b9b8bba071bb59ac77565e800205feca00db6139fa5c026c` |
| P&R log | `8b040cad081e8f52fd55713b79d09a884dc7e21a6c179c2c07481c98884250ac` |
| 正式资源报告 | `c934ab61b8f92f4d919968ca86299146bcf6d08ffd0e306cf7db734014fe032f` |
| routed timing HTML | `ff636627211797eba8f1e3d3922b6401d68c406c6897fd9dfcef55d18b87f09e` |
| .fs | `dfb61b2417a5bd9ecd35fce7922c6294bfd78d8d22a32a45c79a3fb673ca429e` |
| .bin | `f32eed7fad1ca2f51c00ead6e48e112875e1a9c61851c99af0656564dd29f7e3` |

`.fs` 的 `//UserCode: 0xc11030f2` 和 `device.cfg` 的 `set user_code = 0xC11030F2` 均已读回核对；这是本地产物身份，未做 JTAG 身份读回。generated 位流、实现数据库、VO／SDF 等全部保留在忽略的外部实验目录，不加入源码变更。

## 实际物理资源

| 资源 | 实际 P&R |
|---|---:|
| Logic | 92,251 / 138,240 |
| LUT／ALU／SSRAM | 73,562 / 16,175 / 419 |
| Register | 55,571 |
| CLS | 60,596 / 69,120（88%） |
| BSRAM | **309 / 340（91%，余 31）** |
| BSRAM primitive | SP 3、SDPB 219、SDPX9B 35、pROM 45、pROMX9 7 |
| DSP | 156.5 / 298 |
| MULT12X12／MULT27X36／MULTALU27X18 | 41 / 45 / 46 |
| IO Port／IOLOGIC | 142 / 297、105 / 285 |
| AE350_SOC | 1 / 1 |

综合的等效 BSRAM=272，与本轮实际物理数 309 不同。本次没有 GAO，不能套用历史 C1 的 318/340，也不能把 272 当作实际剩余容量。P&R tool rc=0、生成位流，但不代表时序或验收通过。完整 P&R log 有 1 条 PR1014：`clk_50m_d` 使用 generic routing clock resource，可能增加延迟／skew；没有 ERROR／FATAL。

## 冻结门禁结果

按顺序执行固定克隆的 `reports/workstation_physical_20261025/check_timing.py`、`check_pll.py`、`check_common_cdc.py`、`check_routes.py`，原检查器和阈值均未更改。

| 门禁 | 结果 | 证据／失败 |
|---|---|---|
| routed STA | FAIL，rc=1 | audio／USB Fmax 及 audio／USB／DDR UI setup 负端点；详细负路径 |
| PLL／startup | FAIL，rc=1 | 正确 simlib 后仍缺精确历史单元名 `…/pll_stop_s0`，startup coverage 未完成 |
| common CDC | PASS，rc=0 | 18 gray buses、5 levels，errors=[] |
| native routes | FAIL，rc=1 | model readiness synchronization flight 2.038 ns > 2 ns |
| a26 DDR hold 独立补充 | FAIL，rc=1 | 拓扑／0.800 ns 约束存在，但该精确 hold STA slack=−0.910 ns |

PLL 首轮未设置 GOWIN_SIMLIB，DDR configuration 子审计无法找到模型；该环境失败及 stderr 均保留。补设实际安装目录 `/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/simlib/gw5a` 后重跑相同 checker。DDR reset 四场景、108 个 reference cells 通过；configuration 的 620 ns STEP freeze、512 HOLD truth-table cases、32 WSTEP pipelines、两套官方 PCLK models 通过。四组 shared PLL 控制传播上界分别 audio 5.999 ns、USB 6.823 ns、CPU 7.109 ns、LCD 5.914 ns，均低于原 10 ns 限制；这些子结果不能抵消整体 startup 失败。

缺失名对应的实际 VO 单元是 `LUT1 …/pll_stop_d_s0`，`INIT=2'h1`，输出 `u_memory/pll_stop`。目前仅确认名称和局部连接，未修改 frozen checker 或用改字符串把它报成成功。若后续在版本化 checker 支持两种命名，必须完整核对驱动、扇出、极性、reset／停止窗口及负向控制，原失败记录保持。

### Routed STA 数值

| clock | 要求 MHz | 报告 MHz |
|---|---:|---:|
| clk_50m | 50 | 50.487 |
| ULPI | 60 | 79.851 |
| DAC reference | 12.288 | 77.102 |
| audio | 76.8 | **72.236** |
| LCD pixel | 31.5 | 40.302 |
| USB | 48 | **47.227** |
| DDR memory | 400 | 2338.897 |
| DDR UI | 100 | 180.456 |
| HDMI pixel | 148.5 | 163.907 |
| CPU RAM | 50 | 85.062 |
| CPU core | 100 | 1192.605 |

Fmax 数值不是所有跨钟／特殊 pin 路径的替代。全局 setup −1.867 ns、hold −0.910 ns、recovery 3.383 ns、removal 0.278 ns；pulse width 最小 0.583 ns，无 pulse width 违反。audio 有 781 个 setup 负端点、TNS −285.705 ns；USB 11 个、TNS −3.748 ns；DDR UI 116 个、TNS −44.802 ns。

### 关键路径及可修改归属

| 路径 | slack／检查值 | 归因与下一步范围 |
|---|---|---|
| DDR `read_rclksel_conf_3/Q` → lane3 DQS `HOLD` | setup −1.867 ns；data 8.326 ns、skew 3.089 ns | opaque vendor 内部；只在独立物理适配／放置约束处理，保留 vendor bytes 和完整检查 |
| engine ADSR attack ROM DO → envelope_level 写回 | setup −0.823 ns，data 13.783 ns | 实际锁定 `legacy/rtl/audio/unified_oscillator_engine.sv`，不是活动同名文件；需要显式版本化迁出或严格锚定 pipeline 适配 |
| guide read_index → lights value/index CE | setup −0.341 ns，data 20.927 ns | `rtl/push2/push2_score_guide.sv` 与 `push2_lights.sv`；可在适配端寄存有界交付，保留消息／LED 行为 |
| DDR `ddr_init_internal_r/Q` → `wloadn_3/D` | hold −0.910 ns；relation 0.800 ns、skew −0.454 ns、data delay 0.392 ns | 原 SDC min-delay 0.800 ns 保留；新候选未请求历史 C1 wloadn floorplan，独立布局适配需实测 |
| `u_music/model_memory_meta/Q` → `model_memory_ready/D` | data flight 2.038 ns > 2 ns | `rtl/music/basic_pitch_workstation_link.sv:58–63`，已有 ASYNC_REG；保留两级、单消费者同步，改物理邻接，不能放宽门槛 |

audio 的 781 条详细负路径中，destination 在 engine 587、vector 132、effects 43；后续不能只修单个 envelope worst path 就宣称域已闭合。DDR UI 还包括 display descriptor／renderer 数据路径，如 `global_q_240/Q→desc_ok_q/D` 的 −0.813 ns；新原生 HDMI 迁出需重新验证其影响。

当前活动 engine SHA256 `34554bb3bdb30dab68e35769ebaa333b2ed4c98833caec369b71aec85b34d967`，实际 staged engine 为 `7afb67e8b92828b50e42fbdfa259bf5c5ec0b39d1104bc263c5072e93067859e`（locked parent 后执行 native voice_controls transform）。未来应把稳定改动迁到版本化源码并显式改变输入身份，不能修改冻结 baseline 或声称活动文件编辑已自动作用于本轮候选。

### a26 DDR hold 覆盖补充

冻结 routes checker 只在 inherited identity 以 `-a23` 结尾时记录上述 DDR hold 路径，本候选 a26 不进入分支。独立只读脚本 `/Users/sphenicidition/.cache/gw138k-task-20261030/verify_f02_ddr_hold.py` 验证：launch／capture 为 DFF、Q→D 直接相连、launch 来自 DDR_UI_CLKDIV4、capture 来自 direct clk_50m，原 0.800 ns 约束精确存在。SDF 的 cell CLK→Q 加 route 为 0.708 ns，**该值不能替代含时钟 skew 的完整 STA**；精确 endpoint 的 hold slack 已确认 −0.910 ns，补充门禁明确失败。没有以 a23-only 分支跳过当作通过。

## 状态与回退

本轮完成 source/synthesis、offline P&R、位流生成与离线失败归因；`timing_closed`、`physical_gates_passed`、`hardware_verified`、`deployment_allowed`、`release_ready` 均为 false。实际 ULPI 电气、完整外部 IO timing、FPC 音频、HDMI、BLE 与外围验收仍未完成，未继承任何历史候选的实板身份或验收。

当前板卡、SRAM、Flash 均未改变，accepted profile 未改指向。回退依据是固定 commit、保留的父候选和本轮精确产物；后续源码／约束改变必须新建候选身份、重新综合／实现与审计，不能重用 C11030F2 冒充改变后的 release inputs。
