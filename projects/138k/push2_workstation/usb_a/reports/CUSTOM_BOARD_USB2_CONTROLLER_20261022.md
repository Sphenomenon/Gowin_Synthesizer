# 新板 USB2 原生控制器离线验证

日期：2026-10-22。开发身份：`custom_138k_usb2_controller_dev_20261022_v1`。基于 `b593a390fd495a782f7bf3c6756ea5af40399ae8`，承接 [MAC 阶段快照](CUSTOM_BOARD_USB2_HOST_MAC_20261022.md)。本记录随源码提交；不是整机候选、硬件验收或部署身份，没有新 UserCode、位流、SRAM 或 Flash 操作。

## 来源与配置

显式采用 `rtl/usb2/` 中的八个第一方模块，顶层为 `workstation_usb2_host_controller`。未改变 accepted full83、timing85、resource-timing 的输入选择、冻结基线或 vendor 字节。以下路径相对 `projects/138k/push2_workstation/usb_a/`：

| 输入 | SHA256 |
|---|---|
| `rtl/usb2/workstation_ulpi_link.sv` | `0138a87ca4afa33854f0c72ea13f2dea6f212e99d3053d0fbefe44072e1fc5bb` |
| `rtl/usb2/workstation_ulpi_supervisor.sv` | `9741276485cc6393e7786bb7ca5886d719f120e810839fe9aa2078a723b2a840` |
| `rtl/usb2/workstation_usb2_host_controller.sv` | `fef42fd02e74c27629d5efbdbb9957a079198ab0588751a621f3df9d6dadf33d` |
| `rtl/usb2/workstation_usb2_host_mac.sv` | `d73e34695d3fbf7be0ef81423232f093df34fa9bdd11d98ee77b16572622168b` |
| `rtl/usb2/workstation_usb2_host_phy.sv` | `d88814938e3d0bb181a2397585ad480255b5b3ebaa670d5925f91ded6c893688` |
| `rtl/usb2/workstation_usb2_host_port.sv` | `29d267e61a71ef572a96eb35f1877ad032bcaab9f72f225d00315de3e47b44e7` |
| `rtl/usb2/workstation_usb3300_host_init.sv` | `546d0d2ee624dc4ecb2551273c27b9cba5e48c2d81d16dadce13c43e16fc4dbe` |
| `rtl/usb2/workstation_usb3300_host_link.sv` | `9992615d19aa187e5afe3018c9f55b6480f548653cc29a1af98ef8267a51c99b` |
| `sim/test_workstation_ulpi_link.py` | `1732330b8198511533922419822af436f8eeb58d088ae7ce7133855ce7baf256` |
| `sim/usb2/tb_workstation_usb2_host_mac.sv` | `88ed2f4dd10e8532b63d41f3d4340033d8d84493085a155861c498c9791ef923` |
| `sim/usb2/tb_workstation_usb2_mac_25k.sv` | `58dafebbaddf550ea47c0597197bf6b65997de189f26a18e8e2fcfb4770db58c` |
| `sim/usb2/usb3300_host_model.sv` | `f763b935daf2de0f4433dfa513d24fe5406d62258c701e52797003c8c0827c37` |
| `sim/usb2/usb3300_packet_model.sv` | `5a474d54dabc06b9e3db0a6d3e4e189473c17a09d2b88a3bb4403b973b7ef637` |

参考时钟 50 MHz，ULPI 60 MHz。默认上传／包阶段看门狗均为 60,000 拍。原生组合仿真只将接入去抖缩为 100 µs，保留 50 ms 根复位、10 ms recovery、真实 SOF 和正常 HS／FS 包间隔。逻辑／物理 MAC 故障矩阵的上传／包看门狗分别为 1,024／4,096 拍，不缩放 SOF 或响应窗口。

## 本轮修复与边界

- `host_controller` 原生组合 PHY 与 MAC，CSR 配置仍只归端口状态机。命令、上传、结果和接收接口均为 ULPI 域；不暗接旧 48 MHz CPU。
- 原生仿真发现 MAC fatal 在 PHY 撤销事务复位后可能短于参考域采样周期。MAC 现在用独立 `fault_reset_n` 锁存故障，普通事务复位不能清除；控制器立即释放 DATA、拉高 STP、隔离握手及 SOF／事务许可，并跨域锁存。只有显式关闭外部 enable 或全局复位清除，不自动循环重启。
- 同链路模型从实际 ULPI DATA／DIR／NXT／STP 重建包，连接仓库真实 25K CDC／SIE；设备 PID、CRC、ACK、地址提交及 payload 不由测试替代。
- FS 模型曾将尚未获 PHY 接收的设备响应合并入前包，导致 ACK 间隔检查失败。修复模型的响应授权与 EOP 分隔，未放宽 MAC 时序或物理检查门限。模型仍是数字线态／字节模型，不证明模拟信号完整性、电平兼容或 USB 电气合规。

## 已完成验证

USB 测试入口共 13 项，分组执行全部通过，包含实际运行的 Yosys 存储检查和 Gowin 组件综合，不将子场景重复计数：

| 场景 | 结果 |
|---|---|
| 原有 11 项 USB 回归 | 139.747 s，通过；包含锁定的 25K vendor 哈希核验 |
| 原生控制器 HS／FS，真实 25K | 295.570 s，通过；HS 1,143 检查，FS 263 检查 |
| 最终逻辑／物理 MAC、直接连接真实 25K、存储及 Gowin 综合五项复验 | 30.521 s，通过；MAC HS 1,841／FS 449，直接设备 HS 1,108／FS 224 检查 |

原生 HS／FS 均覆盖冷接入、根复位／recovery、实际 SOF、GET_DESCRIPTOR、SET_ADDRESS、SET_CONFIGURATION、512／64 字节二进制 bulk 回环、超过 3 ms 的 SOF 保活，以及保留未消费结果时的会话取消。HS 使用软件端口复位，FS 使用物理断开／重新接入，二次根复位后地址／配置归零且可重新读描述符，无旧结果泄漏。随后注入 NXT 停顿，确认故障在 PHY 复位 MAC 后仍保持、输出隔离，显式关闭／重启可再次完成 PHY 身份和 Scratch 自检；最后一步不等于第三次完整枚举。

Gowin 1.9.12.03 对上述八模块执行真实 `run syn`，器件为新板 `GW5AST-LV138PG484AC2/I1`，器件族 `GW5AST-138C`。组件 SDC 仅有 20.000 ns 参考时钟和 16.666667 ns ULPI 时钟，未加 false path。综合结果：2,105 Logic（1,950 LUT、155 ALU）、791 寄存器、无锁存器、两块 SDPB。BSRAM 数是组件综合分配，不是整机布局布线后的物理资源；不与历史候选资源简单相加。组件网表 SHA256 为 `d90e217bf203f3b93a21060f153722b5503d7ab9e0bd0a5fd829f38b7d713833`。生成文件只留在临时目录，不进入源码。

复现入口：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_ulpi_link.py
```

其中 Yosys／Gowin 检查在缺工具时会明确 skip；本次两者均实际执行通过。Gowin 测试在临时目录重建显式八模块输入和时钟约束，仅执行综合，不执行 P&R 或生成位流，不是新增生产构建器。

## 未完成与回退

还需要 CPU／MMIO／48↔60 MHz CDC、固件及端点策略、25K MIDI／PL 的新 Host 后端、整机显式新板配置、完整综合／P&R／时序／CDC／PLL 门禁，以及功放、HDMI、TF、BLE 等实际路径。功放芯片身份和 ULPI 电平转换问题仍以 [整板清单](CUSTOM_BOARD_BRINGUP_20261022.md)／[电气预检](CUSTOM_BOARD_PREFLIGHT_20261022.md) 为准，不能凭这些仿真进行下载。完整 suspend／resume、LPM、HS 实体拔插及 USB 合规未验收。

回退保持原显式构建 profile，不选择本开发组件即可；当前组件没有改动板上 SRAM 或 Flash，也不继承旧候选的验收和部署身份。后续整机候选必须重新登记全部输入、配置、位流哈希、验收范围与回退方案。
