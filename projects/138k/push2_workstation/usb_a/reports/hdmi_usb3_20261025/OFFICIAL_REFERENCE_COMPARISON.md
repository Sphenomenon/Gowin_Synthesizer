# 官方底板已显示版本与 USB3 诊断对照（2026-10-25）

## 基准身份与结论边界

本次不是仅查看通用 HDMI 示例，而是核对仓库中具有用户实际显示反馈的旧工作站。2026-09-08 的[板测记录](../../../results/workstation_20260911_174045_306332/Prj1/docs/evidence/com26_video_pll_init_20260908.json)记录：用户手动 SRAM 下载后按 S3，确认稳定项目画面、1920×1080/60Hz 及演奏可视化。记录绑定的候选位流 SHA256 为 `2ba120fe5d3d636859eb8ba593d7eea28b2a7e34aeb4c1c3ce0d69a62594d58d`；这是历史用户下载报告，不是本次对旧板执行了位流读回。其[构建输入证据](../../../results/workstation_20260911_174045_306332/Prj1/docs/evidence/build_evidence_video_pll_init_20260908.json)绑定相同位流，并包含各视频输入的哈希。

实际源码从锁定 `accepted_full83` 基线读取，描述清单 SHA256 为 `9bc6482b5885b9bc635d5089589e62aad6adf182a1822e2945a54be024c12717`；逐项再次匹配上述历史构建输入，不把历史 results 树当作新的生产输入。

当前比较对象是已经下载过的 `C11025D2` 最小彩条诊断，其位流 SHA256 为 `b4e0141f1d8ca757588715efab536d8998e8e7dd2c1d628ae4ac77deb2fadcc1`。用户反馈其仍无信号。本轮没有重建整机、生成替代位流或操作板卡，未证明当前硬件损坏，也尚未找到无信号根因。

## 逐项核对

以下五份当前编译输入与旧已显示版本的构建记录逐字节一致：

| 输入 | SHA256 前 16 位 |
|---|---|
| `src/platform/reset_release.v` | `b5d153b9b0660e3e` |
| `src/platform/video_clock_1080p.v` | `e7b3737f377d8a92` |
| `vendor/sipeed_dvi/video_pll_1080p_gw5a.v` | `0807a7d45aa095e3` |
| `vendor/sipeed_dvi/video_pll_init.v` | `ca1e667fe6f5e9c6` |
| `vendor/sipeed_dvi/dvi_tx_tmds_enc.v` | `1be5a5e3fbb785ad0` |

因此两级 PLL 的实际配置、官方初始化 helper、锁定资格／停钟启动序列、像素域复位模块及 TMDS 编码器均未被替换。两版都使用 50MHz 输入、名义 49.5MHz 参考级、742.5MHz 串行 FCLK、专用 CLKDIV `/5`；不能仅凭源码或 STA 声明推定本板确实锁定且达到这些频率。

### 光栅

当前 `video_timing_1080p.v` 仅经过既有 `workstation_resource_timing.raster()` 的 vblank 组合译码寄存化变换。新增回归以冻结原版为参考，逐周期比较完整 2200×1125 一帧的全部 29 个输出位，包括像素坐标、DE、HS、VS、帧／行／vblank 标记，以及复位后的重启；全部相同。另检查有效区共 1920×1080 像素、VS 共 5 行、vblank 标记每帧一个像素。因此这次变换不改变实际光栅输出序列。

### 串行器与输出电气配置

旧版三份 `dvi_tx_top.v`、`dvi_tx_tmds_phy.v`、`dvi_tx_clk_drv.v` 也匹配历史构建哈希。当前使用原生封装 `workstation_custom_dvi.sv`：保留同一官方编码器、四个 OSER10、直接 ELVDS_OBUF 输出及同一 D0–D9 次序，在 OSER10 并行输入之前增加四路 XOR，补偿新载板 P/N 交换，不在串行输出后插入 fabric LUT。

原版与当前反接线缆版各通过 9 个官方原语启动／相位场景和独立 RGB 参考解码；四个逐路撤销补偿的负向对照均按预期失败。这些只验证数字位序／相位与补偿逻辑，不是 FPGA 管脚或插座处模拟波形、幅度与眼图验收。

两版 TMDS 球位均为 `J14/H14`、`J15/H15`、`K17/J17`、`G15/G16`，IO 配置均为 `LVCMOS33D`、DRIVE=8；未发现偷偷切换到 TLVDS 或改变通道次序。

### 必须保留的板级差异

- 官方底板 `K14=hdmi_tx_en` 恒为 1；新载板 K14 经 R21 接 CEC，应保持高阻。新载板 HDMI +5V 走 R46，不是 K14 使能，不能原封不动烧旧整机来“恢复 HDMI”。
- 新载板四对 P/N 与官方原生输出顺序相反，所以当前增加四路并行字极性补偿；不能通过非法交换原生差分对球位代替。
- 原版接 `button1_n/AB13`，历史成功观察是在按 S3 后得到的。当前诊断把外部复位输入固定为 1，不接 S3，但同一 `reset_release` 的 1024 周期上电延时仍在；实际路由网表保留 35 个该模块触发器，INIT 均为 0、时钟均为直接 50MHz。因此不能说诊断“没有复位”，也不能把它当作已经复现了旧版的手动 S3 重启条件。
- 当前直接生成彩条，不依赖 DDR、渲染或 CPU；HPD 仍只观测，不门控视频。缺失业务帧缓冲不应直接解释此探针的无信号。

### 时序约束差异不等于硬件时钟改频

旧 SDC 用 `-divide_by 5` 声明像素时钟，当前用 `-edges {1 7 11}` 描述实际 CLKDIV `/5` 的 60/40 波形；另外只有基本时钟数值格式和显式 `-divide_by 1` 等差异。两份 SDC 不是逐字相同，但上述物理 PLL／CLKDIV RTL 字节没有改变。保留这个分析波形修正，不能改回旧约束冒充显示修复。当前探针原始 recovery 负值及其有限范围启动审计仍按原报告保留，不宣称全时序闭合。

## 验证与证据

- `sim/test_hdmi_usb3_diagnostic.py`：3 项通过，包括新增的整帧光栅对照、彩条／消隐／状态字符覆盖及输入范围检查。
- `sim/test_workstation_custom_board.py NativeBoard.test_reversed_tmds_cable_with_official_primitives_and_independent_rgb_reference`：通过，包含原版、补偿版和四项负向对照。
- `sim/test_current_workstation_sources.py`：10 项通过；未修改 accepted 输入、冻结基线、PLL、IO、原生顶层或当前位流。

相对 `usb_a/` 的输出证据：`out/hdmi_usb3_diagnostic_20261025_c11025d2/official_reference_comparison_20261025.json`，SHA256 为 `d823ad91afb36b2dd4b54dfdd58ec71b638c177473fddf2c59df3ca62b58f9dc`。其中包含完整输入／历史板测证据哈希、复位初值、时钟声明差异和回归用例；串行器原始日志在同一目录的 `official_comparison_tmds_20261025_01/`。

## 下一项有效判据

目前缺少本板运行态，不能从 JTAG UserCode 或“无配置错误”推导 PLL 已锁定。现有诊断已每秒从 **FPGA 球位 U15 的调试 TX** 输出 115200 8N1 文本，不需要重综合即可读取；U15 是球位，不是底板同名稳压器的器件位号。

启动稳定后，`H3D1 xxxx` 的 bit0 表示资格化视频时钟已启用、bit1 像素域复位释放、bit2 串行器复位释放、bit3 HPD、bit4 最近报告周期内检测到像素时钟活动。持续 `001F` 表示这五项均成立，但仍不测量像素时钟的准确频率和外部 TMDS 波形；持续仅 `0008` 则表示只有 HPD、视频时钟启动链未起来，应回查启动与 PLL，不能继续把故障笼统归为显示器或 PCB。

应先确认这根调试 TX 的实际连接并读取状态，再决定是做手动复位条件对照，还是检查连接器处时钟／输出电气。不把当前源代码对照通过当作显示已恢复，也不在没有新证据时再次全量重综合或改写 Flash。
