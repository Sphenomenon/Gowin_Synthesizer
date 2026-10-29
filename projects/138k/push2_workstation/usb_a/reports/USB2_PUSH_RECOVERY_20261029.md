# 实物 Push：HS 恢复阶段排查

日期：2026-10-29，Asia/Shanghai。JTAG 在 138K，Push 接同一个 USB-A 口；本轮 SRAM 下载沿用用户授权，不写 Flash。25K 不同时接入，也未改写其固件。

## Ableton 文档与失败层级

本机官方手册：`migration/midi_device_reference/ableton_push2_20260911_005756/AbletonPush2MIDIDisplayInterface.asc`，SHA-256 `d0d38e42620bde78cf72822bbc71610d76ea7765dd4f61a8779fcea8955c522d`。

- Purpose（第 62 行起）明确允许 standalone 应用；使用 Push 不要求电脑运行 Ableton Live。
- MIDI Mode（第 271 行起）规定初始为 Live 模式；`0x0A` 切换 Live/User/Dual，作用于已经建立的 MIDI 端口。
- USB Display Interface Access（第 1614 行起）将设备描述为 MIDI 加通用 bulk 显示接口的复合 USB 设备。显示帧、灯光和 MIDI 模式命令不能替代底层 USB 握手／枚举。

## AC 与 Push 的原始结果

138K SRAM `C11029AC` 保持不变。23:17:40 和 23:20:43–49 的四次 JTAG 窗口均未见 CPU `connected`，MIDI 事件为 0，CPU fault 为 0。采到端口 WAIT_PHY、DEBOUNCE、CHIRP_STREAM；不是完全没有看到接入，也没有稳定连接，不能仅凭协商过程的 `high_speed=0` 宣称 FS 已连接。

23:27:57–23:28:12 将同一 AC 位流重新 SRAM Program and Verify，清除旧 25K 会话历史。写前／写后均独立确认 `0x0001081B / C11029AC`，位流 SHA-256 `ec8245e6434bd5892fd20f9051bd722733d49802797735450cc852ff6c34030a`。证据目录：

```text
~/.cache/fpga-usb2-hdmi/138k-host-c11029ac-20261029_222154/push-isolation-sram-20261029_232757/
```

单独连接 Push 后三个窗口（23:28:12、16、19）一致：`state_history=64511`，包含 CHIRP、HIGH_SPEED_TAIL、RECOVERY，但不包含 FULL_SPEED_RESET 或 ACTIVE；`received_peak=0`、`sof_peak=12`、CPU connected/events/fault 均为 0。因此本次失败早于 CPU 的 EP0 枚举／Push 专用初始化。不能把原先 AC/DA 的成功 HS 连接或旧 MIDI 计数移用于 Push。

## 恢复阶段观察器

扩展既有 `PORT_OBSERVER=1` 诊断分支，不改 USB 端口、球位、retired ports 或锁定网表：

- 锁存 RECOVERY 进入次数、到 ACTIVE 次数、异常退出次数及退出状态、ULPI 周期数、SOF 数。
- 保留退出前的 Function Control、有效 RXCMD、同步后的 fault 标志，以及实际 ULPI SOF token。
- 记录主机命令和结果，区分尚未开始 EP0 与控制传输失败。
- GAO 新增第三个 ULPI 域观察核；捕获器继续支持历史双核候选。CPU 已连接且非 generic-MIDI 的现有模式按 Push 识别，不再把所有非 GW25K 枚举标成失败。

首次诊断候选 AD 在综合后因 CDC 寄存器合并、约束对象丢失而拒绝；保留 failure meta/sync 寄存器后 AE 布通，但严格时序门禁仍拒绝。AE 同时暴露新诊断标志直接读取参考域 fault，以及已有初始化状态解码到 ULPI 数据口的长路径：改用既有 ULPI 同步 fault；初始化 ready 改为进入 DONE 时同周期置位的保留寄存标志，不加等待、不改失败／复位语义。失败候选均未下载。

`C11029AF` 使用上述版本化源码和相同生产输入固件、60 MHz ULPI、原 IO delay、CDC／PLL 和完整时序门禁；23:49:14 启动重新构建。候选目录：

```text
~/.cache/fpga-usb2-hdmi/138k-push-recovery-c11029af-20261029_234914/
```

23:53:02，AF 完成布局布线，但审计拒绝：ULPI Fmax 为 55.711 MHz，低于 60 MHz；8 个 setup 端点为负，最差 −1.283 ns，路径从 `supervisor/release_q_1_s0/Q` 到 `usb2_ulpi_data_6_iobuf/IO`。hold／recovery／removal 分别为 +0.213／+4.828／+0.253 ns。新观察器与 ready 等价调整已通过下列离线回归，但此诊断候选仍未时序闭合、未下载；板上仍为 AC。原始结果保留于该目录的 `host_probe_audit.json` 和 `build.log`，本次 Git 提交不收录实现数据库、位流或捕获。

## 离线验证

- 首轮 `test_current_workstation_sources.py` 10/10、Host probe 10/10、完整 MMIO 9/9；MMIO 包含真实 CPU／USB3300／25K 路径，耗时 394.194 秒。日志：缓存 `push-recovery-regressions-20261029.log`。
- ready 等价修正后：初始化器 19 场景／5474 检查、物理组合 5 场景／3115 检查、恢复观察器的异常退出／成功恢复／SOF／EP0／重试／全局复位定向仿真通过。日志：缓存 `push-recovery-ready-tests-20261029.log`。
- 最终源码的来源边界 10/10、Host probe 10/10 复跑通过；HS/FS 端口、25K 热复位及原生控制器 3/3 通过（326.849 秒）。端口包含 16 场景／23830 检查，原生控制器 HS／FS 各 1146／266 检查；日志为缓存 `push-recovery-final-source-tests-20261029.log`。

下一步：先修复诊断候选的 ULPI 输出时序并重新通过全部门禁，再读取三核实际捕获，判定退出恢复是 PHY disconnect、MAC fault 或软件取消；当前证据不支持将问题归因为 Ableton MIDI／显示协议。
