# USB2 CPU 寄存器与跨时钟边界

这是 `workstation_usb2_host_mmio` 的内部硬件／驱动接口，不改变 USB PL、MIDI、BLE 或 18-bit 事件契约。仅供显式新板配置选择，旧 `usbh_core` 寄存器与 `usb_hw.c` 不兼容，不能替换源码后沿用旧固件 ROM。

## 时钟与所有权

- `clk_cpu` 面向标称 48 MHz CPU 总线，`clk_ref` 为独立 50 MHz，`clk_ulpi` 为 PHY 60 MHz。输入全局复位异步置位；桥内部各域分别同步释放。
- `host_mmio` 只做原生组合，`cpu_bridge` 拥有寄存器、整包存储、握手与 CPU 可见状态；PHY 配置仍只归 Host 端口状态机。
- 默认关闭 Host。CPU 的 enable 经过参考域两级同步；即使 ULPI 无时钟，也能从 CPU 关闭 Host。HS 许可经 ULPI 域两级同步，只能在 CPU enable 已关闭时改动。
- 端口软件复位使用独立 toggle／ack；只允许一个未确认请求，不因 ULPI 事务复位丢失请求。请求确认只表示脉冲送达端口输入，不是根复位完成，固件必须等待会话代次变化及 traffic 恢复。
- `session_reset_n_i` 是控制器事务有效边界，不是 PHY ready。它或 enable 撤销时，对两侧事务状态异步取消、各域同步释放，清除请求／结果可见性和指针，不清 RAM 内容。短于 CPU 周期的取消也会保持到 CPU 看见；CPU 代次加一并锁存 CANCELLED。

## 总线协议

32-bit 数据、8-bit 字节偏移，地址必须四字节对齐。主机保持 CS、读写方向、地址、数据及 byte-enable，等待一次寄存的 ACK；同次 CS 持续期间不再次产生 ACK 或副作用。主机须撤销 CS 至少一个 CPU 上升沿后才能发下次请求。不是 AXI／Wishbone，无隐式连续 CS burst。

非法地址、非法方向、不允许的 byte-enable、忙时改包、容量超限及空 RX 读取均 ACK＋ERROR，读值为零且不产生相应副作用。SoC 必须明确处理 ERROR，不能将空 RX 的零值当成真实 USB 数据。CONTROL、COMMAND、ACTION 写要求 byte-enable=`1111`；TX_DATA 接受 `0001` 或 `1111`，每次只写低八位。

| 偏移 | 名称／方向 | 定义 |
|---|---|---|
| `00h` | ID，R | `55324801h`；ABI v1，不冒充旧 FS 寄存器 |
| `04h` | CONTROL，R/W | bit0 enable、bit1 HS allow、bit2 W1P port reset；读 bit16 为复位请求未确认。其余写位必须零 |
| `08h` | STATUS，R | 低 16 位为最近 ULPI 状态；bit16 会话可用、17 BUSY、18 DONE、19 CANCELLED、20 复位请求未确认、21 状态快照已收到 |
| `0Ch` | COMMAND，W | PID `[7:0]`、地址 `[14:8]`、端点 `[18:15]`、toggle `[19]`、长度 `[29:20]`；高两位必须零。写入即密封并提交 |
| `10h` | TX_DATA，W | 逐字节预装 OUT／SETUP，最多 512 字节；忙／结果未释放时禁止写 |
| `14h` | RX_DATA，R | 读取一个已提交 RX 字节；未 DONE／无剩余字节／会话无效时 ERROR |
| `18h` | RESULT，R | bit31 DONE、长度 `[25:16]`、响应 PID `[15:8]`、MAC 状态码 `[3:0]`；状态码沿用 MAC 的 0–9 |
| `1Ch` | ACTION，W | bit0 释放结果并清 TX/RX 指针，bit1 只清 TX staging，bit2 清 CANCELLED；忙时拒绝，其余位必须零 |
| `20h` | TX_COUNT，R | 已上传字节数 |
| `24h` | RX_REMAINING，R | 尚未读取的提交字节数 |
| `28h` | GENERATION，R | CPU 所见会话取消代次，32-bit 回绕；全局复位归零 |
| `2Ch` | PORT_DIAGNOSTIC，R | MAC failed `[0]`、port state `[5:1]`、port failure `[9:6]`、MAC state `[13:10]`、init failure `[17:14]`、init stage `[22:18]`、clock failure `[24:23]` |
| `30h` | SOF_COUNT，R | 最近快照中的 MAC SOF 计数 |
| `34h` | CAPABILITIES，R | HS 最大长度 `[9:0]=512`、FS `[19:10]=64`；bit20–23 表示 HS、PING、同步包存储和会话取消代次能力 |
| `38h` | REFERENCE_FAULT，R | 独立参考域故障 one-hot：bit0 启动缺钟、bit1 运行停钟、bit2 监护状态非法；不依赖 ULPI 快照 |

STATUS 的低位：bit0 PHY ready、1 connected、2 high speed、3 traffic enable、4 failed、5 PHY failed、6 SOF enable、7 reset active、8 unsupported low speed，其余零。正常 HS 的空闲 LineState 不作为“断开”的 CPU 判据。

`irq_o` 在 CPU 域为 DONE 或 CANCELLED 的电平或，分别由释放结果／清取消解除。

ULPI 状态、诊断和 SOF 一起密封为 80-bit mailbox，源端保持到 CPU ack，不将自由运行计数器逐位采样。单次寄存器读对应一个已捕获值；不同寄存器读之间仍可能更新，不能把多次读取称为原子整机快照。ULPI 停钟时这些值可能停留在旧快照，须结合本地会话标志、GENERATION 与独立 REFERENCE_FAULT。后者由参考域先寄存为 one-hot，再逐位两级同步，不当作一条实时多位计数总线。

## 包提交与取消

CPU 必须先等 STATUS 的会话可用与 traffic enable，再在提交前装全 OUT／SETUP；上传数必须等于命令长度，IN／PING staging 必须为空。会话可用本身包含仍在发 SOF 的 recovery 阶段，不表示可立即发普通事务。HS 上限 512，FS 上限 64，端点自己的 MPS 仍由固件负责。SETUP 必须长度 8、toggle 0；PING 仅 HS 且长度 0。命令、TX staging 在 BUSY 期间保持不变。

每侧各一块 512×8 同步双时钟 RAM。CPU 密封 TX 后，ULPI 在不等待 CPU 的情况下向 MAC 连续供包；MAC 返回成功包后，桥独立将整个 RX 排入 RAM，检查 last／长度，再跨域发布 DONE。CPU 长时间不读结果不会占住 MAC 结果或 RX 接口，也不停止 SOF；但单个 CPU 邮箱不接受第二个请求。

结果发布前，RX 不能从 CPU 读取。结果发布后直到 ACTION bit0，不能发新命令；读完 RX 不自动释放结果。NAK、STALL、坏包、重复包、NYET 沿用 MAC 结果，不自动改 toggle、不盲重发 NYET OUT。

会话取消优先于未完成事务、旧结果、未读 RX 和上传内容。GENERATION 在 CPU 看见会话失效时递增；CANCELLED 只显式清除或全局复位。软件必须按成功结果与代次使用数据，不能从 BUSY=0 推断成功。取消前已读入调用方内存的部分数据在错误返回后无效，不向业务层发布该部分包。

默认 ULPI 事务总预算为 120,000 拍，覆盖命令等待、上传、等待结果与 RX 排入；超限、非法长度或错误 last 请求端口复位并等待会话取消，不发布半包。CPU 读结果不受此预算限制。ULPI 停钟时该计数器不能自行前进，安全取消依赖独立参考域监护；CPU 还可显式关闭 enable。完整 CDC／束数据最大延迟／复位时序及布线门禁仍须在整机新板配置中执行，仿真和 RAM 推断不能替代它们。

## 第一方驱动

`drivers/usb2/workstation_usb2_host.c` 是此 ABI 的独立驱动，不修改 vendor。调用方提供有界 32-bit MMIO read／write（成功返回 0）和连续运行、可回绕的毫秒计时器；每个 Host 只有一个串行调用者。`open` 校验 ABI，`enable` 先显式关闭并保留至少 1 ms 参考域交接窗口，再等待 traffic；`reset_port` 等代次变化和新 recovery 完成。

`transfer` 预检 HS／FS 长度、指针及 RX 容量，512 字节仍是完整上限，不缩为 64 以绕开 HS。只有完整收包、会话复验及结果释放后才发布 result；MAC 非零状态仍由 result.status 返回，上层处理 NAK／NYET／toggle，不隐式重试。返回错误时 result.length 为零，调用方 RX 内存内容无效。

所有等待同时受可回绕毫秒期限及可配置轮询次数上限限制；计时器不走也不会无限等待。总线错误、协议自相矛盾或超时请求关闭 Host；若关闭写本身也失败，则只能报告 I/O 故障，不能宣称已关闭硬件。软件取消返回须重新枚举／恢复会话，而不是沿用旧地址继续传输。

MMIO 阶段证据见 [原始记录](../../reports/CUSTOM_BOARD_USB2_MMIO_20261022.md)。后续 [原生 CPU 组件](CPU_SOC.md) 已接 VexRiscv 总线并实际执行第一方 RV32I 驱动，通过 HS／FS 枚举和回环；这仍不是整机业务固件、MIDI／PL backend 或上板验收。复现入口分别为 `sim/test_workstation_usb2_mmio.py`、`sim/test_workstation_usb2_soc.py` 与 `sim/test_workstation_usb2_preparation.py`。
