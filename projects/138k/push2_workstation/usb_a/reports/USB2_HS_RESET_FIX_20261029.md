# USB2 HS 复位修复：138K AC 与 25K DD 候选

日期：2026-10-29，Asia/Shanghai。用户授权修复并在需要切换 JTAG 时通知。本轮只使用 SRAM，不改写两板 Flash。

## 修复

1. `firmware.c` 的原生 `WORKSTATION_USB2_NATIVE` 分支不再于 `connect()` 中重复调用 `usbhw_reset()`。原生 `usbhw_hub_enable()` 已执行端口复位并等待协商就绪；旧 FS Host 分支保留原复位调用，backend 的显式端口复位 API 也保留。
2. 25K `midi_usb_hs_phy.v` 从 HS_SUSPEND 进入 WAIT_RST 时，将先前已经完成的 3 ms 资格时间计入 `usb_rst_time_q`，不再重复等待。冷启动及 FS 复位仍从零计时，设备 K 持续时间不缩短。
3. 新增 `tb_usb_hs_reset_timing.v`，检查冷启动和两次连续 HS 热复位均在 Host 的 7 ms 窗口前结束设备 K，并重新完成 HS 协商。

18 项定向检查通过：冷启动 K 为 2,999.888–4,099.844 us，热复位 K 为 3,124.917–4,224.873 us。用已部署 DA 的冻结 PHY 做负对照，同一新测试在 7,224.753 us 结束设备 K 后正确拒绝。

证据：`~/.cache/fpga-usb2-hdmi/25k-hs-reset-regression-20261029_222317/`。原始时序冲突和旧 DA 源码身份见 `USB2_HOST_PROBE_20261029.md`。

## 138K 新候选与实际下载

```text
~/.cache/fpga-usb2-hdmi/138k-host-c11029ac-20261029_222154/
```

- UserCode `C11029AC`；继续使用原生 headless Host 探针，不增加端口、不修改球位，不切换完整工作站的 accepted profile。
- 原生清单 SHA-256：`001b314050ef485786e4e4af890e67fd8000388ad11248cd2339bdd0102e4e42`。
- 实际位流 `impl/pnr/ao_0.fs` SHA-256：`ec8245e6434bd5892fd20f9051bd722733d49802797735450cc852ff6c34030a`。
- 22:21:55–22:24:00 完成综合、布局布线和审计，约 125 秒。保留 60 MHz ULPI 及实际 USB3300 IO 延迟，setup/hold/recovery/removal 为 +0.081/+0.175/+4.973/+0.250 ns，无负路径。
- 22:25:12–22:25:27 执行 SRAM Program and Verify。写前独立身份 `0x0001081B / C11029AB`，写后独立身份 `0x0001081B / C11029AC`。
- 下载记录位于候选 `sram-deployment/`；回滚为原 `C11029AB` 位流，记录精确 SHA-256。138K Flash 的 E5 没有改写。

## AC Host 与旧 DA Device 已实测建立 HS

在没有改写 25K 的情况下，AC 下载后立即完成 GW25K 枚举，证实移除重复复位已改变板上结果：

| 指标 | 22:25:27 | 22:27:39 | 22:32:14 |
|---|---:|---:|---:|
| high_speed | 1 | 1 | 1 |
| Function Control | 0x40 | 0x40 | 0x40 |
| port_state | 16 ACTIVE | 16 ACTIVE | 16 ACTIVE |
| state_history | 130047 | 130047 | 130047 |
| CPU connected / generic MIDI / GW25K | 1 / 1 / 1 | 1 / 1 / 1 | 1 / 1 / 1 |
| attempts / failure_history | 1 / 0 | 1 / 0 | 1 / 0 |
| received_peak | 10,416 | 215,579 | 641,007 |
| transmitted_peak | 2,889,132 | 6,527,657 | 14,083,637 |
| sof_peak | 14,378 | 1,066,923 | 3,264,265 |
| CPU milliseconds | 1,949 | 133,508 | 408,156 |
| MIDI received_events | 0 | 0 | 0 |

`state_history=130047` 比原 AB/DA 的 131071 少 bit10，即本次未进入 FULL_SPEED_RESET。每个窗口前后都独立读取当前 FPGA 身份；core0/core1 各 1024 点，不宣称跨核原子快照。SOF 增量除以 CPU 毫秒增量约为 8000.57/s，与 HS 模式一致；这不是 480 Mbps 的有效载荷吞吐测试。

当前结论是 **480 Mbps HS 连接及 GW25K 枚举已实板成立**。新 SRAM 从零计数，不能沿用 AB 镜像下的 1135 个 MIDI 输入；已请用户重新操作触摸板，以验证本次 HS 下的新增 MIDI 事件。

22:44:24 再读同一 AC 身份：连接已持续约 19 分钟，仍为 `high_speed=1`、`port_state=16`、`state_history=130047`、`attempts=1`、`failure_history=0`。CPU 仍识别 GW25K，`cpu_fault=0`、`out_errors=0`；本次启动后的 `received_events` 仍为 0。证据位于同一候选的 `capture-20261029_224424/`。

## 回归与 25K 后续

- 138K `test_current_workstation_sources.py` 10/10，探针单测 9/9。
- `test_workstation_usb2_application.py` 4/4；覆盖生产 Push 整帧、FS64/HS512 分包、交替热插拔／失败重试、backend 显式复位／epoch 和真实应用端到端仿真。原生连接 mock 明确检查没有第二次复位。
- 25K 首轮完整回归发现旧 `tb_usb_board_device` 在热复位后固定等待 650,000 周期，超过 10 ms 才回应 Host chirp；修复设备按时结束等待后，该用例反而错过协商窗口。保留首次失败证据，将测试改为在 7 ms 内等待设备 K 结束再回应，不放宽 Host 或设备时限。
- 修正测试后的完整回归于 22:36:00 完成，102/102 通过，运行期间输入无变化。证据：`~/.cache/fpga-usb2-hdmi/25k-hs-full-checks-20261029_223129/validation.json`。其后仅构建器增加显式物理实现选项；RTL、约束、配置和测试输入与该回归完全一致。构建选项帮助及非法值拒绝另有 4/4 检查，见缓存的 `25k-build-implementation-option-tests-20261029.json`。
- 新 25K 候选使用当前版本化完整键盘、默认 USB2、`--usb2-debug`，不是剥离业务的 USB-only probe。与 DA 的既有差异包括默认关闭的 attach delay／probe 支持、FIFO 复位同步和 FS reset re-arm；这些均保留并进入候选来源记录。
- 首次 `C12529DB` 于 22:35:09 物理实现失败：`PR0009`，8 条 GAO 调试网未布通；未发布位流、未下载。失败日志保留在 `~/.cache/fpga-usb2-hdmi/25k-hs-fixed-c12529db-20261029_222538/`。
- 重试 `C12529DC` 于 22:37:40 启动，使用显式 `place_option=2`、`route_option=1`、`replicate_resources=0`；22:45:45 仍路由失败，`PR0004`、3394 条网未布通，未发布或下载。来源快照和日志位于 `~/.cache/fpga-usb2-hdmi/25k-hs-fixed-c12529dc-20261029_223740/`。
- DB 物理报告显示主设计 CLS 为 11415/11520，BSRAM 为 54/56，GAO 还需 363 个逻辑单元和 2 个 BSRAM。改用安装工具 `IDE/data/config/rtlplaceoptions.xml` 明确标注的 routability-priority（`place_option=1`）重试；路由和资源复制恢复原默认策略，时钟、功能、全部时序门禁不变。
- `C12529DD` 于 22:48:20 启动，22:53:41 完成，完整键盘、USB2 debug 和全部离线门禁通过。来源快照和日志位于 `~/.cache/fpga-usb2-hdmi/25k-hs-fixed-c12529dd-20261029_224820/`；该目录的 `regression-input-binding.json` 已将 102 项完整回归和 4 项构建选项检查与实际来源快照绑定。setup／hold／recovery／removal 为 +0.102／+0.189／+0.006／+0.352 ns，setup／hold 负端点均为 0；实际位流 `impl/pnr/ao_0.fs` SHA-256 为 `f83432abf9f186ee9bb87101d6394981e10212a419b0f55c70c4d812d28e9da1`。DD 尚未下载，25K 仍为旧 DA。
- 22:51:42，旧 DA 重新插拔后，AC 捕获到 `high_speed=0`、Function Control `0x45`、ACTIVE、CPU connected／generic MIDI／GW25K 均为 1，说明本次回退 FS；不能据此前一次持续 HS 连接宣布热插拔已修复。证据为同一 AC 候选的 `capture-20261029_225142/`。后续应将 JTAG 切到 25K，先读取旧 DA，再部署 DD 并重测热复位／重插拔。
- 25K 下载后先读设备侧 HS／online／MIDI 诊断；再将 JTAG 接回 138K，验证主机侧状态。可使用原先会二次复位的 AB Host 作为热复位硬件对照，但不得将这种临时验证部署冒充最终 AC 部署。

## 本次提交时的板上状态

25K 后来已拔下，当前同一 138K USB-A 接 Push，JTAG 仍在 138K。23:27:57–23:28:12 重载同一 AC SRAM 镜像后，Push 的独立会话历史到达 HS RECOVERY，却没有进入 ACTIVE 或开始 CPU 枚举；这是另一项尚未解决的问题，见 `USB2_PUSH_RECOVERY_20261029.md`。没有下载 DD，也没有改写任一板的 Flash。
