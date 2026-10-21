# 新板 USB2 Host 端口与 25K HS／FS 协商

日期：2026-10-22。承接 [全范围 bring-up 清单](CUSTOM_BOARD_BRINGUP_20261022.md)。本轮实现真实 Host 端口控制并连接现有 ULPI 平台，与仓库现有 25K CDC 设备核做双端计时回归，**不把 PHY 协商当成完整 Host／MIDI／PL 或实体上板完成**。

## 1. 身份与构建范围

开发源码快照：`custom_138k_usb2_port_dev_20261022_v1`。起点提交仍为 `45e7b4870b57372578a967d284c9cf4b09d1bae0`；与 ULPI 初版标识、pinout v2 标识及历史接受的 UserCode 分开。本轮新增输入由包含本报告的提交归档，尚未选入完整工作站构建。

| 路径（相对 `usb_a/`，25K 路径另列） | SHA256 |
|---|---|
| `rtl/usb2/workstation_ulpi_link.sv` | `0138a87ca4afa33854f0c72ea13f2dea6f212e99d3053d0fbefe44072e1fc5bb` |
| `rtl/usb2/workstation_ulpi_supervisor.sv` | `9741276485cc6393e7786bb7ca5886d719f120e810839fe9aa2078a723b2a840` |
| `rtl/usb2/workstation_usb3300_host_init.sv` | `546d0d2ee624dc4ecb2551273c27b9cba5e48c2d81d16dadce13c43e16fc4dbe` |
| `rtl/usb2/workstation_usb3300_host_link.sv` | `9992615d19aa187e5afe3018c9f55b6480f548653cc29a1af98ef8267a51c99b` |
| `rtl/usb2/workstation_usb2_host_port.sv` | `29d267e61a71ef572a96eb35f1877ad032bcaab9f72f225d00315de3e47b44e7` |
| `rtl/usb2/workstation_usb2_host_phy.sv` | `e81fa7ddf66fd1c6c80df3ea88b5acfc5e7f807b6490868551a68bfcd5cf1e38` |
| `sim/usb2/usb3300_register_model.sv` | `19c808ad5a28fb5977ca995f9c6e0c067fe178a06d96967b3ecf04f382b9d9ce` |
| `sim/usb2/tb_workstation_usb2_host_port.sv` | `38185d09ef2455d4516a4eff296d1abad92900de5a4fbad6c029875acc987f46` |
| `sim/usb2/tb_workstation_usb2_25k_negotiation.sv` | `7d70b2ea6bca043dd762046553ea965fc3297f850e6b4c064c30df621e5ba8cc` |
| `sim/test_workstation_ulpi_link.py` | `768cff86f92291d5fe5dcd49437892bd8ccff21b7fbc4d93863e27da4565c984` |
| `projects/25k/prj/usb2_device/hs/usb_cdc_core.v` | `35863cea6652980a22e8d741e9148a93928dcc2ddf7a7013cf4e479b7267f338` |
| `projects/25k/prj/usb2_device/sim/tb_usb2_hs_control.sv` | `c2a6a59ff0b9c53f355f96e7b9699022552a5b61d122d41121de35fa37d079c5` |
| `projects/25k/prj/vendor/ultraembedded_usb_hs/UPSTREAM.json`，未改 | `06d978f6ff82d36797b8ffef1fa5ec3b52aef40e629760b7cb777a754fad9a67` |

六个 Host 模块均为第一方原生 RTL；端口模块拥有 PHY 配置，平台组合仅做连接／复位／所有权与安全隔离。25K 仅修改已版本化的第一方 CDC 适配及其回归，不改 vendor／原始清单／旧位流／历史验收。25K 支持模块直接来自原锁定上游，回归和原构建准备均检查原始 SHA256。

`build.py --prepare-pinout` 保持 pinout-only；accepted full83、timing85、资源时序候选未改为新板或新 USB 来源。无新 UserCode、无位流、无 Gowin 整机综合／P&R、无 SRAM／Flash 部署。旧 `6E78` 等 25K 实板身份也不能用于本轮改过的输入。

## 2. 协议与实现

主要依据为 USB 2.0 §7.1.7.5／§7.1.7.6、ULPI 1.1 §3.8.2.1／§3.8.5.1 和 USB3300 DS00001783C §6.1.7／Table 6-8。相关页面已渲染核对，不从二手教程推断电平或位域：

| 原始资料 | 本轮核对身份 |
|---|---|
| USB-IF `usb_20_20250603.zip` 内 `usb_20.pdf` | `d39698a33486c399124af92bd02e4f978fd9a836b5cf4e52e6e4633eb1d89f61` |
| 原始 ULPI Revision 1.1，2004-10-20，`ULPI_v1_1.pdf` 镜像 | `b329c5a763f11674717a369001cdc0c25226034d86942ce26b561e0db33a2a5f` |
| USB3300 DS00001783C | `33e73e37f5110cb9e3ef66ccf8c7fdd4a16593c7b1afcff0c5df523e41963a9e` |

来源：USB-IF `https://www.usb.org/document-library/usb-20-specification`，原始 ULPI 文档镜像 `https://cdn.sparkfun.com/assets/4/3/e/3/2/ULPI_v1_1.pdf`，Microchip 原厂 `00001783C.pdf`。外部手册不作为构建依赖，不复制进生产输入。

实现顺序为：

1. PHY 初始化／自检成功后，端口写／读 Function `45h` 并读取 Debug `15h`；正常 FS Host 使用 TERM=1，不能把初始化的 power-up `41h` 直接称作已配置 Host。
2. 连续 J 去抖，默认 100 ms；接入抖动重计时，LS 单独报告且不执行 HS 协商。
3. 写／读 `50h` 开始根端口 SE0／raw 模式，至少 50 ms。设备 K 连续 2.5 µs 才有效，T0+7 ms 仍未结束或禁止 HS 时回退 FS。
4. 合格 K 结束后在 90 µs 开始预算内启动一个连续 NOPID train，K=`00h`、J=`FFh`，每段 50 µs，不在段间插 Idle／STP；一直持续到总复位结束前 100–500 µs。
5. 停止后等待新的 SE0 RXCMD 证明管线排空，再写／读 `40h`；不是使用旧线态快照立即改 OpMode。复位总时间到达后才交接正常 HS。
6. 没有有效设备 chirp 时，在完整复位之后写／读 `45h` 并确认设备状态，保持 FS。两种速度均先允许 SOF，再等待 10 ms 才开放普通事务。
7. 断开／软件复位均建立取消边界；软件复位先停止新调度，再有界等待 MAC idle，不中途剥夺在途包的 PHY 拥有权。失钟、CSR 超时／错误、读回漂移、raw train 背压／排空异常都有独立失败位置和 DATA 高阻／STP 高隔离。

原链路 1 ms 看门狗会错误截断长达数十毫秒的合法 Host chirp，故增加**独立且有界**的 60 ms NOPID 时限；普通包及 CSR 仍为 1 ms。新增 `rxcmd_valid_o` 表示新 RXCMD，即使饱和计数器不再变化也可消费状态。不是放宽普通包／CPU 超时来掩盖错误。

接口、错误码、时钟域和复现命令见 [模块说明](../rtl/usb2/README.md)。`sof_enable_o` 仅为调度许可，不能当作已发送 SOF；`session_reset_o` 仅为待集成的本地边界，不更改 USB PL 或 18-bit 事件契约。

## 3. 双端联调发现的 25K 问题

锁定 vendor SIE 用 15-bit SE0 计数器的 bit14 判断复位，60 MHz 下只需 16,384 拍，约 273 µs。25K HS 适配此前直接复用它，既可能在合法 100–500 µs chirp 尾段回到 FS，也可能让不足 3 ms 的 HS 空闲清掉已提交地址／配置。

修复位于第一方 `hs/usb_cdc_core.v`：

- HS 连续空闲以 180,000 拍（3 ms）为边界。仅在进入 vendor SIE 的 reset-detection LineState 路径增加 guard；不篡改真实 RX data／active／valid／error，不改 vendor SE0 计数器。
- 根据锁定 SIE 的 16,384 拍门限，guard 先遮蔽 163,616 拍，使最终复位判定不早于 3 ms。线上非空闲或离开 HS 即清零。
- HS→FS 复位检查不再受“自上一轮 T0 已经 10 ms”的无关条件限制。切回 FS 后保留至少 100 µs 检查窗口，再开始原 1.1 ms 设备 K；原完整 3 ms 冷启动复位检测不被缩短。
- 不宣称补齐 suspend／resume／LPM 或功耗状态；这轮证明的是合法短空闲保持与明确的热复位／重新枚举路径。

负对照使用原 `HEAD` CDC 文件（SHA256 `a6260bcbeb7418142a82aaa066b8c2030f0f7d7a3f42cadc8b4fdca054f16b21`）搭配新增相同测试：实际在地址／配置后的 500 µs HS 空闲处失败，报 `legal 500us HS idle cleared device state`。修复后相同检查通过，随后还经真实 SIE 完成热复位、重新协商和新描述符读取；不是只让状态位符合预期。

## 4. 验证结果与边界

USB 回归新增／扩展到 7 个 Python 测试入口（双端联调包含 HS／FS 两个子场景），分组执行通过：

| 范围 | 已观察证据 |
|---|---|
| 原 ULPI 物理总线 | 10,176 次检查、17 次复位；含普通超时、NOPID 独立有界超时、PID 撤回、全部 Scratch／RX 字节、514 字节 TX、RXCMD 与抢占 |
| 初始化／失钟／运行期交接 | 原 19／4／5 场景仍通过，分别为 3,762／223／3,115 次检查 |
| Host 端口快速故障矩阵 | 15,940 次检查、14 场景；HS／FS、禁止 HS、去抖／LS、CSR 漂移／超时／重试、开始／raw 背压／排空失败、断开／软件复位／MAC 无法静止／失 PHY |
| 实际六模块 Host＋真实 25K HS CDC 核 | 默认 60 MHz、50 ms 根复位和 10 ms recovery；3,666,025 拍、2,736,000 个物理 NOPID 数据字节、912 个完整 K/J 段；双方均为 HS，配置读回 `40h`，无 link fatal／争用 |
| 同一组合＋真实 25K FS CDC 核 | 3,607,530 拍；双方为 FS、配置 `45h`，没有 Host chirp 或伪造 RX 数据 |
| 25K 真正的包级控制／数据回归 | 保留描述符限长／qualifier／other-speed、SET_ADDRESS 状态 ACK 后提交、配置／CDC、512 字节二进制 SIE 回环；另通过地址／配置跨 500 µs 空闲保持及 3 ms 热复位／重新枚举 |

快速矩阵使用缩放计时，只作故障覆盖。双端真实计时仅将接入去抖缩为 100 µs 以节省等待；**50 ms 复位／50 µs K/J／100–500 µs 尾段／10 ms recovery 均未缩放**。

联调模型抽象 USB3300 寄存器、ULPI 时序、线态与保活活动。25K 使用真正 CDC／SIE RTL，不强制内部状态；但 recovery 的 SOF 活动由独立模型提供，尚不是 138K MAC 发出的完整 SOF token。因而该测试证明端口计时与双端协商，不证明 138K Host 的枚举、PID／CRC／重传、端点或业务传输。25K 设备侧包级测试不能越界当成 Host 侧通过。

Verilator 5.046 对六模块 `workstation_usb2_host_phy` 执行 `--lint-only -Wall` 零警告。Yosys 0.67+post 的 `hierarchy -check`、通用 `synth`、`check -assert` 通过，通用映射 3,060 cells；这不是 Gowin LUT／BSRAM／时序，也不是带真实 I/O 的 P&R。

25K `usb_cdc_core` 与同一锁定支持源也通过 Yosys 层次检查、通用综合和 `check -assert`，显式参数 `USB_SPEED_HS=32'h54727565`（字符串 `True`），通用 2,672 cells，保留上游仿真用 `$print`；不冒充 Gowin 25K 资源／时序结果。

原入口另通过 pinout 25、current sources 10、firmware 6、`GW138K_VERIFY_CLEAN_PREPARE=1` baseline 23 项，共 64 项。与 USB 的 7 个入口合计 71 项 Python 测试，分组验证；不改旧输入策略，不将这些数字解释为硬件验收。

复现全部 USB 回归（含约两分钟真实计时仿真）：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_ulpi_link.py
```

单独快速矩阵或 25K 真实控制／热复位：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_ulpi_link.py PhysicalLink.test_high_speed_host_port_and_full_speed_fallback
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_ulpi_link.py PhysicalLink.test_existing_25k_control_and_warm_reset
```

## 5. 剩余实际交付

1. Host MAC／SIE 仍要实现 HS inter-packet／response 定时、真实 125 µs SOF、512 字节事务的 FIFO／CRC／重传及错误回滚。旧 FS Host `USB_CLK_FREQ=60 MHz` 仍不能满足这些要求。
2. 138K CPU／MMIO 时钟与端口状态／软件复位要显式桥接。`session_reset_o` 要接回现有生命周期；不另建公共参数或篡改 18-bit 事件。
3. 25K MIDI_KEYBOARD 尚未将 MIDI／PL 描述符及端点接到 HS 物理后端。现有 CDC 联调不是 MIDI／PL 完成；后续保持原 VID/PID 与协议契约，并验证 FS Push 回退、拔插和 PANIC。
4. 完整原生新板配置与电气约束、DAC 型号对应驱动／安全启动、HDMI 四 lane 极性与 CEC、TF 真卡、蓝牙新板接线／实际服务仍按全范围清单推进，没有因 USB 进展消失。
5. USB3300／电平转换器的 [电气阻断](CUSTOM_BOARD_PREFLIGHT_20261022.md) 未解除；未上板、未写 SRAM／Flash，也没有新部署身份。固化必须在真实新板候选、离线门禁和实体读回／现象验收后独立进行。

回退：不选择新六模块即保持旧工作站构建；25K 可回到起点提交的第一方 CDC／回归源码，不覆盖 vendor 或已有验收文件。后续任何含本轮变更的整机／25K 构建须新源清单、输入哈希、配置、新 UserCode 和位流身份，不继承旧验收。
