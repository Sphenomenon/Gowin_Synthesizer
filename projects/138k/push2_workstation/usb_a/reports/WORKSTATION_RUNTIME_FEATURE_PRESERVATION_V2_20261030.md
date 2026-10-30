# Runtime rev4 v2 功能保留静态审计（2026-10-30）

本审计固定在 `custom138k-workstation-v1-41e653fe462e5ea3` 的已完成综合输入与 VG，解释 NL0002 层次裁剪，并发现 native HDMI 的频谱、XY 和双声道电平显示回归。**功能保留门禁未通过**；不能以独立分析 producer 仍存在代替可视输出检查。本报告冻结修复前事实，后续修复使用新源码／候选身份，不能覆盖此证据。

机器证据为 [runtime_feature_preservation_v2.json](workstation_task_20261030/runtime_feature_preservation_v2.json)。范围仅为选中源码、静态 LUT 真值与寄存器连线；没有新综合、P&R、物理资源、STA、板测或部署验收。

## 固定输入与编译边界

- 工程：`~/.cache/gw138k-task-20261030/runtime-rev4-synthesis-41e653fe/workstation/Prj1`。
- VG：`impl/gwsynthesis/custom_138k_integration.vg`，SHA256 `2319746ad8eabba1e19721908402dd0c25bd91aba52b896650d82153e6c4e3da`。
- `process.json` 的 560 项输入必须与准备 profile 的 `staged_input_sha256` 整体完全相等，独立逐项重哈希，审计前后再次封口；不是只检查非空子集。原综合状态为完成、exit 0、输入未变、`synthesis_only`。
- 实际启用请求队列是 `rtl/timing/basic_pitch_ddr_client_queues.sv`（SHA256 `4a1c49cbea79514d68a1d0c567f0cd5dfd6b1bdfad1c9cf5df1e1a9c4443d2ab`），不是同名 `rtl/music/` 文件。
- 实际启用 raster 是 `rtl/display_data/feedback_renderer.v`，dashboard 是 `src/video/feedback_dashboard.v`；历史 `src/video/feedback_renderer.v` 禁用。选中源和 include 提供者及各自哈希见 JSON。
- 此时工作区已有后续修改，审计不将其当作本 VG 的来源。

## 层次裁剪与保留结论

| 对象 | 源码与 VG 结果 | 结论范围 |
|---|---|---|
| `u_video/u_scan_window` | 标签裁剪，writer/CPU 准入条件合并进 stable slot 的 LUT | 准入逻辑仍在；不是移除准入 |
| `u_managed/runtime/taps` | analysis/record enable 均绑 0，统计／事件输出悬空，帧字段本为直接 alias | 裁剪合理；不能解释成全局录音关闭 |
| `u_managed/consumers/spectrum` | 9 组 FFT 输出在顶层全部悬空 | 此观察 FFT 消失有明确来源；不代表可视 FFT 已通过 |
| `u_managed/midi_uart` | custom top 的 `midi_rx_i=1'b1` | 独立 MIDI 扩展口在此板型未接入；USB MIDI 不能由此判断 |
| `u_managed/pc_uart` | idle 选择 LUT 与两级 RX 同步器保留 | PC UART 条件路由保留；无协议／物理验收 |
| compute recorder / score | 两个层次与其存储原语保留 | 没有全局裁掉录音或乐谱；不代替业务验收 |
| native HDMI producer | 独立 `output_audio_analysis`、writer、reader 均存在，16 位谱输出直连 writer | 计算／导出保留；**可视分析链被关闭** |

### Scan window 的实际逻辑

源码 `workstation_ddr_scan_window.sv` 只阻塞 writer 与 **CPU 写**，CPU 读允许在 scan fetch busy 期间进入空槽。`video_ddr_scanout.v:160` 的 busy 是 `active || request_pending`。

- `u_video/u_arbiter/u_writer_slot/n16_s1`：LUT4 INIT `0100`，I0=`active`，I1=`request_pending`，I2=`writer_qvalid`，I3=`merged_req`。16 组合逐项核对为 `!active && !request_pending && !full && merged_req`。
- `u_video/u_arbiter/u_cpu_slot/n16_s2`：LUT4 INIT `001F`，I0=`active`，I1=`request_pending`，I2=`cpu_mem_write`，I3=`cpu_qvalid`。16 组合逐项核对为 `!full && (!write || !(active || request_pending))`。
- CPU 后级 `n16_s1` INIT `4000` 再与 `m_release[2] && !memory_state[1] && memory_state[0]` 组合；128 组合通过，匹配 AHB bridge 的 `M_REQUEST=1`。
- writer 281 个和 CPU 115 个保留的 payload DFFRE 均只使用相应 capture 使能。两槽 `full_s2/Q` 直接连接 `u_core/{writer,cpu}_qvalid`，中间没有 scan-window 组合门控。
- `full_s2` 的 D LUT 都是 INIT `556A`；在已占槽条件下，下一占用状态是 `!queued_ready`，不受新请求准入或当前 scan busy 支配。ready 的 arbiter 策略仍可能延迟服务。这里没有证明完成时限、跨复位生命周期、恰好一次或所有 DDR 客户端有界服务。

### Runtime taps 与观察消费者

`workstation_runtime_controlled.sv:217–220` 禁用的是 runtime 内的两个脉冲 tap，compute 域的独立 observation bridge、recorder、score 仍接线。serializer 与 observation 的 valid、error、rate、epoch、sequence、PCM 共 **99 位** canonical alias 逐位相等。taps 没有承担这些字段的寄存或节流，因此标签消失不会断开已完成物理帧。

`workstation_observation_consumers.sv:67–74` 的观察用 256 点 FFT 输出在 `gw138k_push_workstation_top.v:417–418` 全部悬空；这是该层次被裁剪的直接原因。recorder 与 score 及其 5 个 SDPB leaf 保留。

### UART

custom top 的 MIDI 接收输入在第 42 行绑 idle 1；`midi_uart` 不保留。PC 输入在第 383 行受 `music_model_status==14 || tf_mode_50` 选择。VG 中顶层 `n1049_s1` LUT3 INIT `F1`，输入为 `tf_mode_50`、`model_ready`、物理 `pc_uart_rx_i`，8 组合核对为启用时透传 RX、否则 1；连接 50 MHz 的 `rx_sync_0_s0` 再到 `rx_sync_1_s0`。此结论不包含波特率、帧内容或物理 UART 成功。

## 必须修复：native HDMI 关闭了可视分析

1. 显式 runtime provider 定义 `WORKSTATION_RUNTIME_NATIVE`，再 include profile HDMI 与 `workstation_hdmi_display.sv`。
2. native 分支 `workstation_hdmi_display.sv:194` 以 `ENABLE_ANALYSIS=0, SHARED_EXPORT=0, SHARED_RENDER=1` 实例化 raster；关闭本地 FFT 的意图合理，因为 `u_runtime_display/producer/analysis` 已拥有独立 FFT。
3. 但 `feedback_renderer.v:176/189` 同一个 `ENABLE_ANALYSIS` 也传给两路 `feedback_dashboard`。
4. 实际选中的 dashboard `src/video/feedback_dashboard.v:285` 关闭分析页文字，`:412–441` 关闭谱柱、XY／Lissajous、左右电平及分析页布局。共享输入即使有效也不会进入可见像素。
5. VG 的 reader 与 raster 已没有 spectrum/image/analysis/左右 peak 端口，reader 的 image/spectrum cache 也被裁剪；producer 的 FFT 与写入链仍在，构成“计算存在、可视输出消失”的真实回归。

来源比较已查验锁定基线的实际 GPRJ 编译项与原始字节：accepted full83 的 HDMI 第 148 行、resource route0 第 149 行均显式 `ENABLE_ANALYSIS=1`；renderer 把 1 传入两 dashboard。现有非 native provider 也选 1。此缺口由 `b1ed354211f2dcc8fe77f2cd94966064cbd9bcee` 的 native HDMI 组合引入，不是历史默认方案本来关闭。这里只比较来源，未新跑默认 prepare／综合／硬件。

最小修复：renderer 新增 `RENDER_ANALYSIS=ENABLE_ANALYSIS`，两 dashboard 单独用 `RENDER_ANALYSIS`，native 显式设 `RENDER_ANALYSIS=1`、保留 `ENABLE_ANALYSIS=0`。默认继承保持旧 provider 行为，独立 FFT 不复制。必须用真实 writer→reader→dashboard 的已知频谱、XY 与左右电平像素回归，并保留原配置负对照及默认兼容比较。

恢复 minor1 reader 的双银行 image 为 `2*2048*32=131072` logical bits，spectrum 为 `2*512*16=16384` logical bits，总计 `147456` bits，即 **18 KiB**。这是被裁剪存储的逻辑预算，不能换算为已验证物理 BSRAM 数；dashboard 像素逻辑、元数据寄存器、实际映射和新增时序路径仍需新候选综合、P&R 与功能保留检查。

## 复验

只读审计脚本保存在本机固定 cache，脚本与解析器 SHA256 一并写入 JSON：

```sh
python3 /Users/sphenicidition/.cache/gw138k-task-20261030/runtime-feature-audit-v2/audit.py
```

脚本覆盖 16+16+128 个准入组合、两槽占用更新的有效组合、396 个 payload FF 的 capture 使能、99 位物理帧 alias、16 位 producer→writer 谱 alias、UART 8 组合和两级同步连接，同时重验全部 560 项综合输入封口。本静态结果不解除 CDC、SDC 对象、时钟物理、资源、DDR deadline、可视输出或整机板测门禁。

父级独立重跑脚本，得到相同 identity `runtime-feature-static-v2-6486801daf7954b2` 和完全相同 JSON SHA256 `653f10d0f84242a3e488b4802aac7270d23929282a8642c20cfeb8514520b9d4`；`all_features_preserved` 仍为 false。该检查点提交的是已复核的缺陷证据，修复及新候选验收另行登记。
