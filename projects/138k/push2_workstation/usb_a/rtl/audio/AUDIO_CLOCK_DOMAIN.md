# 双音频参考监测与 GW5A 时钟域组合

`workstation_audio_clock_monitor.sv` 与 `workstation_audio_clock_domain.sv` 提供可装配的独立时钟域实现，组合 [采样率事务核心](SAMPLE_RATE_SWITCH.md)。当前完整 top、FPC、DSP、时钟清单及构建 profile 尚未采用此组合；源码／仿真不等于 F03／A06 整项完成，物理时序、routed CDC、DAC 与 SRAM 验收仍未验证。

## 参考资格与失钟预算

每路源时钟驱动独立自由运行 binary 计数器，并在同一源上升沿将 **next binary** 转成 Gray 寄存。50 MHz 域以逐 bit 两级同步获取 Gray，转回 binary 后按无符号模差测量固定窗口内的源上升沿数。源计数器只在全局协调复位清零，并在对应源域等待三边沿同步释放，避免 raw source 上直接解除异步 reset 的 recovery／removal 风险；源停振时可保持这些测量寄存器复位，但失钟判定、超时和故障控制始终在常开 50 MHz 域，不等待它们释放。`restart_i` 仅清 50 MHz 域的测量基准、窗口与资格，不复位或门控源计数器。

| 默认参数 | 值及含义 |
|---|---|
| 原始参考 | K18 12.288 MHz（48k×256）、J19 16.9344 MHz（44.1k×384） |
| 参考域 | 标称 50 MHz，20 ns；仍须核对参考时钟自身供电／稳定性 |
| 测量窗口 | 50,000 参考周期，即标称 1 ms；端点名义计数 12,288 和 16,934.4 |
| 频率容差 | 标称 ±2000 ppm，另加至少 ±2 个端点／CDC 计数量化余量；44.1 路的非整数端点先 floor／ceil，再扩大范围 |
| 整数接受范围 | 48 路 12,261–12,315；44.1 路 16,898–16,971，边界包含在内；并非精确的 ±2000 ppm 窄带滤波器 |
| 稳定资格 | 连续 4 个有效完整窗口，初次约 4 ms；恢复时如果当前部分窗口不合格，最坏再等 5 个窗口及同步／预热延迟 |
| 短失钟 | 同步 Gray 连续 500 个参考周期无变化即撤销 present／qualified，约 10 μs，另加源 Gray 到参考域同步延迟；不等待 1 ms 窗口 |
| 停低证明 | 同步 Gray 和同步源电平连续 16 个参考周期无变化，电平确为低，且 restart 后同步历史预热完成；约 320 ns，另加同步延迟 |
| 计数宽度 | 32 bit，单窗允许增量必须小于 2³¹；参数校验拒绝名义上限超出半计数范围的配置。系统还须保证实际最高输入频率不在一个窗口内多次回绕 |

`clock_present_o` 只说明近期有源上升沿；即使频率错误仍可能为 1。`qualified_o` 同时要求连续频率窗口合格，错频最迟在下一个窗口撤资格；源停振按短超时撤资格，恢复后重新累计稳定窗口。`window_valid_o` 是参考域单周期结果，`window_good_o` 与 `window_edges_o` 保存最近完整窗口；没有统计最近窗口之前的测频结果不能当资格。

`stopped_low_o` 与频率资格独立。输出低但 DCS 内部门控尚未撤销的旧源，仍可能让新选择停在 QUALIFY 并超时；停在高的输出永远不产生停低应答。该证明供“撤选后确认停低”使用，存在 CDC 观测延迟，不能解释成对任意异步输入电平的零延迟断言。

`restart_i` 或期望模式变化都立即撤资格和窗口结果，随后先预热同步历史，再建立新的差分端点。restart 不取消物理时钟，不反压音频数据，也不复用上一个 DCS 源的测量资格。参考 50 MHz 未外部频标校准，这些结果属于相对测频，不证明绝对准确度、周期抖动、占空比或电气完整性。

## 组合与复位边界

组合层实例化两个独立原始参考监测器、一个选中输出监测器及官方 GW5A `DCS`：`CLKIN0=reference_48_i`、`CLKIN1=reference_44_i`、其余输入接 0、`SELFORCE=0`、`DCS_MODE="FALLING"`。DCS 的 CLKSEL 来自事务核心的 **50 MHz 寄存 onehot／全零输出**；没有普通逻辑时钟 mux，也不使用 SELFORCE 抢切停高源。

选中监测器的期望频率依据实际 `clock_select_o[1]`，不是提前提交的 staged 请求。事务核心在撤选和新选择时分别 restart，要求真正停低、新输出频率重新合格。复位请求同样为寄存控制，避免组合状态译码在 RESUME→RUN 发生瞬间低脉冲、误触发异步复位。

外部 `rst_ni` 可以异步断言，组合先在常开 50 MHz 域等待三边沿同步释放，再共同释放事务和三个监测器的参考域。监测器单独使用时，其 `rst_ni` 同样应已对 `clk_i` 同步释放。

`audio_reset_no` 是选中时钟域的实际局部复位：不安全时在 50 MHz 域立即异步断言；选中参考／事务资格成立后，等待 **三个真实选中时钟上升沿**才释放。即使选中时钟停高不再有边沿，失钟资格撤销仍能断言该复位。其用途仅限音频交付／serializer 子域，不清除 USB 会话、DDR、CPU、公共参数或系统事件队列。

`frame_quiescent_i`、`prefill_ready_i`、`output_running_i` 由外部经过 CDC 后在 50 MHz 域提供，继承事务核心契约：先确认完整帧与旧流作废，实际局部复位释放后再预填充，最后确认本代次第一完整输出帧。装配方须每轮清理旧应答，不能常接 1；mute／flush 是按消费者域握手的请求，不直接用组合译码作异步 reset。

组合的 `SWITCH_TIMEOUT_CYCLES` 默认为每等待阶段 2,000,000 个参考周期，即 40 ms。独立事务核心默认 20 ms；现有 FPC 的 1028 帧启动静音在 48k／44.1k 分别约 21.42／23.31 ms，如果预填充应答包含此启动阶段，20 ms 必然不足。后续整机应按实际 DAC、DSP 初始化和缓冲预算显式配置超时，并测量总静音时长，不能用一个 timeout 数字作为实际性能证据。

## 时钟与 CDC 约束需求

此实现添加了同步器属性，但**尚未**修改父工程 SDC／CST 或声称 routed CDC 通过。接入时需要：

- 为两路原始参考分别登记实际端口、周期、电气和专用时钟输入资源；DCS 输出按两种来源建立模式正确的生成时钟及互斥关系，核对实际 DCS 全局布线和所有两模式时序，不能将其当普通数据网。
- 三个监测器的 `source_gray[*]` 寄存器到对应 `gray_meta[*]` 首级，必须限制跨位传播／偏斜。最快正常参考周期约 59.05 ns，建议首次接入用更紧的 20 ns 数据到达上限并在布线后核验。已存在的测频项目采用 `set_max_delay` 到首级与仅首级异步 hold 例外，可作工具语法参考；不能加宽到整个 Gray 同步链或令异步时钟组例外覆盖该上限。
- 首级 `gray_meta` 不得在同步前加入组合 Gray 编码、位选择、旁路或复制；`gray_sync` 第二级及后续转码／窗口逻辑保留正常 50 MHz setup／hold。分别核验原始两路与选中一路的物理路径，不能只验证其中一条总线。
- 原始电平同步的 `level_meta` 仅首级作明确 CDC 处理；`level_sync` 不直接充当时钟。三个源计数器的 `source_reset_pre`／`source_reset_n`、常开控制域的 `control_reset_pre`／`control_reset_n` 及音频域 `reset_release` 都须保留 recovery／removal 和正确域检查；不能给整个子模块加 reset false path 掩盖恢复／去除问题。
- DCS CLKSEL 的时钟控制要求、源失钟／恢复行为和 PDN／SMUTE 外部时序须由器件／DAC 正式手册及真实波形验收；仿真中的脉宽检查不替代物理 pulse-width 门禁。

## 局部验证

```sh
PATH=/opt/homebrew/bin:$PATH python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_sample_rate_switch.py
PATH=/opt/homebrew/bin:$PATH python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_audio_clock_domain.py
```

组合测试直接使用官方 GW5A `prim_sim.v` 并记录模型 SHA256，三组异步初相位覆盖频率窗口、短失钟、低电平停稳、错频拒绝、双向切换、忙拒绝、旧源／目标停高故障、显式恢复和三边沿局部复位释放；缩窄源计数器验证多次回绕。另一 TB 使用真正的默认 50,000 周期／4 窗／500 周期失钟配置，核对名义测频、资格时间、停高／停低及 restart 不修改源计数器。测试不连接真实 serializer、DSP 或板卡。
