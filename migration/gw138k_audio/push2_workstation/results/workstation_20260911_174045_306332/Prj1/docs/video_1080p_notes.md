# 1080p60 显示时钟与扫描约定

本轮目标为标称 **1920 × 1080、逐行、60.000 Hz**。时钟来自核心板 Y1100 / V22 的 50 MHz 基准，经两级 PLL 得到 148.5 MHz 像素时钟和 742.5 MHz 串化时钟。频率计算不使用近似的 148 MHz，也不依赖 MS5351 的上电配置。实际频率仍继承板载晶振误差；逻辑仿真和布局布线通过不代表已测量板上的刷新率或 TMDS 信号质量。

## 官方资料核对

以下页码为手册印刷页码，括号内为 PDF 文件页码。

| 资料 | 本设计用到的依据 |
|---|---|
| [DS1239-1.0.3 GW5AST 数据手册](../../../Doc/GW官方/DS1239-1.0.3_GW5AST系列FPGA产品数据手册.pdf)，表 3-16，42 页（PDF 51） | GW5AST-138 OSER10 最高 IO 逻辑串行速率为 1600 Mbps。1080p60 的每条 TMDS 数据通道为 1485 Mbps。表下注明实际速度由具体 IP 决定。 |
| 同手册，表 3-18，43–44 页（PDF 52–53） | C1/I0 和 C2/I1 的 PLL PFD 范围均为 19–81.25 MHz，VCO 为 650–1300 MHz，输出最高 1000 MHz。两个 PLL 都满足这些范围。 |
| [UG306-1.0.9 时钟资源用户指南](../../../Doc/GW官方/用户指南/UG306-1.0.9_Arora_V时钟资源(Clock)用户指南.pdf)，35–36、40、50–51 页 | PLL 反馈 MDIV 支持 1/8 小数；ODIV0 的小数部分仅在整数部分 2–127 时有效；LOCK 必须连续稳定至少 2 ms 才能判定锁定。输入稳定后必须复位下一级 PLL。 |
| 同指南，24–26 页 | CLKDIV 为专用 HCLK 分频资源，支持 DIV_MODE = 5，输出与输入保持相位关系；RESETN 是低有效异步复位输入。 |
| [UG304-1.3.7 GPIO 用户指南](../../../Doc/GW官方/用户指南/UG304-1.3.7_Arora_V可编程通用管脚(GPIO)用户指南.pdf)，101–102 页（PDF 111–112） | OSER10 依次发送 D0 到 D9，PCLK = FCLK / 5；沿用现有 Sipeed TMDS 编码与 ELVDS 输出平台。 |

1600 Mbps 是 IOLOGIC / Gearbox 的器件能力上限，不是该 Dock、ELVDS 电阻网络、线缆和显示器组合已经通过 HDMI 电气规范的证明。1080p60 需要在目标板上检查稳定显示、闪点/掉帧及必要的信号完整性。HEADPHONE 音频输出链路不使用 HDMI 音频包；当前视频发送器工作于 DVI 兼容模式。

## 精确频率方案

| 级别 | 输入 | IDIV | FBDIV | MDIV | VCO | 输出 |
|---|---:|---:|---:|---:|---:|---|
| `u_reference` | 50 MHz | 1 | 1 | 24 + 6/8 | 1237.5 MHz | CLKOUT0 / 25 = 49.5 MHz |
| `u_tmds` | 49.5 MHz | 1 | 1 | 15 | 742.5 MHz | CLKOUT0 / 1 = 742.5 MHz |
| `u_pixel_div` | 742.5 MHz | — | — | — | — | 专用 CLKDIV / 5 = 148.5 MHz |

源码为 [video_clock_1080p.v](../src/platform/video_clock_1080p.v) 和 [video_pll_1080p_gw5a.v](../vendor/sipeed_dvi/video_pll_1080p_gw5a.v)。两个 PLL 不设置固定物理位置，由项目 PnR 结合 DDR 的专用 PLL / HCLK 位置分配。第二级只输出串化时钟，其专用 HCLK 的 CLKDIV / 5 产生像素时钟，保持 OSER10 所需 FCLK/PCLK 相位关系。

每一级先经过当前官方 `video_pll_init` 的ICP/LPF搜索，原始LOCK只有在helper完成时才经O_LOCK放行。两个初始化器均使用稳定的50MHz参考、CLK_PERIOD20；MULTI_FAC24与24.75属于相同表分档，第二级为15。每一级O_LOCK再在50MHz域同步并连续检查100000周期；任何失锁立即清除稳定标志。第一级稳定前，第二级保持 RESET。像素域和系统域分别在各自时钟上同步释放 4 级复位。不能将视频 PLL 的 lock 与 DDR 校准完成混为一个状态；DDR 校准和帧可读性由显存控制模块另行判断。

两个 PLL 通过资格检查后，`video_serializer_startup` 先释放 CLKDIV 的低有效复位和 OSER10 的高有效复位，再等待四个完整 50 MHz 周期（80 ns），最后通过 PLL2 原生 `ENCLK0` 打开串化时钟。UG306 的 ENCLK0 是动态输出使能，静态 CLKOUT0_EN 保持 TRUE。像素时钟也随该门控停止；像素逻辑仍在启钟后继续保持复位四拍。失锁或外部复位会关闭输出、重新断言复位，下次必须重新完成 PLL 资格检查和 80 ns 等待。PHY 复位直接连接保留的 50 MHz 域寄存器，不再在像素时钟上重寄存，也不把 742.5 MHz 引到逻辑阵列做复位同步。

Gowin 1.9.12.03 对初始化 RESET 的 `set_max_delay` 可能显示约束 active，但不报告实际路径，集成设计中的 CLKDIV 和 DDR PHY 也出现了这种情况；不能把空报告视为零延迟。SDC 因此只对已审计的停钟复位入口设置精准例外，40 ns 传播预算由构建检查器读取布局后的 `.vo` 和 `.sdf` 独立执行。检查器核对五级启动链、PLL.ENCLK0、CLKDIV 和四路 OSER10 的实际连接，并逐路累加输入缓冲、50 MHz 时钟布线、源寄存器 C2Q、RESET 布线和恢复时间，要求总计不超过 40 ns。DDR 另外核对原 IP 与控制序列的哈希、PLL.ENCLK2 和全部 101 个 PHY RESET 端点。80 ns 启钟窗留出另一半余量；所有正常像素、TMDS 和复位分配路径继续按正常时钟检查。

独立 `build/serializer_startup_probe` 的路由 SDF 给出三路 RESET 最大布线 2.983/2.983/3.368 ns；加上输入缓冲 0.532 ns、源时钟布线 3.869 ns、C2Q 0.275 ns 和恢复时间 0.119 ns，最差总计 8.163 ns，距启钟至少 71.837 ns。该数字只是探针结果；正式构建必须由 [check_serializer_startup.py](../scripts/check_serializer_startup.py) 对自身的路由产物重新计算，并将 SDF/VO 哈希随证据保存。

2026-09-08 13:45:44 的首个集成路由产物已通过完整时序及独立复位分配审查：setup/hold 违例均为零，详细报告最小 slack +0.136 ns、最小脉宽 slack +1.325 ns。复位审计包括上述 105 个端点以及 8 个受同一停钟序列控制的 UI 负沿校准寄存器 CLEAR，共 113 个；最坏分发加恢复时间 8.556 ns，距 80 ns 启钟窗口仍有 71.444 ns。检查器同时核对 SDC 例外选择集合，拒绝误覆盖 `u_dll/RESET` 等未审计路径。最终哈希和完整证据见 [验证记录](verification.md)。首版上板DDR状态正常但HDMI无信号。14:20:38第四路OSER10版本重新构建，114个复位端点审计通过（最坏8.441ns）、最小slack +0.138ns；用户重新下载后仍无信号，见验证记录。

只用一级 50 MHz 参考 PLL 时，742.5 / 50 = 297/20。合法 PFD 限制 IDIV 只能取 1 或 2，反馈的 1/8 小数精度不能在 ODIV = 1 时产生这个比值；ODIV ≥ 2 则需要 VCO ≥ 1485 MHz，超过 1300 MHz。`ODIV0 = 1.25` 也不合法，因为其小数只在整数部分 ≥ 2 时有效。因此使用两级 PLL。

`cam_dvi` 的 `TMDS_PLL_60HZ_mod.v` 采用 50 × 2 × (11 + 1/8) / 15 = 74.166666… MHz，而同目录 `.ipc` 写着期望 74.25 MHz；这里以实际参数计算为准，未复制该近似配置。

SDC 应对实际 PLL 引脚声明以下时钟关系，保持第二级 serial 和 pixel 同步分组；与 DDR UI 时钟和 50 MHz 控制域间的数据路径必须通过 CDC：

| 输出引脚（相对于 `video_clock_1080p` 实例） | 相对 50 MHz 的比值 | 标称周期 |
|---|---:|---:|
| `g_hardware.u_pll/u_reference/PLL_inst/CLKOUT0` | 99/100 | 20.202020… ns |
| `g_hardware.u_pll/u_tmds/PLL_inst/CLKOUT0` | 297/20 | 1.346801… ns |
| `g_hardware.u_pll/u_pixel_div/CLKOUT` | 297/100 | 6.734007… ns |

2026-09-08 的独立 `build/clockdiv_probe` 工程用相同 PLL、HDMI 引脚和双时钟 BSRAM 检查专用分频拓扑。该探针报告的 BSRAM 高脉宽为 2.135 ns，要求 0.776 ns，最小脉宽裕量为 +1.359 ns；旧的 PLL CLKOUT1 像素输出在首次集成报告中该项为 −1.365 ns。因此改用 CLKDIV，而不豁免最小脉宽检查。探针仍有其他时序违例，此结果仅支持时钟拓扑选择，完整设计仍需重新布局布线验证。

## DDR 扫描接口

[video_timing_1080p.v](../src/video/video_timing_1080p.v) 以可见区域左上角为计数起点，坐标也包含消隐区。输出无额外寄存延迟，均表示当前光栅位置。

| 参数 | 水平 | 垂直 |
|---|---:|---:|
| 有效区域 | 1920 | 1080 |
| 前肩 | 88 | 4 |
| 同步脉宽 | 44 | 5 |
| 后肩 | 148 | 36 |
| 总计 | 2200 | 1125 |
| 同步极性 | 正 | 正 |

`pixel_x[11:0]` 范围 0–2199，`pixel_y[10:0]` 范围 0–1124；DE 在 x < 1920 且 y < 1080 时有效。HS 在 x = 2008–2051 为高，VS 在 y = 1084–1088 为高。148500000 / (2200 × 1125) = 60；行频为 67.5 kHz。

| 标志 | 位置与用法 |
|---|---|
| `frame_start` | (0, 0)，一个像素周期；表示当前帧首像素，不提前于首像素。 |
| `line_start` | 每行 x = 0，一个像素周期；包含 45 行垂直消隐。 |
| `vblank_start` | (0, 1080)，一个像素周期；距下一帧首像素有 99000 个像素周期，约 666.667 µs，可用于首行 DDR 预取和帧边界协调。 |

复位后坐标从 (0,0) 开始，第一帧不会自动等待 DDR。显示路径需要在 DDR 初始化、帧准备和行缓存数据有效前输出黑色；不能因 DDR 忙而暂停扫描时钟/计数器。行缓存到 RGB 的读取延迟应同样施加到 DE / HS / VS，保持首尾像素对齐。若采用 RGB565，单帧占 4,147,200 字节，仅 60 Hz 扫描读取的有效数据带宽即 248.832 MB/s；渲染写入、刷新与突发开销需要额外预算。

## 集成约束审查建议

`vendor/gowin_ddr3/reference_demo.sdc` 是原示例的历史参考，其输入时钟写成 100 MHz，且将 400 MHz、100 MHz、PHY UI 三组时钟全部设为 `-exclusive`。不能原样用于本项目的 50 MHz 输入。DDR UI 实际来自 `u_ddr3/gw3_top/u_ddr_phy_top/fclkdiv/CLKOUT`，频率为 memory_clk / 4 = 100 MHz；DDR memory_clk 来自 `u_pll/u_pll_0/PLL_inst/CLKOUT2`，频率为 50 MHz × 8 = 400 MHz。当前 SDC 显式命名这两路以及视频级联三路时钟；检查器核对综合后六个时钟节点的唯一性与频率。

SDC 的 `set_clock_groups` 优先级高于 `set_false_path`，后者又高于 `set_max_delay`。依据本机 Gowin 1.9.12.03 随附的 SUG940-2.0.4 时序约束指南 37 页（约束优先级）和 69–70 页（例外语法），不能先把视频/UI 整组设为 false path 再期望局部 max_delay 重新生效；当前版本的 max_delay 语法也未列出 `-datapath_only`。

对 `video_ddr_scanout` 建议保留以下具体约束，层次前缀需按综合结果填写。`get_regs` 匹配计数应检查非零；工具可能将一位寄存器命名为 `*_s0`。

| 跨域路径 | 约束和时序依据 |
|---|---|
| `request_toggle → request_meta/D`、`ack_toggle → ack_meta/D`、`done0_toggle → done0_meta/D`、`done1_toggle → done1_meta/D` | 只对第一级 D 输入设 false path；meta 到 sync、sync 到 settled、settled 到消费者仍保留目标域 setup/hold。 |
| `held_request[*] → request_word[*]` | max_delay 20 ns；仅移除这些数据路径的假同边沿 hold。源数据与 toggle 同拍锁存，经 UI 域 meta、sync、settled 后采入独立的完整 20 位邮箱寄存器，理想最短稳定时间为 30 ns；再下一拍才解码和计算地址。数据保持到整个读行请求完成并收到 ACK。综合已核对 20 个捕获 DFFCE。 |
| `done0_tag[*] → tag0[*]` 和 `done1_tag[*] → tag1[*]` | max_delay 12 ns；仅移除数据路径 hold。像素域三级 toggle 流水加消费，最短约 20.202 ns 后才采集，标签在下一次同缓存行写完前保持不变。 |
| `under_gray[*] → under_meta[*]` | max_delay 20 ns，并仅移除 hold。缺行计数至多每条扫描线更新一次，相邻 Gray 更新最短间隔 14.815 µs；20 ns 预算小于此间隔的 1/700。Gowin 的 max_delay 包含源时钟延迟，故不直接用一个像素周期作为此项约束。Gray 转码与二进制递增分拍寄存。不要对该总线的 setup 再加 false path；`under_meta → under_sync` 保留 UI 时序。 |
| `line_memory` 的 UI 写端与 pixel 读端 | 应由真实双时钟 BSRAM 承载。确认综合推断结果，不对整个扫描模块加 false path；读端到 RGB 的流水及 TMDS 编码仍要满足 148.5 MHz。 |

若约束针对握手总线源寄存器使用宽泛目的选择器，应在报告中确认只命中这条稳定数据通路，避免误遮蔽另外的控制通路。上述预算保留建立时间余量；实际布线后的 max-delay 报告才是约束是否满足的依据。

DDR PHY 对有同步链依据的入口设置例外：Gowin 1.9.12.03 的 `simlib/gw5a/prim_sim.v` 中 IDES8_MEM 把 CALIB 经 FCLK 域 `calib_0 → calib_1 → calib_2` 采样，以 `calib_1 & ~calib_2` 产生调整脉冲；原 DDR 示例 `.vo` 的 `ddr_sync/recalib_s[0] → recalib_s[1]` 是 clk50 域同步链。SDC 仅切断 `ides_calib_d/Q → IDES8_MEM/CALIB` 和 `recalib_s[0]/D`，保留第二级与实际 DDR 数据时序。DDR IP 自身停钟复位状态机另有逐周期网表审计，具体 80 ns 窗口和 40 ns 分配预算见 [DDR 平台说明](ddr_platform_notes.md)。`wloadn_3` 只有单级 clk50 寄存器，DQS 模型对 WLOADN 有 setup/hold 要求，未用初始化名义豁免。

视频 PLL 无固定位置约束。DDR C 版 IP 的 `PLL_L[0]`、`DDRDLLM_BL`、`LEFTSIDE[4]` 等专用资源保持原平台需求；若 PnR 报 HCLK 冲突，应从 PLL 到 OSER10 的专用资源连通性定位，不应给 742.5 MHz 串化网套用允许普通布线的宽泛例外。V22 50 MHz 基准已知的普通布线说明与高速串化网是不同路径。

## 仿真与上板边界

- `tb_video_timing_1080p` 穷举完整 2,475,000 像素光栅，核对有效像素数 2,073,600、同步宽度/极性、帧/行/消隐预取标志、回绕和复位。
- `tb_video_clock_1080p` 检查理想模型的 148.5 / 742.5 MHz 和复位；另外实例化真实锁定过滤、停钟释放复位和启动流水，检查 80 ns 窗口与短失锁后的完整重新资格检查。
- 直接使用本机 Gowin 官方 CLKDIV/OSER10 行为模型的独立测试，在首次启钟和失锁后再次启钟两种情况下分别核对 50 个连续变化的 10 位字，确认 D0 到 D9 顺序和完整符号；测试源为 `build/serializer_startup_probe/tb_primitive_startup.sv`。该模型仍不模拟亚稳态、模拟 PLL 或 PCB 信号质量。
- 仿真时仅将 `video_clock_1080p.SIMULATION` 设为 1，调用 `sim/models/video_clock_1080p_model.v`。综合默认值为 0，调用真实 Gowin PLL。模型只验证数字接口，不模拟 PLL 抖动、模拟锁定过程或 PCB。
- 以上两个独立测试于 2026-09-08 通过。集成设计的综合、PnR、DDR 校准、显存读回、1080p60 显示器识别和板测证据以 [verification.md](verification.md) 的最新记录为准；本文件不将仿真结果标作已跑通 DDR 或已通过 HDMI 板测。

## 最终上板核对（2026-09-08）

15:06官方PLL初始化版 `2ba120fe…` 手动下载并按S3后，用户确认稳定显示项目画面，显示器信息页为1920×1080/60Hz；GUI正弦演奏驱动波形、峰值、声部指示，松键后回落。12次连续快照均DDR=0xCB、HPD=1、欠载0；像素块数1450/1451符合148.5MHz±0.1024MHz量化，8.625s内扫描和渲染各推进517帧。最终STA最小slack +0.138ns；PLL控制11个动态端点完整传播最大8.069ns，114个复位端点也通过独立预算审核。原始ACK、用户确认和对应位流哈希见 [验证记录](verification.md)。该次短时验收不覆盖全容量DDR压力、热插拔、信号眼图及模拟音频质量。
