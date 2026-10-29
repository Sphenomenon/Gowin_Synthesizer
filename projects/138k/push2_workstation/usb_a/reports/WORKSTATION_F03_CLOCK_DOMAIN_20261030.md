# F03／A06 双音频时钟独立检查点（2026-10-30）

本检查点完成可装配的双参考测频／失钟监测、官方 GW5A DCS 与常开切换事务的独立组合。**F03／A06 整项仍未完成**：当前完整工作站 profile、top、FPC、DSP 和时钟清单尚未消费此实现；未综合、P&R、routed CDC、板测、SRAM 或 Flash。机器记录、逐文件 SHA256、精确命令及输出见 [clock_domain.json](workstation_task_20261030/clock_domain.json)。

## 来源与范围

- 基础源码：`3d4b3175d0f20d0b787b61b43e4543739b26bca1` 加 JSON 列出的已修改／新增输入；本身份为 `f03-a06-clock-domain-offline-20261030-v1`，不是位流 UserCode。
- 实现：[monitor](../rtl/audio/workstation_audio_clock_monitor.sv)、[domain](../rtl/audio/workstation_audio_clock_domain.sv)、[事务核心](../rtl/audio/workstation_sample_rate_switch.sv)。契约分别在 [时钟域说明](../rtl/audio/AUDIO_CLOCK_DOMAIN.md) 和 [事务接口](../rtl/audio/SAMPLE_RATE_SWITCH.md)。
- 原始参考沿用既有测频来源：K18 标称 12.288 MHz，J19 标称 16.9344 MHz；已有六个 10 秒窗口不是当前组合的新实板测量。50 MHz 参考未外部频标校准。
- 器件依据：本机 `UG306-1.0.6E Arora V Clock User Guide` 正文 12–15 页／PDF 21–24 页的 DCS；正文 8 页／PDF 17 页的 PLL 输入频率限制。原始 PDF SHA256 和路径在 JSON，不修改 vendor／冻结 baseline／历史证据。
- 仿真直接使用 Gowin `gw5a/prim_sim.v`，SHA256 **`2ec53fec48601d2d491299bc3a28b4b199d3a79708f1dd38f72555a5c688ebd5`**。DCS 为官方 `CLKIN0..3` 端口，`FALLING`／`SELFORCE=0`，不是普通 mux stub。

## 本次实现与纠错

三路监测（原始两路及 DCS 输出）均使用源域 binary／next-Gray 同沿寄存、参考域两级同步、固定窗口无符号模差测频。默认 1 ms 窗、连续 4 窗、±2000 ppm 加端点量化余量，短失钟为 500 个参考周期。DCS 撤选须有 restart 后真实连续停低证明，新选择重新测频，旧资格不能复用。

`source_binary`／`source_gray` 现在经过源域三边沿同步释放；组合的 50 MHz 控制复位也三拍释放。源停钟不会阻断参考域超时和失败处理，restart 不清源计数器。选中音频域局部复位可在无时钟边沿时异步断言，资格和事务许可恢复后须有三个真实选中边沿才释放。

组合校验揭示了上一检查点的状态译码缺陷：核心的 `audio_reset_no` 原由 `state == RUN || ...` 组合产生；RESUME→RUN 即使两端都需要释放复位，译码仍出现 delta 低脉冲，重新清零实际异步复位链。单独核心的静态电平检查没有暴露此问题。

本次将 **audio reset 请求与 DCS onehot 选择改为 50 MHz 寄存输出**，在对应事务阶段原子改变。负对照从上述基础 commit 只读提取旧核心到临时目录，与当前 domain／monitor／TB 组合；未改写工作区或冻结来源。旧核心稳定复现退出 1：

```text
startup state epoch=0 active44=0 reset=0 state=1
Time: 30511000  Scope: tb_workstation_audio_clock_domain
```

这是仿真 30.511 μs 时已报告 RUN、实际局部复位却被清零的错误；不是物理波形测量。使用寄存控制后，同一测试三组异步初相位均通过，并验证实际 reset 释放需要三边沿。负对照的旧源 SHA256、编译／运行 argv 与失败原文保存在 JSON。

正常事务仍先完整帧 quiesce，再撤选、资格、预填充及真实输出应答，最后提交模式／epoch。旧源停高时 DCS 无法等到门控撤销下降沿，必须故障静音／局部复位；禁止用 SELFORCE 非无毛刺切换掩盖。恢复须等源重新合格，并显式重试。未定义新 MIDI CC、切换入口或持音／TF／录音产品策略。

## 校验

从仓库根目录执行，环境为 Python 3.14.6、Icarus Verilog 13.0 stable、Verilator 5.052。以下命令 exit 0，完整输出在 JSON：

```sh
PATH=/opt/homebrew/bin:$PATH python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_sample_rate_switch.py
PATH=/opt/homebrew/bin:$PATH python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_audio_clock_domain.py
PATH=/opt/homebrew/bin:$PATH verilator --lint-only -Wall --top-module workstation_sample_rate_switch projects/138k/push2_workstation/usb_a/rtl/audio/workstation_sample_rate_switch.sv
PATH=/opt/homebrew/bin:$PATH verilator --lint-only -Wall --top-module workstation_audio_clock_monitor projects/138k/push2_workstation/usb_a/rtl/audio/workstation_audio_clock_monitor.sv
```

- 原事务核心：1375 个参考周期，覆盖双向切换、实际输出应答前不提交、busy／目标拒绝、旧源停高、目标丢失、各等待超时、启动失败及显式恢复。
- 新组合：三组异步初相位；短窗／12-bit 计数器多次回绕、错频仍 present 但不 qualified、全撤选停低、新源重新资格、旧源／目标停高和恢复、局部复位三真实边沿。
- 生产默认预算：真实 50,000 周期／1 ms 窗与 4 连续窗测试，计数 12,288／16,934；500 周期失钟设置在测试中 503 个参考周期撤资格（包括 CDC 观测延迟），并分别覆盖停高／停低、restart 不改源计数器。
- first-party monitor／controller 的 `-Wall` lint 零警告。额外整包 vendor simlib lint 尝试 **未通过**，退出 1、109 条警告，包含其旧 procedural assign/deassign、命名／宽度／unused 及组合层有意留空诊断输出。精确命令记在 JSON；没有屏蔽警告或修改 vendor，因此不能写成整个组合 lint 全绿。

独立时钟 TB 的 quiesce／prefill／output-running 仍是外部响应模型，不能据此声称真实 serializer／DSP 完成。后续真实帧组合补证另行注明，不回写原独立测试为更大范围验收。

## 约束、硬件与剩余工作

1. 三条 `source_gray[*] → gray_meta[*]` 分别约束和检查：最快正常源周期约 59.05 ns，首次接入建议更紧的 20 ns 数据到达／偏斜目标；只对首级做明确异步处理，第二级和后续保留 setup／hold，不能被整体异步时钟组例外覆盖。
2. 两参考／DCS 两种来源生成时钟、onehot 时钟控制、真实专用布线及所有 setup／hold／recovery／removal／pulse-width 尚未入父 SDC／CST 或物理验证。源域、控制域、音频域三类 reset 释放同样需 routed 审计。
3. 实装 **AK4493S** 正式手册／修订及 384fs 自动识别、ACKS、PDN／SMUTE 变频次序仍待核对，不能用旧 AK4493 手册替代。板级电气、两参考／MCLK／BCK／LRCK 实测、冷暖启动与真实音频未验收。
4. 16.9344 MHz／384fs、BCK 除 6 的数字方案可实现；现有 FPC 和 DSP 未迁移。输出时基驱动请求、tagged PCM、DSP 两率系数／历史、最终 PCM 同帧 tap、持音与 PANIC／Note Off、媒体和录音格式仍需完整集成。
5. domain 每阶段 40 ms 默认超时需用真实 serializer 启动与帧应答核对。当前 FPC 1028 帧静音在 48k／44.1k 约 21.42／23.31 ms，旧核心 20 ms 不足以覆盖此预填充；超时数字本身不是实际切换时长。

回退：这是独立源码检查点，无板卡状态变化；完整 accepted／pinned／resource／新板 profile 与已有部署身份未被本检查点切换。后续只在显式新候选接入，继续保留现有回退路径。
