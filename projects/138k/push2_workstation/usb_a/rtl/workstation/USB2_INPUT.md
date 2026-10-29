# 原生 USB2 工作站输入组件

`workstation_usb2_input.sv` 将真实业务固件所在的原生 CPU／USB2 SoC 接入已有 `push2_usb_a_control`，一直到原来的 18 bit 事件异步 FIFO、读端缓存及音频域生命周期输出。它不是新的参数 owner，也不是新板完整顶层。默认 `--usb2-component soc`、accepted 和资源候选均不自动改用本组件。

## 明确选择与来源

```sh
python3 projects/138k/push2_workstation/usb_a/build.py \
  --prepare-usb2-soc --usb2-component workstation-input \
  --usb2-firmware-profile workstation --usb2-soc-output /tmp/usb2_input_new
```

可显式加 `--usb2-full-speed-only` 做 Host FS 诊断；不把成功回落当成物理 Push 验收。输入组件要求真实业务固件，不允许 probe 冒充。

准备流程选择 14 项原生 SoC RTL、11 项现有 owner／映射／显示及新装配 RTL，并从 `resource_rework_route0` 严格锁定基线读取四项既有支持源：事件 FIFO、反馈 CDC、Push MIDI 解码和字体。共 29 项；不读取私有历史暂存，不复制完整项目。`component_inputs.json` 绑定源、来源清单、支持源还原结果、ROM 和生成工程哈希。

只允许组件准备和综合；生成目录没有板级管脚、PLL 或部署授权。`workstation_integrated=false` 仍表示整机尚未集成，不能把 `input_owner_integrated=true` 解释为整机通过。

## 时钟与接口

| 接口 | 时钟／契约 |
|---|---|
| CPU、工作站服务、telemetry、取消计数 | `clk_cpu`，48 MHz |
| `performance_words_i[447:0]` | `FEEDBACK_AUDIO_DOMAIN=0` 时为 `clk_ref`，50 MHz；显式选择 1 时为原始 `clk_audio`，76.8 MHz。原 owner 的完整快照 CDC 搬到 CPU 域 |
| `display_meta_*`、`service_state_*`、score／playlist valid/ready、track launch/index | CPU 域，沿用现有 owner 端口；外部组合根负责必要 CDC，不能直接接另一个域的脉冲或总线 |
| `analysis_done_i` | 原 owner 内的同步路径保留，不在新顶层再复制业务状态 |
| USB3300 ULPI | `clk_ulpi`，60 MHz，数据／方向／握手由原生 SoC 管理 |
| `audio_valid_o/ready_i/event_o`、lifecycle／cancel | `clk_audio`，76.8 MHz，真实既有 FIFO／读端缓存 |

CPU 复位两拍释放，与 SoC 内释放对齐。传输会话失效异步置位、两拍 CPU 同步释放，仅用于输入服务资格；不复位工作站 CPU、停止音频时钟或改变采样调度。音频侧仍需要明确的 `audio_reset_n`。组合根必须实现真实时钟、跨域接口及板级就绪门禁。

音频事件位布局、内部 kind 15 接入／断开／PANIC／屏障以及背压均沿用原 owner；公共参数继续由 `workstation_session.sv` 和 `workstation_parameters.sv` 下游路径执行。本组件末端只有事件接口，不能据此宣称实际参数已经应用或 DSP 已发声。

整机组合沿用 `gw138k_usb_controlled_audio.sv` 的现有输入：将本组件的 `audio_valid_o/event_o/ready_i` 对接其 `usb_event_valid/data/ready`，并同时连接 `audio_lifecycle_o/cancel_o` 到 `usb_lifecycle/cancel`，不能只接 MIDI 数据而丢掉取消旁路。原生新板显式选择 `FEEDBACK_AUDIO_DOMAIN=1`，原始音频反馈只经过 owner 自身的一次完整快照 CDC；不先经过 UART 遥测快照再把旧副本计作新的音频回报。默认 0 的参考域接口保持兼容；不能把音频总线直接接到默认的 50 MHz 接口。显示／服务快照和 score／playlist 仍需正确域交接，不再实例化第二份 `push2_usb_a_control`。

## 服务适配与取消

`workstation_usb2_service_adapter.sv` 不保存业务参数，只保存一笔已捕获的服务请求。合法地址如下，均为字对齐；写操作要求完整四字节使能：

- 读：`00,10,14,18,1c,20,24,2c,30,34,38,3c,40,4c,58,5c,60,64,68,6c`。
- 写：`00,04,08,28,30,34,44,48,54,58`。

保留 `0x02000200` 地址窗，表内为低八位；`50` 历史预载、probe 的 `f0` 等不在白名单。未对齐、非法地址及部分写返回总线错误；合法访问只在原 owner 接受时完成，持续 valid 不重复提交。CPU 撤销请求后立即撤销 owner 选择，禁止总线超时后的迟到写入。

传输会话失效而 owner 仍 connected 时，适配器优先向原 owner 提交断开写 `00=0`。connected 直接取原 telemetry 位 1，没有第二份权威连接状态。即使 CPU 正等待 FIFO，旧输入队列也会经原 owner 复位并排空读端缓存，音频侧发出取消生命周期。

断开义务保持到原 owner 接受 `00=0`，不会因传输会话先恢复而撤销。请求捕获或等待期间一旦观察到会话失效，其接入写／原始 MIDI／通用 MIDI 就永久作废，不能在背压解除或下一次会话恢复后重新提交；新会话必须使用新的服务请求。两项锁存只记录待交付的取消义务，不复制 connected 真值，也不扩展 18-bit 事件布局。

会话无效时的连接写，以及无有效会话／owner 尚未连接时的原始 MIDI `04`、通用 MIDI `54`，完成为**已取消、不提交 owner**，不是总线故障；这避免一次正常热拔插永久污染 CPU sticky fault。这个 ACK 只表示请求已结束，不表示参数应用成功。CPU backend 仍须通过真实传输 generation／连接状态识别会话丢失。

`canceled_requests_o` 是 CPU 域 32 bit 饱和诊断计数：等待中的请求被 CPU 撤销，或上述过期请求被取消时各加一。复位清零，不自动清除真实 CPU fault。有效会话内的 FIFO 满仍背压；CPU 总线默认 480,000 拍（10 ms）超时会记录 sticky fault，不能声称已实现任意长下游停顿后的自动恢复。

## 验证边界

```sh
GW138K_USB2_INPUT_EVIDENCE=/tmp/usb2_input_evidence_new \
  python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_input.py -v
```

证据目录必须不存在。完整测试需要 GNU bare-metal RISC-V 工具链、Icarus、Verilator 和 `gw_sh`；缺少 Gowin 时综合用例显式 skip，不能报告完整八项全部通过。测试执行实际业务 CPU、原 owner／FIFO／CDC 和实际 25K MIDI／PL RTL；音频端仍是带背压的事件检查器，LCD 仍是 tile 完成模型。该测试不能替代真实参数提交、DSP／串行输出、LCD 物理驱动、电气门禁、P&R、上板验收或 Flash 冷启动。

Push 的 CPU／ULPI 回归另用仿真专用端点模型，不把 25K 描述符改成 Push，也不修改 vendor PHY／SIE：

```sh
GW138K_USB2_PUSH_EVIDENCE=/tmp/usb2_push_evidence_new \
  python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_push.py -v
```

默认 HS／FS 场景分别保存在新建的 `hs_1`／`hs_0` 子目录，拒绝覆盖已有子目录。模型使用合成的最小设备／配置描述符和 EP1 OUT 屏幕、EP2 IN／OUT MIDI，不是实物 Push 描述符或设备实现。生产 CPU 不复位，验证持音拔线、硬件会话断开、重新枚举、同一 pad 再触发及部分屏幕帧从新 header 恢复；每速率检查 5 个真实 owner／FIFO／CDC 映射事件。另一个 HS 用例保存在 `hs_1_complete_frame`，等待重连后的完整 16 字节 header／327680 字节像素和生产 CPU 的帧完成提交；这里只校验传输的长度、CRC、MPS、toggle 和完成顺序，不核对独立图像参考或真实屏幕。原始部分帧记录见[Push peer 回归记录](../../reports/USB2_HOTPLUG_PUSH_PEER_20261027.md)，完整帧结果另见[交替接入记录](../../reports/USB2_MIXED_HOTPLUG_20261027.md)。

同一个持续运行的 CPU、主机和 USB3300 模型下，25K／Push／25K／Push 的交替回归为独立入口：

```sh
evidence="$HOME/.cache/fpga-usb2-hotplug/run_new"
mkdir -p "$evidence/tmp"
TMPDIR="$evidence/tmp" GW138K_USB2_HOTPLUG_EVIDENCE="$evidence" \
  python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_hotplug.py -v
```

每种速度在单次执行内完成四次接入、三次断开，断言 CPU 不复位、设备模式自动切换、两次 25K PL 会话及 tile 坐标重新开始、Push 帧重新发送 header、精确 10 个映射事件及四次默认初始化生命周期／屏障。25K 使用真实 MIDI／PL RTL，Push 仍为上述仿真端点，LCD 完成和音频事件接收仍是模型；不以此宣称实际参数已经提交、DSP／串行音频连续、实物 HS 能力、屏幕恢复或硬件验收。该交替用例只接收 Push 的部分帧，完整帧由独立 HS 用例验证，不能将不同用例的范围混写。
