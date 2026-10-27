# 2026-10-27：独立当前 UI / DDR / HDMI 调试工程

## 目标与范围

为显示调试建立小规模综合布局布线入口，不再每次构建完整工作站。
保留当前 1920×1080 UI、真实 DDR 管理和外部 DDR 往返，不使用色块替代 UI，也不直接把生成图接到 TMDS。
这是独立诊断配置，不是删功能后的整机发行版，不替换 accepted full83、timing85 或 native resource 候选。

```text
workstation_hdmi_demo（可替换输入）
 → 原有波形采集 / FFT / 立体声分析
 → display_data_writer → 原有队列 DDR 管理 → 外部 DDR
 → display_data_reader → feedback_renderer / feedback_dashboard
 → ddr_frame_writer → 原有队列 DDR 管理 → 外部 DDR 帧缓存
 → video_ddr_scanout → 原生板级 TMDS → HDMI
```

保留波形、频谱、相位图、效果卡片、文字和状态。AE350、USB、BLE、CNN、TF、合成器与 LCD 不实例化。
默认输入是 48 kHz 确定性双声道三角波，左 375 Hz、右 750 Hz；状态每秒切换。
`--hdmi-input static` 固定场景状态，仍保留周期音频观察数据。
这两种输入均可复位重放，不依赖文件、网络、真实音源或业务 CPU。

## 源身份与数据入口

- 入口：`build.py --hdmi-isolation`；实现：`tools/workstation_hdmi_isolation.py`。
- 新 RTL：`rtl/display_data/workstation_hdmi_demo.sv`、`rtl/display_data/workstation_hdmi_isolation.sv`。
- UI / DDR 使用锁定 `resource_rework_route0` 源和既有 native 时序适配；不把 active RTL 同名文件误当成当前候选输入。
- 基线清单 SHA256：`f5d7758d098b0a1c130988d687dd8b8e1bbe6581d685279dedde65f5bb8f8948`。
- 原始输入清单 SHA256：`ff5086550b0cedd8f75bd3c62650a28bb076c96137d1989a59a45816a7667fc7`。
- 启用 38 个 RTL / vendor 输入。与 C1 整机输入清单共有的 39 个文件（含头文件和许可等）全部逐字节一致。
- DDR 管理仍为 `basic_pitch_ddr_client_queues → basic_pitch_ddr_arbiter_pipeline`；不是换成简化仲裁器。
- 核心保留 sample / PCM / trigger / 状态 / 效果入口，另保留原生 DDR 客户端和 UI 页面提交接口；板级探针只把没有生产者的业务端口置闲。
- PCM 观察入口在 50 MHz 域；DDR 客户端及 UI 页面接口使用导出的 `ui_clk / ui_reset_n`，地址是 32-bit word 单位。
- DDR 分配继续使用 `rtl/ddr_address_map.vh`，没有新建地址权威或挪动分区。

完整命令和端口约定见 `rtl/display_data/README_HDMI_ISOLATION.md`。
默认显示 RTL dashboard，不伪造 AE350 软件页面；CPU 页客户端保持可接入。

## 构建与物理约束

- 在现有 `build.py` 增加显式独立配置；不调用整机 prepare，不编译固件，不生成新的长期编号生产 builder。
- 三份原理图 netlist 经现有 pinout 解析，只启用时钟、DDR、HDMI 管脚；保留板级 TMDS 反相。
- 六个业务时钟为 50 / 400 / 100 / 49.5 / 742.5 / 148.5 MHz；不降频，不增加整域 false path。
- 保留原有显示 / DDR CDC 例外和 DDR 初始化路径 `set_min_delay 0.800`，完整报告 setup / hold / recovery / removal。
- 物理 DDR PLL / DLL / divider 定位来自现有板级约束；DDR 初始化两个 FF 另用显式 `boards/custom_138k/hdmi_isolation.cst` 管理，不改整机约束。
- 本配置最终使用 place2 / route1 / replicate0，开启自动 hold 修正；整机配置完全不变。
- 16 bit GAO 继续观察 reset、DDR / BIST / front 状态及视频健康；探针额外寄存 15 bit，避免无业务消费者时被优化删除。
- GAO 带来的 `tck_pad_i` 是工具声明的 20 MHz JTAG 输入；独立审计显式核对其周期与 `tck_ibuf/I` 对象，不能把它当成第七个业务时钟忽略。
- UserCode / GAO ID 每个候选独立；关闭 SecurityBit，不写 Flash，不自动写 SRAM，不更新整机 latest 指针。

## 已完成离线验证

- 新单元测试 7 项：最小源集、锁定 UI / DDR、静态模式、输入漂移、工具假成功、默认时序目标兼容、CLI 配置互斥、采样与重放、UI 像素回归（部分在同一测试项内）。
- `test_current_workstation_sources.py`：10 项通过，accepted 输入边界保持。
- `sim/timing/test_workstation_timing_gate.py`：10 项通过。
- 使用实际 demo PCM 和两个实际 renderer：共享数据写 DDR / 回读后，**1,036,800 对像素逐项相同**，即完整 1920×1080 图像。
- 同一回归覆盖三帧、25 ms DDR 停顿、描述符 / 发布顺序、缓存代际一致性，以及 FFT 尚未就绪的启动帧。
- 实际队列管理器 + scanout：稳定 / 换帧、迟到行恢复、迟到 epoch 恢复三项通过；故意迟到时记录 underrun 并恢复，不把旧行显示成新帧。
- frame writer / view 提交：8 次提交、7 次迟到 pending 竞争通过。
- 物理检查复用锁定 DDR reset / 配置、视频 PLL_INIT、serializer / DDR 启动审计；仅在审计视图去掉一层 `u_display/`，不修改实现。
- serializer 原生层级 / 极性的六处适配使用已存在 native 审计的相同锚点，校验单次匹配，并记录原始与适配哈希。
- 检查脚本：`reports/workstation_hdmi_isolation_20261027/check_physical.py`。

仿真生成的 `current_ui.png` 是 RTL 渲染结果，不是上板截图，不是另画的 UI 示意图。

## 迭代记录

| 候选 | 综合 + P&R 墙钟 | 变化 | setup / hold 最差值 ns |
|---|---:|---|---:|
| D1 | 193.533 s | 首个完成实现的独立 UI / DDR | +0.501 / −1.331 |
| D2 | 189.335 s | 单独尝试参考时钟 PRIMARY 约束；本来已为 PRIMARY，无收益 | +0.501 / −1.331 |
| D3 | 199.899 s | 保留整机 WLOADN 区域；关闭 SecurityBit | +0.154 / −1.496 |
| D4 | 204.993 s | 使用锁定基线两个初始化 FF 的原始位置 | +0.036 / −0.431 |
| D5 | 240.822 s | 同源同定位，改 route1 | +0.669 / −0.117 |
| D6 | 331.446 s | capture 位置改为 R5C2，负向，不选用 | +0.652 / −0.309 |

D6 在独立 CST 保留 launch `R52C59[0][B]`，将 capture 从基线 `R17C2[0][A]` 改为 `R5C2[0][A]`。
该尝试没有改善结果，已回退至 D5 的 `R17C2[0][A]`；不将负向实验留作默认配置。
`set_min_delay 0.800`、时钟与检查门限都不变。

D1 的工具返回 0，但最初结果收集器误找 `hdmi_isolation.fs`，因此其包装状态失败；实际 GAO 镜像为 `ao_0.fs`，后续已修正。
更早准备阶段的 Tcl 宏选项 / GAO 网名问题没有产生可用镜像；分别改为显式配置头文件及保留的诊断寄存器。
所有失败与中间输出仍保留在 ignored `out/`，没有覆盖成“通过”。

## 交付候选 D5 与剩余问题

- 选作后续显示调试参考的是 D5 `C11027D5` / GAO `27D5`，不是负向的 D6。
- D5 综合 + P&R 实测 **240.822 秒，即约 4 分 1 秒**；不能据此承诺所有后续构建都固定为四分钟。
- D5 FS：`out/hdmi_isolation_20261027_d5/impl/pnr/ao_0.fs`。
- FS SHA256：`ecec68500569c14a24ff1d3558c1ebeb05403e5ba0e5e688d964fad326a5762b`。
- D5 输入清单 SHA256：`8adb017a1bbbf01c42ff9c33f48d1d30d9a4d02987303c23c54c6cd208d7d0ec`。
- `display.cst` SHA256：`5fc1cfc4c80fa6f786f0c78d16545d538bbee17989b263a1fc5d7748933ee867`。
- `display.sdc` SHA256：`757c664119762709e9347848b261f8c0ca1385ddd4edb3f5dd48dd0da1b25b31`。
- 新输入生产者 SHA256：`79cc8a7f580e9703c1064715e35a1d04859bdcb14f34b0a26b4178afedfd7f0d`。
- 新显示核心 / 探针 SHA256：`b9e68f5cf9312081b31a501f889826c15fda92baf0484ac82f39fb9738e711b4`。

最终默认源使用独立 CST 表达 D5 的两个 FF 位置。E1 `out/hdmi_isolation_20261027_e1_default` 仅 prepare，未编译 / 下载。
已逐字节确认 E1 的 **42 个实现输入**（38 个源、两个头文件、CST / SDC）与 D5 相同；Tcl / GAO 仅身份不同。
这证明默认源没有保留 D6 的负向位置改动，不把 E1 冒充已完成 P&R 的镜像。
另已检查配套使用 HEAD 版本的 pinout 工具 / profile，与当前工作区配套版本生成相同的 HDMI / DDR 约束；本次提交不夹带其他 USB 工作区改动。

D5 的视频 PLL_INIT、四路 serializer 与 DDR reset / 配置审计无错误，64 个 routed 选择器全部命中，六业务时钟及 GAO JTAG 时钟清单符合预期。
**严格时序仍失败**：setup / hold / recovery / removal 为 **+0.669 / −0.117 / +2.867 / +0.264 ns**。
唯一负路径为 `u_display/u_memory/u_ddr3/gw3_top/u_ddr_phy_top/ddr_init_internal_r_s0/Q`
到同一 PHY 的 `wloadn_3_s0/D`，从 DDR UI 域到 50 MHz 域的初始化保持路径。
因此 D5 是可用于继续缩小问题的诊断镜像，不是 timing-closed 或 release-ready；没有改 false path、时钟或 min-delay 门限掩盖它。
日志仍保留 PR1014：50 MHz 时钟存在普通布线分支；主时钟表为 PRIMARY 不代表所有分支都走专用资源，不能声称这一警告已消失。
离线物理结果在 `out/hdmi_isolation_20261027_d5/verification/routed_audit/result.json`。

## 资源明细口径

独立工程 D5 的报告 CLS 为 12,616、Logic 14,724、REG 13,041、DSP 9.5。
主设计 BSRAM 为 78 块，另有 GAO 1 块；分布与 D4 的逐实例核对相同：

| 物理归属 | BSRAM 块 |
|---|---:|
| 当前 DDR 控制器 / PHY 平台 | 32 |
| FFT / 立体声分析 | 30 |
| 波形采集 / 对齐 / 查表 | 6 |
| 共享显示数据读缓存 | 6 |
| scanout 双行缓存 | 4 |
| GAO | 1 |
| **含 GAO 合计** | **79** |

这些是实现 VO 原语计数与物理报告核对的结果，不是按容量折算的综合等效数。
尤其不能把含 DDR 平台的全部 79 块都算成 UI 渲染器自身占用。

## 验收与回退

离线验证结束时尚未操作板卡；随后按用户明确授权完成下述 SRAM 下载，实际 HDMI 画面仍待用户验收。
独立配置不带其他业务竞争，即使通过也不能替代整机 DDR 负载与屏闪回归。
整机 HDMI 修复目标仍未完成，不能把这个诊断工程冒充完整工作站修复。

需要恢复已知整机画面时，回退目标仍是 B3 `C11026B3`：
`out/official_ddr_ab_20261026_01/c11026b3/impl/pnr/ao_0.fs`，
SHA256 `a901738a4e07eb777cbc32eb571179e93ebae86e8488e573d4b65696e100011c`。
它仍有既知屏闪和时序缺口；不能宣称严格 release ready。

## SRAM 下载：2026-10-27 23:57（UTC+08）

- 用户明确要求“烧进sram我来检查”；仅执行 SRAM Program 和独立 Read Device Codes，没有 Flash 操作或断电。
- 下载 D5 `out/hdmi_isolation_20261027_d5/impl/pnr/ao_0.fs`，SHA256 `ecec68500569c14a24ff1d3558c1ebeb05403e5ba0e5e688d964fad326a5762b`。
- 下载前独立读取为 B3 `C11026B3`；SRAM 下载完成后，两次独立读取均为 D5 `C11027D5`，器件 ID `0001081B`，状态码 `00022230`。未执行 SRAM 逐位回读。
- 证据位于 `out/hdmi_isolation_20261027_d5/sram_deployment_20261027_235659/result.json` 及同目录日志。首次日志解析器未识别 `User Code is:`，已修正并额外独立读取确认，没有重复下载。
- 板上保留 D5 等待用户检查当前 UI、动态内容和屏闪。未进行 GAO 运行状态采样，不能由 UserCode 推断 DDR 就绪或 HDMI 显示正常。
- D5 已知 hold slack `-0.117 ns` 仍然存在；本次为诊断上板，不构成时序关闭、画面验收或完整工作站验收。

2026-10-28 的身份变化、D5 重新下载、用户确认 UI/动态内容可见但仍有屏闪，以及 D1 连续欠载计数，见 `WORKSTATION_HDMI_FLICKER_20261028.md`；不得继续将 D5 描述成“从未上板”。
