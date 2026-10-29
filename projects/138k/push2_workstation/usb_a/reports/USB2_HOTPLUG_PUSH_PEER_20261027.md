# Push peer：生产 CPU／ULPI 热插拔离线回归

日期：2026-10-27。验证身份：`usb2-hotplug-push-peer-20261027-dev2`。这是仿真记录，不是发布候选、板上版本或硬件验收。

## 来源与配置

本次增加仿真专用 Push peer、集成 bench 和测试入口；生产 RTL／固件沿用[会话围栏修正](USB2_HOTPLUG_SESSION_FENCE_20261027.md)。工作区 HEAD 核对为 `a579eec259a0190d45abcc7e4c0bd4a0e7b5df15`；实际参与执行的输入另由组件 manifest 和下列哈希绑定，不以并行任务的 HEAD 或 latest 指针代替来源身份。

| 新增来源 | SHA256 |
|---|---|
| `sim/usb2/usb_push_device_model.sv` | `f7cd9196cb5a7ec9187a557eca25c6ec027eab0d1b6ba42bb635abe815472b8f` |
| `sim/usb2/tb_workstation_usb2_input_push.sv` | `0114c2815c0d0194eb25231168008face398851bff366ea587ff7fa7f7c73c98` |
| `sim/test_workstation_usb2_push.py` | `c1cecca7c2e2ea0e84b86cd99c772bc45cacb26fd61c23518f56fd4353d22d38` |

该表绑定 dev2 执行时版本；后续 bench／入口的完整帧增量及新哈希见[dev3 交替记录](USB2_MIXED_HOTPLUG_20261027.md)，不倒改原执行哈希。

测试沿用 `prepare(... firmware_profile='workstation', component='workstation-input')`，HS 允许协商，FS 显式关闭 HS。执行真实 RV32I 业务固件、USB2 主机／ULPI、原 `push2_usb_a_control`、事件 FIFO 和 CDC，未用 C mock 替代 USB 传输或枚举。

peer 不是实物 Push：控制器为仿真代码，描述符是合成的最小 USB 设备／零接口配置，按既有固件分支提供 VID `2982`、HS PID `1967`／FS PID `9999`。复用 25K 版本化工程中的原字节 PHY、RX／TX SIE 和 CRC16，不能据此推断 Push 内部硬件实现。EP0 处理枚举，EP1 OUT 接收屏幕，EP2 IN／OUT 接收／发送 USB-MIDI；地址、配置及 IN 数据释放等待状态 ACK，OUT 按 CRC、MPS 和 toggle 检查，重复 OUT 不重复提交。

## 实际执行结果

```sh
GW138K_USB2_PUSH_EVIDENCE=/tmp/usb2_push_evidence_new \
  python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_push.py -v
```

本机实际执行目录：`/tmp/ulpi-push-input-20261027-145205/hs_1/`、`hs_0/`。两个场景分别执行，均退出 0，包含完整暂存源码、ROM、编译／执行日志及 `push_evidence.json`。

| 证据 | HS | FS |
|---|---|---|
| ROM SHA256 | `31c4d7d58141ef0ec2b33f826a9c22251b7d4f23771cbaa189427b0f1277d457` | `80a3415b6c89de06f359b268e14b7e826c14f6dd34ea54ddad4739ecf422aa41` |
| 组件 manifest SHA256 | `a3e7f37241973d056e8886da01b2735e1e6dc1cad4f105dde2d3cb03d11063e8` | `384ab5818e933ecf33d53b9ba70591b0aa629afeaed3a60c882ffada701e3cd9` |
| 执行日志 SHA256 | `dc19a3777e457d84f246d0ec450e9ecc3e4deb081a1e51f65c6a1f23b1ea4447` | `f0ead147fc1239eb57ae99bf988c39988e82f283f19e41b0bcb3f1633ebbf49e` |
| 执行结果 | PASS；5 个映射事件 | PASS；5 个映射事件 |

每场景实际验证：

- CPU 在第一次接入后完成 pad 36 的 On／Off；屏幕已经收到 header 和至少 1024 字节时再注入 pad 37 On，证明部分帧传输期间仍轮询 MIDI。
- pad 37 保持按下时拔除模型设备；真实主机传输会话失效，owner 断开并经原音频接口交付断开生命周期，不复位生产 CPU。
- 重新接入并从地址 0 枚举到地址 1；原 held 状态已经清除，同一 pad 37 可以再次 On／Off，不重复提交旧 MIDI。
- 新会话必须重新发送正确的 16 字节屏幕 header，随后接收至少 1024 字节新部分帧；模型拒绝无 header 的续传、CRC／MPS 错误及超出完整像素长度的传输。HS 像素包 512 字节，FS 为 64 字节。
- owner 原始 MIDI 写入精确 5 次，audio 端精确收到 5 个既有 18-bit 映射事件；两次 attach／初始化屏障、一次 detach，带背压时数据保持稳定。

两次执行的原始输入、仿真暂存副本、组件暂存输入、prepare 输入一致性检查均为 true；`hardware_tested=false`、`full_frame_validated=false`、`deployment_allowed=false`、`release_ready=false`。

本轮另复跑服务适配器 129 checks、生产固件／backend 两项 C ASan／UBSan 测试、pinout 32 项、custom-board 9 项、implementation 17 项、accepted 来源边界 10 项，均通过。完整 native 综合回归 1 项仍因历史资源精确值断言失败，详见下节；不能据通过项宣称所有回归全绿，不删断言、不修改历史期望掩盖差异。

## 电气旁路边界

锁定的三个外部网表再次按固定哈希校验；101 个端口记录、`retired_ports` 和生成 CST 与 HEAD 原 resolver 输出相同，ULPI 仍使用 `carrier.ball(high, 2)`。U4／U5 `not_fitted_short` 声明下，B 侧名义 3V3 检查为 `no_voltage_domain_conflict_detected`，`actual_board_measured=false`、`full_electrical_acceptance=false`。本项唯一待实测的是 USB3300 ULPI IO 是否确由 3V3 供电；未新增 CST 或补写 `IO_TYPE`。

## 当前源码完整综合与独立审计

旧综合产物因会话适配器源码哈希变化而被拒绝，未用修改证据或忽略漂移的方式复用。重新用三个锁定外部网表准备、综合当前原生整机：`/tmp/ulpi-bypass-current-20261027-145657/native/`。Gowin 实际综合退出 0，独立 `workstation_custom_board_audit.py` 退出 0；配置身份仍是开发配置 `custom138k-native-integration-20261027-a26`，本次具体输入／产物以新哈希区分，不继承旧候选或板上身份。

| 实际产物 | SHA256 |
|---|---|
| `integration_inputs.json` | `72febe9b24708f0f6c3f76207d28e95d1c461c24ddd54c5934d39311a297cd46` |
| 综合网表 | `bbc28c7d162804cf167ba541aeb0d263a781033167ecd6137bf596a01babe176` |
| 综合日志 | `9136d049984a5c7551ad7feb49e56e1556577fcced552bdb99b0da03bf2e1758` |

审计输出为同级 `audit.json`／`audit-cli.json`。电气状态为 `no_voltage_domain_conflict_detected`、`electrical_blocked=false`，但 `release_ready=false`。对篡改 blocked 标记、非法状态、状态与标记不一致、伪造实测和完整电气验收的五个负例均拒绝；修改只发生在临时生成元数据，检查后恢复原字节，外部锁定网表不变。

综合资源实际值为 Register 54183、Lut 73623、Alu 15292、Bsram 272、Ssram 419；Bsram 是综合口径，不是物理布局布线验收计数。完整综合测试原来精确要求 57037／76650／15325／274／371，因此在资源断言处失败，后续该用例的其它负例未执行。本节独立执行的五个电气负例不冒充完整测试通过。此前旁路 resolver 对照已证明 230 个编译输入与 HEAD 原 resolver 字节一致，证据为 `/tmp/ulpi-bypass-offline-20261027-AGr64Q/compiler-input-comparison.json`；后续会话围栏 RTL 本身改变了少量逻辑，不能沿用旧综合网表作其验证。

复现当前缓存产物审计和明确保留的失败：

```sh
PYTHONPATH=projects/138k/push2_workstation/usb_a \
  python3 projects/138k/push2_workstation/usb_a/tools/workstation_custom_board_audit.py \
  /tmp/ulpi-bypass-current-20261027-145657/native
GW138K_CUSTOM_SYNTHESIS_INPUT=/tmp/ulpi-bypass-current-20261027-145657/native \
  python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_custom_board_synthesis.py -v
```

## 剩余缺口与回退

- 后续 dev3 记录已补同一个持续运行的生产 CPU 在实际 25K RTL peer 与此 Push peer 之间的 HS／FS 四次交替；仍不是实物设备验收。
- 本 dev2 集成仿真只接收部分屏幕帧；dev3 已另验证独立 Push 重连后的 RV32I／ULPI 完整 327696 字节帧，仍不证明交替场景完整帧或真实图像恢复。不同用例不能拼接冒充设备验收。
- 仍缺实物 Push／25K 的 HS 能力、交替拔插、持音清除、屏幕恢复、真实 DSP／串行音频连续性，以及独立的电气、P&R、路由时序、CDC／PLL 与物理资源门禁；通过综合和综合网表审计不替代这些阶段。
- 未操作板卡、SRAM 或 Flash，`bitstream_sha256=null`、`hardware_accepted=false`、`sram_deployed=false`、`flash_deployed=false`。不更新 accepted、latest 或部署索引。
- 这些文件均为离线验证输入，不进入生产源清单；回退只移除上述三个仿真文件及文档入口，不回退电气旁路或会话围栏，不影响并行 HDMI／DDR 任务。

目标继续进行中；本轮新增的实际 CPU／ULPI 证据不能替代未完成的实体闭环。
