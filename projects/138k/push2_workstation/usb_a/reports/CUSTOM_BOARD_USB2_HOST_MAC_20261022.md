# 新板 USB2 Host MAC 与真实 25K 包级回归

日期：2026-10-22。承接 [端口协商快照](CUSTOM_BOARD_USB2_HOST_PORT_20261022.md)，仍以 [整板交付范围](CUSTOM_BOARD_BRINGUP_20261022.md) 为目标。本轮把 Host 侧从端口协商推进到真实包事务，但没有将分层测试当作完整新板工程或硬件验收。

这是 MAC 阶段的历史快照，以下哈希与测试计数不代表后续组合版本。提交前的原生控制器、独立故障复位及当前验证身份见 [控制器阶段记录](CUSTOM_BOARD_USB2_CONTROLLER_20261022.md)。

## 1. 开发身份与来源

源码快照：`custom_138k_usb2_mac_dev_20261022_v1`。起点为已推送的 `b593a390fd495a782f7bf3c6756ea5af40399ae8`。本轮新增 MAC、同步存储与回归，并为现有 PHY 导出正常包 STP／RXCMD；尚未提交，也未选入 accepted full83、timing85 或资源候选。没有新 UserCode、位流或 SRAM／Flash 部署。

下列路径相对 `projects/138k/push2_workstation/usb_a/`：

| 输入 | SHA256 |
|---|---|
| `rtl/usb2/workstation_usb2_host_mac.sv` | `297e537c8e50cf629e4b35f5395911b7110766a8ad1f2a7f99ee36144d97f916` |
| `rtl/usb2/workstation_usb2_host_phy.sv` | `d88814938e3d0bb181a2397585ad480255b5b3ebaa670d5925f91ded6c893688` |
| `sim/test_workstation_ulpi_link.py` | `bfe302daaa79e433d25d72dc8278b874036baf3b4fa1f09246b7f61cc4a83e6d` |
| `sim/usb2/tb_workstation_usb2_host_mac.sv` | `077597d93f0756d2529d028b5cd56799037b9f46501f3e14cb26fe4a34ebf122` |
| `sim/usb2/tb_workstation_usb2_mac_25k.sv` | `c352cb2f965522ac97efd755d012082f6f7e5d82642c2c0bf682736b946c3a34` |
| `sim/usb2/usb3300_packet_model.sv` | `5549104974a5e7418e144fc8625ad3b1b4f33fb7571c85af2b99e98064937c62` |
| `sim/usb2/tb_workstation_usb2_25k_negotiation.sv` | `aa3e872fc3c1cfa360fcf3568b2491b5c6a7dc9cb72d6f7de13e954275c2518e` |

其余五个 PHY 支持模块、25K 第一方 CDC／描述符、锁定 vendor 与原始清单均承接起点提交；本轮未修改它们。回归仍检查全部上游 SHA256，不从历史私有 staging 获取输入。前一报告的哈希是其历史快照，未覆盖为本轮值。

## 2. 实现与边界

`workstation_usb2_host_mac.sv` 是原生第一方 60 MHz 模块，不是改旧 FS Host 的频率常数或改 vendor SIE。完整接口／结果码见 [USB2 模块说明](../rtl/usb2/README.md#host-mac-事务边界)。

- 支持单次 OUT／IN／SETUP 与 HS PING。命令带地址、端点、DATA toggle 和上限，HS 512／FS 64 字节；SETUP 使用 8 字节 DATA0。端点自身的 max-packet 与重试策略仍归固件。
- 上传先完整接收再发 token，避免 CPU 背压造成 USB 包中途无数据；默认总上传预算 1 ms。IN 私有接收后核验 PID、CRC16、RxError 和长度，合格才 ACK，ACK 后才发布结果。重复 toggle ACK 但不重复发布；超限或坏包不 ACK、不泄漏部分数据。
- 成功结果与提交后的 RX 流是两个背压边界，不阻止 SOF。MAC 发出真正的 3 字节 SOF token／CRC5，HS 每 125 µs、FS 每 1 ms；HS frame 每 8 个 microframe 增加一次。事务按最大包预算在帧尾暂停调度，不挤掉下一次 SOF。
- 结果区分成功／NAK／STALL／无响应／协议错误／重复包／超限／上传超时／非法命令／NYET。NYET 不是未接收，后续需 PING，不能盲目重发。这里没有自动端点 toggle 或静默自动重试。
- 以 ULPI 1.1 §3.8.2.6 Table 9／10 以及 USB 2.0 §7.1.18／§7.1.19／第 8 章为依据；已重新渲染核对 Table 10。HS TX→TX、RX→TX 与 FS SE0→J 分别用正确时基，不套用旧 FS 位宽计时。
- 两块 512×8 存储采用同步读写和下一拍预取。存储本身无异步复位，状态／提交可见性复位；回归检查结果稳定、背压、首次／末尾字节及会话重启，不依赖清零 RAM。新增 Yosys 检查直接要求两块单读单写、同一时钟的 `$mem_v2`，避免写法变化静默变成 8,192 个数据触发器。
- PHY 新增 `mac_txend_o`／`mac_line_valid_o`，在 MAC 所有权内提供真实正常包 STP／新鲜 RXCMD。根复位／chirp／CSR 不可泄漏为 MAC 完成。`idle_o` 等总线排空与间隔，供后续端口静止握手使用。

`fatal_o` 不是可以消费为普通超时的结果：它意味着无法保证 PHY 包已完成。完整组合必须锁存故障、隔离 DATA 并拉高 STP，再显式重启；不能把 fatal 取反直接当 enable 造成循环自动重试。目前这层与 CPU／MMIO／CDC 的原生组合仍是后续工作，独立 MAC 不是可直接上板的顶层。

## 3. 分层证据，不拼接成整机验收

| 路径 | 实际覆盖 | 尚不覆盖 |
|---|---|---|
| 原六模块 PHY＋真实 25K 核 | 默认 60 MHz、50 ms 根复位、10 ms recovery，双方 HS／FS 协商及取消／故障 | 此场景的保活活动仍由原模型抽象，没有新 MAC 或 CPU |
| MAC＋独立字节故障模型 | HS 1,839／FS 447 次检查；CRC5、OUT CRC16、完整接收、重复包、CRC／PID／RxError／溢出、不 ACK 坏包、NAK／STALL／timeout、NYET／PING、部分上传超时、ZLP、SOF、结果／RX 背压、帧尾延后及 reset | 没有 USB3300 电气、PHY 初始化或设备核 |
| MAC＋真实 ULPI Link＋独立物理管脚模型 | 同样 HS 1,839／FS 447 次检查；DIR／OE 无争用、NXT 背压、STP／00、token→DATA TX CMD 间隔、RX→ACK TX CMD 间隔，按规范 Table 10 的时基检查 | 模型不做模拟电平、bit stuffing／差分波形或 PHY 延时 PVT；未组合根端口初始化 |
| MAC＋真实 25K CDC／SIE | HS 1,108／FS 224 次检查；实际 SETUP、描述符、地址状态 ACK 后提交、配置、HS 512／FS 64 字节二进制回环，空闲超过 3 ms 仍由真实 Host SOF 保持，之后再次读取描述符 | 通道为字节级 PHY 抽象；device chirp 由测试侧合法线态驱动，非前一行六模块复位路径；不是 MIDI／PL |
| RAM 推断 | 两个 512×8、各单读／单写、读写时钟均为 `clk_ulpi` 的同步 memory，`check -assert` 通过 | 未证明 Gowin 138K 实际 BSRAM、布局布线或 60 MHz 时序 |

FS 描述符使用设备实际声明的 EP0 8 字节上限，读取 8＋8＋2 三包并正确切换 DATA1／DATA0；没有为测试把设备改成 HS 的 64 字节 EP0。两端实际发出的 PID／CRC／ACK／数据被对方真实 SIE 消费，没有强制内部协议状态。

逻辑／物理故障矩阵将上传／包阶段看门狗分别设为 1,024／4,096 拍以加快故障等待，不缩放 SOF、HS／FS 包间隔或响应窗口。真实设备包级回归使用 MAC 默认的 60,000 拍看门狗；原六模块双端协商继续保持前一报告的 50 ms／10 ms 实际计时。所有 HS／FS 选择都由测试参数显式给定，不在被测 RTL 内替换常量。

Verilator 对 MAC 及 `host_phy` 分别 `--lint-only -Wall` 零警告。Yosys 层次、存储推断、通用综合及 `check -assert` 通过。最终通用 `synth` 为 30,418 cells，包含将存储按 generic 工艺展开的 8,192 个数据 DFFE；推断回归检查的是映射前的两块同步 memory，不能拿 generic 数字宣称已经使用两块 Gowin BSRAM。目标器件的物理 RAM／LUT／时序仍须由实际 Gowin 整机候选独立核对。

USB 入口由原 7 项增加为 11 项（新增逻辑 MAC、物理 ULPI、真实 25K 包事务和存储推断，前三项各含 HS／FS 子场景）。旧 pinout 25、current-sources 10、firmware 6、clean-prepare baseline 23 项继续通过，共 75 个 Python 测试入口，分组复验；不将该数字当作整机或硬件验收。

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_ulpi_link.py
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_ulpi_link.py PhysicalLink.test_host_mac_transactions_and_failures PhysicalLink.test_host_mac_on_physical_ulpi PhysicalLink.test_host_mac_with_actual_25k_packets PhysicalLink.test_host_mac_buffers_keep_synchronous_memory_ports
```

存储检查在没有 Yosys 的环境明确 skip，不伪报已证明 RAM 推断；本轮安装环境实际执行通过。所有仿真、JSON 和综合中间结果均在临时目录，不进入源码提交。

## 4. 距离原目标的剩余工作

1. 将六模块 PHY 与 MAC、持久 fatal／安全隔离组成一个实际原生边界，验证根复位至真实 SOF、枚举、拔插和软件 reset 的完整路径，而不是拼接本报告的三种独立模型。
2. 接现有 CPU／MMIO 与固件，显式处理 48／60 MHz、取消／会话、结果提交、端点 max-packet、toggle、NYET/PING 与重试策略，保持现有 18-bit 事件与 PANIC 契约。
3. 将 25K MIDI_KEYBOARD 的 MIDI／PL 描述符与端点接上实际 HS 后端，并验证 FS Push 回退及业务层；现有 CDC 是包层伙伴，不替代业务交付。
4. 原生新板整机配置、引脚／电气约束、DDR、功放型号与格式／安全驱动、HDMI 极性／CEC、TF 真卡、蓝牙新板连线和实际业务服务仍须按完整清单完成。音频采样节拍不能被传输或显示阻塞。
5. [USB3300／电平转换器电气阻断](CUSTOM_BOARD_PREFLIGHT_20261022.md) 尚未解除。没有 Gowin 整机综合／P&R／CDC／PLL／物理资源验收，没有上板、SRAM、Flash 或冷启动证据。

回退：继续使用起点提交及原显式构建，不选新 MAC；PHY 两个新增输出不改变旧输入来源。下一完整候选必须重新记录源码、配置、输入及位流身份，不继承旧 UserCode 或部署验收。
