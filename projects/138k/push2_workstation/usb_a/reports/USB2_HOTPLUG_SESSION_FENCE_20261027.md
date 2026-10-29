# USB2 热插拔会话围栏：源码与离线验证

日期：2026-10-27。开发记录身份：`usb2-hotplug-session-fence-20261027-dev1`。
源码基于 `128d5cfee72d70160e584c33ee2bf35d39f3a90c` 加当前工作区差异；不是发布候选或板上版本。

## 目标与本轮修正

目标仍为：修正新底板电气连接后，完成同一 USB2-A 口上 25K 与 Push 的交替接入、热拔插和业务恢复。不假定两设备同时连接，也不将允许 HS 协商等同于实物已经使用 HS。

电气旁路采用 `pinout.json` 的 U4／U5 `not_fitted_short` 声明，仍未实测 USB3300 ULPI IO 的 3V3 供电。本轮不改锁定网表、球位、电气约束或 accepted/pinned 构建选择。

服务适配器原来仅根据当前 `session_valid_i` 判断过期：请求捕获时会话无效而随后恢复，旧接入写可能重新提交；已连接 owner 的断开写也可能在背压期间因会话先恢复而被撤回。新增定向场景首先在旧实现复现了旧接入写复活。

修正位于 `rtl/workstation/workstation_usb2_service_adapter.sv`：

- 捕获或等待中的请求观察到会话失效后，接入写／Push 原始 MIDI／通用 MIDI 永久作废，以取消完成，不制造 CPU 总线故障。
- 断开义务保留到原 owner 接受 `00=0`；传输恢复不能使旧连接跳过断开。
- owner 的实际 connected 仍来自 telemetry；新增锁存只代表撤销／交付义务，不建立另一份连接或公共参数真值。
- 不改 18-bit 事件、PANIC、PL 线规、音频采样调度或 CDC／时序约束；新会话使用新的请求。

## 来源身份

| 文件 | SHA256 |
|---|---|
| `rtl/workstation/workstation_usb2_service_adapter.sv` | `e79f56c7cf515171aaa537c4dbc0e4cd39d09aceaa82bb36a65e50e1f6f2aaff` |
| `sim/usb2/tb_workstation_usb2_service_adapter.sv` | `076682e9ef84f04571275187e2133ad82f8ec68094196e193462960f0dc95df0` |
| `sim/usb2/test_workstation_usb2_firmware.c` | `85919544d6d57efbf0288ef414f36d06d3fe23735b60546647b3422923c5fcab` |

## 实际验证与边界

| 检查 | 结果 | 证明范围 |
|---|---|---|
| 服务适配器 Icarus 仿真 | 129 checks 通过 | 精确一次交接、非法访问、撤销、短暂失联、背压期间断开保持、旧接入／两类 MIDI 作废、新请求恢复 |
| 实际 RV32I 生产固件＋owner／FIFO／CDC＋真实 25K MIDI／PL RTL | HS、FS 两场景通过 | 每场景 136 个音频事件、20 个旧事件丢弃、硬件断开／重连与 PL；音频接收端仍为事件检查器，LCD 为完成模型 |
| 生产固件函数的 C ASan／UBSan 测试 | 通过 | HS512／FS64 完整 Push 帧、像素 XOR、NAK／PID；25K↔Push 交替、速度变化、重复 IN、半帧拔线、PL 暂存清理、枚举失败重试 |
| 原生 backend C ASan／UBSan 测试 | 通过 | HS／FS 容量、toggle、重复包、NYET／PING、控制复位、generation 和计时器 |
| Host port／组合链路／停钟监督 | 3 测试通过 | 15940／3115／223 checks，HS chirp、FS 回退、去抖、恢复、会话隔离及故障注入 |
| Gowin 原生输入组件综合与独立门禁 | 通过 | 38 SDPB＋1 SDPX9B，39 synthesis BSRAM、3892 registers（门限 <4096）、16384 个 ROM 字；ROM／资源／来源篡改拒绝 |
| accepted 来源边界／pinout | 10／32 测试通过 | 不切换旧整机来源；旁路语义和位置规划继续有效 |

Push／25K 交替的 C 测试调用生产 `connect`、`poll_midi`、`frame` 等函数，但 USB 传输、设备枚举和描述符为模型，不能据此宣称实际 Push 已经经过 RV32I／ULPI 链路或完成实物热插拔。真实 25K 的 RTL／CPU 场景与该模型测试分别记录，不能合并冒充实物闭环。

实际 CPU 场景的本机证据保存在 `/tmp/ulpi-hotplug-input-20261027-135719/hs_1/` 与 `hs_0/`，含源哈希、ROM、编译／执行日志和 `input_evidence.json`；两场景的来源、暂存组件和准备输入一致性均为 true，hardware／deployment／release 均为 false。

完整输入组件八项用例中，七项通过，一项 lint 断言失败：用例只允许一条 native `SYNCASYNCNET`，当前 Verilator 返回 `host.cpu_reset_n` 与 `host.usb.bridge.cpu_session_ready` 两条。单独以 HEAD 的原服务适配器替换暂存副本后，两条诊断完全相同；没有修改源文件、禁用告警或放宽断言。对照结果保存在 `/tmp/ulpi-hotplug-lint-comparison-20261027.json`。

上一轮完整新板综合用例还有未修改的资源快照不匹配。本轮没有改写该快照或把输入组件综合替代完整整机／物理验收。新增 RTL 后，旧整机网表、P&R、STA 或位流证据也不能自动代表当前源码。

## 复现

从仓库根目录执行；证据目录必须尚不存在：

```sh
GW138K_USB2_INPUT_EVIDENCE=/tmp/usb2_hotplug_input_new \
  python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_input.py -v
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_application.py \
  NativeApplication.test_production_push_frame_packetization \
  NativeApplication.test_transaction_adapter_bounds_toggles_and_nyet -v
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_ulpi_link.py \
  PhysicalLink.test_high_speed_host_port_and_full_speed_fallback \
  PhysicalLink.test_supervised_host_composition_and_runtime_handoff \
  PhysicalLink.test_clock_supervisor_without_a_running_phy_clock -v
```

第一条完整输入套件仍会暴露上述既有 lint 断言失败，不应报告全部通过。

## 未完成与回退

- 后续已补生产 CPU／ULPI 对仿真 Push peer 的 HS／FS 拔插恢复，见[独立记录](USB2_HOTPLUG_PUSH_PEER_20261027.md)；同一 CPU 下两种 peer 交替和独立 Push 重连完整帧见[dev3 记录](USB2_MIXED_HOTPLUG_20261027.md)。仍缺真实 Push 设备交互，以及物理 Push／25K 的连续交替、持音拔线、屏幕恢复和音频连续性验收。
- USB3300 ULPI IO 供电仍须实测；后续记录已补当前源码完整综合及独立审计，完整 ULPI 电气属性、P&R／路由时序／CDC／PLL／物理资源门禁仍须分别完成。
- `bitstream_sha256=null`、`hardware_accepted=false`、`sram_deployed=false`、`flash_deployed=false`；本轮未调用 programmer 或操作板卡，不更新 latest／部署身份。
- 源码回退只撤销本轮服务适配器的两项锁存和对应测试／说明；保留此前电气旁路修正及他人 HDMI／资源报告。此回退无需编程板卡，不能用整目录 reset 覆盖工作区。

目标保持进行中；本记录不是热插拔功能的实体完成声明。
