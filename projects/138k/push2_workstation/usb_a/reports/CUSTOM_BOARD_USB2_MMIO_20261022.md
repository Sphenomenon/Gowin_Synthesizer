# 新板 USB2 CPU 寄存器边界与驱动

日期：2026-10-22。开发身份：`custom_138k_usb2_mmio_dev_20261022_v1`。基于已推送的 `e88fc9c5565b53e5556329fb954735b8fc26b95e`，承接 [原生控制器阶段](CUSTOM_BOARD_USB2_CONTROLLER_20261022.md)。本轮源码仍未提交／推送，没有新 UserCode、位流或板卡操作，不是“整机已可上板”。

## 来源与选择

新增 `workstation_usb2_cpu_bridge.sv` 和 `workstation_usb2_host_mmio.sv`，与已有八模块组成十模块显式组件；另加第一方 `drivers/usb2/workstation_usb2_host.c/.h`。旧 FS vendor、冻结基线、accepted full83／timing85／resource-timing 的输入及固件来源均未改。新板位置准备仍是 pinout-only，不会自动选中此组件。

以下路径相对 `projects/138k/push2_workstation/usb_a/`。完整输入哈希、配置、验证范围与未完成项见 [机器记录](custom_board_usb2_mmio_20261022/verification.json)。

| 本轮主要输入 | SHA256 |
|---|---|
| `rtl/usb2/workstation_usb2_cpu_bridge.sv` | `0bef0fa9c848ec606442b1b397a19eb7d822af0802cebdb2ed4e1acb6287fb26` |
| `rtl/usb2/workstation_usb2_host_mmio.sv` | `fdbd3e33be9232505df19daaa950a322601063f7dd8903c93873c867de37a033` |
| `drivers/usb2/workstation_usb2_host.c` | `afc2a876c6de37057ba02538f4d61cdead4e6e422a0ae01b55cb939fe30aa2d6` |
| `drivers/usb2/workstation_usb2_host.h` | `4d7ea3e7374f951d295dfa7acb160ddc1a73b0604394982927b9aa43eea32192` |

## 实现边界

- CPU 标称 48 MHz、独立参考域 50 MHz、ULPI 60 MHz。寄存器协议、位图、密封／提交／取消及驱动约束由 [CPU MMIO 文档](../rtl/usb2/CPU_MMIO.md) 定义，不另造 USB PL／BLE 线规。
- CPU 先预装整包再密封命令；两块 512×8 双时钟 RAM 承接 CPU→MAC 上传和 MAC→CPU 完整接收。未提交包不可读，CPU 不轮询也不会拖住 MAC 的结果／接收接口或 SOF，旧结果不允许被新命令覆盖。
- 会话无效或关闭 Host 对两侧事务状态异步取消、各域同步释放，不清 RAM 字节但清可见性与指针；CPU 锁存取消和代次，禁止拿 BUSY=0 当成功。ULPI 总预算默认 120,000 拍，坏 last／长度或超限请求端口复位，不发布半包。
- enable 直接交接到参考域，不依赖 ULPI 消费命令。参考域先将监护故障寄存为 one-hot，再单独同步给 CPU；缺钟时不依赖已经冻结的 ULPI 状态快照来报告缺钟。
- 第一方 C 驱动预检真实 HS 512／FS 64 上限及调用方 RX 容量；保留 MAC 的 NAK／NYET／重复包等结果，不自动重发。使用会话代次复验、完整接收后发布、计时器回绕处理及轮询次数上限；总线／协议失败或超时请求关闭 Host，不宣称关闭写本身失败时硬件已停。

## 验证及限制

新独立入口共 7 项，分组执行通过；工具依赖的 RAM／综合检查本次均实际执行，不是 skip：

| 项目 | 证据范围 |
|---|---|
| 双时钟邮箱 | CPU 半周期 10,417／7,353／25,000 ps，分别 7,828／8,170／7,342 检查；512 字节密封、背压、非法 MMIO、整包可见、各阶段短脉冲取消、反复复位、超时、错误 last 与停钟 |
| RAM 推断 | Yosys 验证两块 512×8 memory、各一个同步读／写端口，TX 写 CPU／读 ULPI，RX 写 ULPI／读 CPU，不以 generic 门级寄存器数代替目标 RAM |
| 寄存器主机→真实 25K | HS 2,683／FS 4,970 检查；同一十模块组件＋物理 ULPI 模型＋真实 CDC／SIE；冷接入、50 ms 根复位、10 ms recovery、枚举、SET_ADDRESS ACK 提交、配置、512／64 字节 bulk 回环、真实 SOF 保活、持有 CPU 结果时复位／重连、NXT 故障隔离与显式重启 |
| 真正停止仿真时钟 | 3,220 检查；全局复位后 PHY 从未起钟、正常初始化后实际停钟，CPU 仍能读独立缺钟／停钟原因并关闭 Host；时钟自行返回不清故障，显式重启重新执行实际 PHY ID／Scratch 自检 |
| C 驱动模型 | GCC 严格警告、ASan／UBSan；512／64 字节及调用方缓冲边界、SETUP、PING、NAK／NYET 不盲重试、部分接收取消、非法结果长度、毫秒回绕、计时器冻结、I/O 失败与 ABI 拒绝 |
| RV32 对象编译 | 使用仓库既有工具链解析入口，`rv32im/ilp32 -Os -ffreestanding -Wall -Wextra -Werror`；只证明对象可编译，不是整机固件链接或 ROM 已选择 |
| Gowin 组件综合 | 实际 `run syn`，十个明确 RTL 输入，`GW5AST-LV138PG484AC2/I1`；4 SDPB、1,073 寄存器，不生成 P&R／位流 |

标称 50／60 MHz 时钟不缩放；原生联调只将接入去抖缩为 100 µs，根复位、recovery、SOF 与包间隔保留原值。物理线态仍为数字模型，不是模拟电平／480 Mbps 眼图／USB 合规。测试只读取层次诊断，数据传输与控制使用 CPU MMIO，不强制 DUT 协议状态。

Verilator 对十模块顶层 `--lint-only -Wall` 零警告。组件综合临时 SDC 仅有 CPU 20.833333 ns、参考 20.000 ns、ULPI 16.666667 ns，无 false path。四块 SDPB 是组件综合分配，不是整机 P&R 后的物理 BSRAM 或完整 CDC／束数据最大延迟验收，不能直接加到历史候选资源表。

六项新测试与旧 USB 13 项的组合执行耗时 813.621 s，全部通过；最终六项针对性复验（含另加的停钟测试）耗时 15.082 s，通过。另有 pinout 25、current-sources 10、firmware 6、clean-prepare baseline 23 项通过；去重后共 84 个 Python 入口，不将重复执行或参数子场景再次计数。新入口曾因导入旧 TestCase 类额外发现旧回归，现改为模块导入，并确认独立入口只发现 7 项；额外执行的旧测试不是新的 MMIO 测试。

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_mmio.py
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_ulpi_link.py
```

## 下一步与回退

尚未将新 MMIO 接入 VexRiscv 实际总线仲裁，也未将第一方驱动接入整机固件编译／旧 `usbhw_*` 调用者。因此寄存器主机端到端、C 模型与 RV32 对象编译**不能合称真实 CPU 执行新固件已通过**。下一步须在显式新板配置中选择十模块，明确处理总线 ERROR，接入固件及 25K MIDI／PL HS backend，并运行真实 CPU／固件到设备的回归；不能静默替换已接受 profile 或只复制旧 FS 驱动。

新板原生组合根、完整综合／P&R／时序／CDC／PLL／IO 约束、实体排线及各外设仍按 [整板范围](CUSTOM_BOARD_BRINGUP_20261022.md) 逐项推进。功放 U1 型号、电平转换器实装／修正仍缺证据，HDMI、TF、BLE 和真实音频路径也不因本阶段通过而算完成。没有 SRAM／Flash 部署身份或硬件验收。

回退保持 `e88fc9c` 所在既有显式构建 profile，不选择新 MMIO／驱动即可；板上内容未改。临时综合工程只用于组件 RAM 回归，不是生产唯一输入；进入整机时必须由版本化配置提供相同明确来源，重新登记配置、全部输入、位流和验收。后续保留有价值的独立协议回归，不把临时目录当成必须长期存在的构建来源。
