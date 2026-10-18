# USB1 Full-Speed CDC 回环调试

本工程使用 60 MHz GPIO USB Full-Speed 核，实现单路 CDC 串口原样字节回环。它与 `../usb1_bringup/` 的被动观测工程独立。当前协议仿真通过；Gowin 构建、SRAM 下载、macOS 枚举和实板回环结果由主调试流程记录，不能由仿真代替。

## 2026-10-16 21:38 硬件更改后实板通过

**USB1 已在当前 Mac 完成 12 Mbps Full-Speed CDC 枚举及 1848 字节真实二进制回环。** 用户确认“补上上拉了”，未提供电阻阻值和具体接法，不将其记为已确认使用 1.5 kΩ。本轮复用已通过时序的 GAO 镜像，未修改 RTL、未写 Flash。

- 镜像仍为 `builds/20261016_011545_836351/impl/pnr/ao_0.fs`，SHA256 `bed38e61a1c0b21c738f5ad56d43ea2dc2abe0b1a53ac236fdde674ad4cdc253`，GAO=`AA53`；本轮[首次加载](reports/usb1_postchange_program_20261016_213448_176010.json)和[重新加载](reports/usb1_postchange_reload_20261016_213803_924838.json)均 SRAM Program+Verify 通过，UserCode=`4322`、Status=`70022020`。
- 先前拔插 USB1 曾使板子掉电重启：UserCode 变为 `944E`，主机重新看到 Flash 中的 `Primer 25K MIDI / 1209:0001`。该时点全零 GAO 来自不匹配的运行镜像，不能用作 USB1 诊断证据。重新加载目标 SRAM 镜像并等待启动后，对唯一位置 `0x01113200` 的旧 MIDI 设备调用 IOKit `USBDeviceReEnumerate(options=0)`，在保持供电的情况下触发重新枚举；[调用报告](reports/usb1_postchange_reload_20261016_213803_924838_host_reenumerate.json)记录成功。
- [主机枚举与回环报告](reports/usb1_postchange_hostreset_loopback_20261016_2138.json)确认唯一 `FB9A:FB9A / FPGA-USB-Serial`，registry ID=`4295069140`、location=`0x01113200`、configuration=1，CDC control/data 类分别为 2/10，唯一串口为 `/dev/cu.usbmodem1113201`。目标自身的 `UsbLinkSpeed=12000000` 和 `Device Speed=1` 均确认 12 Mbps，打开串口前复查仍为同一目标。
- 每轮按 1/7/31/32/33/63/64 字节分块写入并读取，共 8 轮、56 块、发送/收回各 1848 字节，全部逐字节一致，无额外字节。payload SHA256=`45366e8626cf4b69da2713d8647ba35567a42bebb583486a7cd7b17387ed033b`。12 Mbps 是链路速率，115200 是 CDC line coding 参数，本轮未测持续吞吐率或长期可靠性。
- [回环后 GAO](reports/usb1_postchange_pass_status_20261016_2138_decoded.json)采集 128 点，均为 FS_J；PLL 锁定、60 MHz 复位释放、USB 总线复位释放、attach intent 和 received sticky 均为 1，overflow 与 SE1 long sticky 均为 0。SE0 long sticky=1 记录本轮已发生的总线复位历史，不表示当前 SE0 故障；当前连续 SE0 计数为 0。该 50 MHz GAO 布局不包含字节计数，1848 字节结论来自主机逐字节回环报告。

截至本轮最后验证，板上为上述 USB1 GAO SRAM 镜像；断电后需重新加载。综合证据见 [硬件更改后报告](reports/usb1_postchange_20261016.json)。以下保留更改前的失败历史。

## 2026-10-16 01:15–01:17 硬件更改前实板历史

**该轮已实际下载普通 CDC 镜像和 GAO 诊断镜像，两次 SRAM Program+Verify 均通过；当时 USB1 尚未枚举，未执行真实串口回环。** 按用户要求直接进行固件和软件测试，该轮没有要求检查接线或测量电阻。

- 普通镜像 `builds/20261016_010036_373789/impl/pnr/usb1_cdc.fs`，SHA256 `364f8f48fa4b0bdfa6f5731816a45785ac1254b51883fb6924ece4893979e540`；UserCode=1630、Status=70022020。50/60 MHz setup/hold 违规均0，Fmax分别186.565/169.927 MHz。
- 该轮最后加载的 SRAM 诊断镜像为 `builds/20261016_011545_836351/impl/pnr/ao_0.fs`，SHA256 `bed38e61a1c0b21c738f5ad56d43ea2dc2abe0b1a53ac236fdde674ad4cdc253`；UserCode=4322、Status=70022020。50/60 MHz与工具自动20 MHz TCK均报告，setup/hold违规均0；采用已记录的复位同步器入口和观察器首级同步豁免，未添加整组时钟豁免。
- macOS I/O Registry 查询成功，严格目标 `FB9A:FB9A / FPGA-USB-Serial` 数量0；完整13设备列表与下载前无增减，未打开其他串口。系统日志中的 FTDI 请求中断属于JTAG下载器，不作为USB1枚举证据。
- 两次独立GAO各128点：`0001FFFF0000D0B4/D0B5`。PLL锁定、60 MHz复位释放、2秒启动等待已结束（attach intent=1）；USB协议核复位未释放，D+/D−均为0（SE0），连续SE0计数65535饱和，没有FS-J长驻记录或收到字节。50 MHz观察快心跳逐点交替。

该轮定位到 **USB核持续看到SE0并保持总线复位，尚未进入枚举事务**。历史线态变化计数为1，不把它视作有效USB包；短数字快照不能确认电气/接线根因。该轮暂不展开硬件判断，也不把仿真256字节回环说成实板回环成功。LCD与BLE成功源文件、镜像和记录均保留，当时板上运行USB诊断逻辑。

统一结果在 `reports/usb_hardware_summary_20261016.json`；下载、主机检查、CSV和解码报告均位于 `reports/`。[GAO说明](debug/GAO.md)记录了保留分进程构建、单SDC、综合后插入调试核的兼容处理。

## 固定上游与本地适配

上游为 [WangXuan95/FPGA-USB-Device](https://github.com/WangXuan95/FPGA-USB-Device/tree/ebf0696f0b1dc604a4ed8eedee4c3eae1643e66f)，固定提交 `ebf0696f0b1dc604a4ed8eedee4c3eae1643e66f`。`../vendor/fpga_usb_device/` 保存未经修改的 `usb_serial_top.v`、完整 `usbfs_core/` 依赖、上游 README、LGPL-2.1 全文和逐文件 SHA256 清单。上游没有提供 testbench，本工程增加了独立物理总线 BFM。

原上游只把 token 的 endpoint 传入 transaction，未核对低 7 位设备地址。本工程使用 `generate_core.py` 在固定 SHA256 的 `usbfs_core_top.v` 中插入 `usb1_address_filter`，生成 `generated/usbfs_core_top.v`；vendor 文件保持原样。适配仅改变 RX packet 到 transaction 的桥接：

- SETUP / OUT / IN token 必须匹配当前设备地址；对应 DATA / host ACK 仅归属一个已选 token，完成后消费归属，外地址数据不会进入回环。SOF 仍全局转发。
- USB 总线复位恢复地址 0。标准 SET_ADDRESS 必须为 EP0、DATA0、恰好 8 字节，且 `bmRequestType=00`、`bRequest=05`、`wIndex=wLength=0`、地址不超过 127。
- 新地址在 EP0 状态 IN 的零长度 DATA1 包被 host ACK 后生效；新有效 SETUP 取消未完成的地址变更。

`prepare_sources.tcl` 可由普通和 GAO 构建入口 source，支持防崩构建器在全新目录重新生成适配。工程应添加生成版 core，排除 vendor 同名 `usbfs_core_top.v`，其余 vendor RTL 原样添加。派生 core 与相关源代码保留上游 LGPL-2.1 许可及来源。

这是一份首轮枚举/回环实现。原描述符和其余 transaction 行为保留，包括 CDC 配置中缺少 Header / Call Management functional descriptor、类 IN 请求默认返回零，以及没有显式 SET_CONFIGURATION 状态。本次仅验证列出的合法控制交换与地址安全边界，不表示完整 USB 规范认证或所有错误/重传处理都已验证。若 macOS 看到了 USB 设备但未产生 CDC 端口，应记录真实描述符/主机结果，再独立适配描述符。

## 接口与标识

顶层为 `usb1_device_top`，板级引脚为：

| 信号 | FPGA 球号 | 行为 |
|---|---|---|
| `clk_50mhz` | E2 | 50 MHz 输入，`u_clock` 生成 60 MHz |
| `usb1_dp` | L6 | USB1 D+，三态收发 |
| `usb1_dm` | K6 | USB1 D−，三态收发 |
| `led_ready` | E8 | 本板 active-high；LOCK 且复位释放后约 0.894 Hz 心跳 |
| `led_done` | D7 | 本板 active-high；真实 CDC OUT 字节到达后点亮，总线复位清除 |

所有上述 IO 的 BANK 按本板已确认的 3.3 V 约束；USB 线禁用 FPGA 内部弱上拉。时钟模块 `usb1_clock_60m` 和其 PLL/LOCK 复位、CST、SDC、构建文件由主流程及独立时钟子任务负责。

沿用上游实验标识：VID `0xFB9A`、PID `0xFB9A`、制造商 `github.com/WangXuan95`、产品 `FPGA-USB-Serial`，无序列号。1 配置、2 接口（CDC control 0 / data 1）、1 个串口；数据 OUT 为 `0x01`，最大包 32 字节；IN 为 `0x81`，描述符最大包 64 字节而实际每包最多 32 字节。数据不作大小写转换，也不由 DTR 门控；本工程没有分配生产用 VID/PID。

上游 `usb_dp_pull` 要求通过 **1.5 kΩ 电阻**接到 D+。本工程顶层只保留内部 `usb_attach_request`，没有将其接到 FPGA 的电阻控制 IO，也不将强输出或 FPGA 弱上拉用作电阻替代。D+/D− 仅在发送 USB 包时由核驱动，其余时刻高阻。硬件更改前外部上拉情况未确认；用户现已确认补上上拉，实际阻值与接法仍未提供。本轮实际枚举与回环结果记录在上方，不能据此补造电阻测量结果。

上游在时钟/复位释放后还有 120,000,000 周期（2 秒）等待。由于外部电阻未受 `usb_attach_request` 控制，这个信号不能证明主机已经检测到插入。`usb_reset_released` 表示核的总线复位释放，不表示已配置或已枚举。观察主机时至少留出启动等待时间。

## 回环与状态

`usb1_cdc_loopback` 把 `recv_data/recv_valid` 原样送入上游 1024 字节发送 FIFO。上游 OUT 没有应用层 ready 背压，因此连续写入且不读取可以溢出。首轮主机验证按不超过 64 字节的批次写入并读完整批次，再发下一批。计数器均为 16 位饱和计数；`echo_queued_count` 只计入 FIFO 成功，不代表 host 已 ACK。

顶层保留 `(* syn_keep = 1 *) wire [63:0] status`，供需要时 GAO 观测：

| 位 | 含义 |
|---|---|
| 63:48 | 收到的 CDC OUT 字节数 |
| 47:32 | 成功进入回环发送 FIFO 的字节数 |
| 31:16 | FIFO 满导致丢弃的字节数 |
| 15 / 14 | PLL LOCK / 60 MHz 复位释放 |
| 13 / 12 | USB 总线复位释放 / 内部 attach 请求 |
| 11:10 | 两级同步后的 `{D+,D−}` |
| 9 | overflow sticky |
| 8 / 7 | `recv_valid` / FIFO `send_ready` |
| 6 / 5 | 收到字节 sticky / 心跳 |
| 4:0 | 0 |

## 可复现仿真

运行 `sh prj/usb1_device/run_sim.sh`，需要 `python3`、Icarus Verilog 和 `vvp`。脚本先验证固定上游 SHA256 并重建桥接，再在临时目录编译/运行测试，退出时移除仿真二进制。使用真实核心及真实物理 D+/D− 三态端口，host BFM 独立实现 NRZI、位填充、CRC5 和 CRC16，并从引脚解码设备响应。仿真建模所需外部 D+ 上拉，只跳过内部 2 秒启动计数；不替代 PLL 或模拟电气验证。

2026-10-16 强化测试通过：

- 物理 SE0 总线复位，EP0 device/config/product 描述符（包括跨 32 字节包的 57 字节配置）、SET_ADDRESS/SET_CONFIGURATION/GET_CONFIGURATION、SET_LINE_CODING 与 DTR/RTS 控制交换。
- 外地址 SETUP/OUT/IN 及其 DATA 静默，状态 ACK 前新地址无效、ACK 后旧地址无效/新地址成功；新 SETUP 取消待提交地址，总线复位恢复地址 0。
- 0/7/9 字节 SETUP、DATA1 SETUP、地址 128、单个 SETUP 后分开的 7+1 DATA 不得提交地址；重复 ACK 无归属。此项硬化地址提交，异常请求的回复内容仍沿用上游。
- 0…255 全部二进制字节逐字节回环一致，所有响应 PID / CRC16 / NRZI / 位填充检查通过；空 IN 返回 NAK。
- FIFO 未溢出时 RX/入队均为 256、drop 为 0；之后不读取而写 1025 字节，准确报告 1 个丢字节和 overflow sticky；总线复位清除会话计数与 sticky。

上游文档报告过 macOS 10.15 的 CDC 实测；本板与当前 macOS 的有限实测结果见上方主机枚举和真实回环报告，仿真结果不替代实板证据。
