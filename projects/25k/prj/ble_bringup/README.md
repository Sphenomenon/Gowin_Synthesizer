# GW25K BLE 首轮调试

目标器件为 GW5A-LV25MG121NC1/I0（Gowin 型号名 GW5A-25A）。本工程适配已有 RTL8723DS ROM-v2 BLE 包，主动输出仅为 BLE UART/复位和两个状态灯；另接系统时钟、SW1 按键与 USB1 两个纯输入监测脚。USB1、USB3300、LCD 和其它外围没有顶层输出。

**2026-10-16 本板 BLE 功能实测通过。** macOS 已扫描并连接 `RTL8723-BLE`，读取 FFF1 得到有效 20 字节数据，并收到序号 0、1、2 的三个通知，全部通过 `BTST` 内容与 CRC 校验；包内毫秒计数为 18522、19022、19522，间隔均为 500 ms。结果保存在 `reports/ble_hardware_20261016.json`。对应 GAO 镜像的临时 SRAM Program+Verify 通过，UserCode=`0xEEDB`、状态=`0x70022020`。本次通过范围为 BLE 广播、连接、读取及通知；Wi-Fi 和主动 USB1 测试仍待后续硬件条件与实现。

## 引脚和硬件边界

| 顶层信号 | 球号 | 板上网络与方向 |
| --- | --- | --- |
| clk_50mhz | E2 | 52300 核心板 Y1100 的 50 MHz 系统时钟 |
| restart_n | L10 | SW1_KEY，低有效，板上已有上拉；按住约 20 ms 停止，释放约 20 ms 重开会话 |
| module_uart_tx | J8 | U3.42 UART_OUT / BT_TX，模组 TX → FPGA RX |
| usb1_dp / usb1_dm | L6 / K6 | USB1 D+ / D-，只作输入监测，显式关闭内部上下拉 |
| module_uart_rx | K9 | U3.43 UART_IN / BT_RX，FPGA TX → 模组 RX |
| module_bt_dis_n | K8 | U3.34 BT_DIS#，低复位、高运行，板上 R20=10K 上拉 |
| led_ready | E8 | READY，输出高亮；专用配置脚在 bitstream 中复用为 GPIO |
| led_done | D7 | DONE，输出高亮；专用配置脚在 bitstream 中复用为 GPIO |

I/O 约束全部采用当前实板已确认的 LVCMOS33。没有连接 L9 / BT_HOST_WAKE_DEV；它的模组极性和必需时序没有资料确认，因此本工程不主动驱动它。RTL8723DS 需要实际装有天线、供电和内部时钟，ROM version 必须为 2。初始化失败不能仅凭 UART 超时判定芯片损坏。

**Wi-Fi 当前没有可用的 FPGA 数据通路。** 原理图明确把 U3.12 WL_DIS#、U3.14～19 的 SDIO 引脚标为 NC；BLE UART 不提供本包可用的 Wi-Fi 数据业务。若实板没有额外飞线，Wi-Fi 需要补 SDIO/使能的硬件连线及独立驱动后再调试。

## 行为与 LED

配置后约 1024 个系统时钟保持 POR；随后自动开始一次 180 秒会话。先把 BT_DIS# 拉低 200 ms，再拉高等待 2000 ms，然后执行 H5、HCI 型号/ROM 检查、30147 字节补丁下载和广播配置。UART 固定为 **115200 / 8E1**，不能当作普通 8N1 AT 串口使用。

| 状态 | READY | DONE |
| --- | --- | --- |
| 正在初始化 | 约 1 Hz 心跳 | 灭 |
| 初始化完成、可扫描 | 约 1 Hz 心跳 | 常亮 |
| 已连接、未订阅 | 约 1 Hz 心跳 | 约 1 Hz 闪烁 |
| 已订阅 | 约 1 Hz 心跳 | 约 3.9 Hz 快闪 |
| 初始化或传输失败 | 约 3.9 Hz 快闪 | 灭 |
| 180 秒会话到期 | 常亮 | 灭 |
| SW1 按住并去抖后 | 灭 | 灭 |

READY/DONE 原图串联电阻为 10K，亮度可能很低。会话从 enable 开始计时，包含启动和补丁下载时间；不会在失败后自动反复复位模组。故障闪灯沿用核心的 uptime_ms，在 180 秒到期后也会冻结。失败或到期后，按住 SW1 至少约 20 ms，再释放至少约 20 ms，即可重开会话。

原包的已知限制：若模组在初始化完成后自行重启或 H5 链路重新握手，驱动不会自动清除 initialized 并重新执行固件/HCI 初始化。此轮保留 vendor 源码，遇到这种情况应按 SW1 重开完整会话；不能把 H5 再次 link_up 单独作为完整初始化成功的证据。

复位、失败和到期时，UART_TX 与 BT_DIS# 的 FPGA 输出均置为高阻。R20 仍把 BT_DIS# 上拉，高阻并不等价于关闭射频；停止时没有发送关闭广播或断连指令。USB1 D+/D- 是单独声明的纯输入，CST 为 PULL_MODE=NONE；其它未使用 GPIO 按 Gowin `unused_pin default` 配置为三态输入加弱上拉，而非主动逻辑输出。

USB1 监测实例来自 `../usb1_bringup/rtl/usb1_passive_monitor.v`，记录同步后的线态、跳变数、活动与持续 SE0/SE1 sticky 标志。它没有发送、D+ 枚举上拉或 USB 协议解码；仅凭线态无法认定枚举成功。

## 构建和当前验证

Gowin 构建入口为 `build.tcl`，它自动切换到本工程目录。源码来自 `../vendor/rtl8723ds_ble/rtl/`，其中 H5/GATT 使用下述自动生成的适配副本。实际 GowinSynthesis 会以 `impl/gwsynthesis` 解析 `$readmemh` 相对路径，且当前 macOS 版本不能正确解析非 ASCII 的 ROM 字符串路径；因此 `prepare_sources.tcl` 把原样 ROM 暂存至 `/private/tmp/gw25k-ble-rom-[pid]/rtl8723ds_patch.mem`，并生成 `generated/ble_bringup_top.v`，只替换其 PATCH_FILE 默认值为该 ASCII 绝对路径。原 RTL 模板及 vendor 均保持不变，每次构建重新生成。暂存 ROM 与 vendor 已逐字节比对相同。

为处理 GW5A-25A 上的寄存器布局不足，预处理还会运行 `prepare_adapted.py`。脚本先按 vendor MANIFEST 核验 H5/GATT 原文件，再生成 `generated/rtl/` 中的两个副本：H5 的 280 字节 `pending_ram` 改用无异步复位的同步读写并请求 block RAM，数据保持原容量，UART 忙周期提供预取时间；固定 MTU=23 的 GATT 将两个回复槽及活动槽各收紧到 32 字节，最大实际出包为 31 字节，槽数和发送时序不变。其余协议状态机和完整 30147 字节补丁不变。两个构建入口均采用 area / map_option 2；实测 GAO 构建已完成布局，使用 11854 Logic、12316 FF、21 BSRAM，生成 `impl/pnr/ao_0.fs`。

脚本保留 JTAG 专用功能，并将 READY/DONE 复用为 GPIO；E2 同时复用 CPU/SSPI 功能以接收系统时钟，遵循该器件的官方示例选项。两个调试构建入口显式设置 `bit_security 0`，允许临时 SRAM Program+Verify 读回校验。GW5A-25A 使用至少 15 MHz 的 JTAG TCK。可选 GAO 构建与只读采集方法见 `debug/GAO.md`。

`set_option -use_ready_as_gpio 1` 和 `-use_done_as_gpio 1` 的依据为本机 Gowin 手册 `IDE/doc/EN/SUG1220-2.0E_Gowin Software Tcl Commands User Guide.pdf` 第 3.3.20 节，印刷页 46/47（PDF 页 53/54）；语法表明确 0 为专用脚、1 为通用 I/O。

在本工程目录执行：

```sh
python3 tests/simulate.py
python3 tests/simulate.py --adapted
```

原包和资源适配副本均已使用 Icarus Verilog 运行 **5/5 通过**：

- 板级 POR、BT_DIS# 时序、I/O 输出使能、按键去抖、会话到期、重新启动以及 USB1 被动 SE0 监测。
- 原包 H5：握手、全双工 8E1、ACK、重复包、重传、SLIP、长度限制、背压、校验及奇偶校验错误。
- 原包 GATT：发现、ATT 错误、CCCD、控制器信用、回复队列、通知序号与 CRC。
- 原包整机模型：实际检查 30147 个补丁字节、120 个补丁分片，完成 HCI 初始化、ATT 发现、CCCD 和 3 个 CRC 有效通知。
- 错误 ROM 在补丁下载前被拒绝。

原包结果位于 `reports/simulation_results.json`，资源适配结果位于 `reports/adapted_simulation_results.json`，各项日志位于 `reports/*.log`。Vendor 包的 MANIFEST 40/40 校验通过，源码及原始 ZIP 保持原样。上述五项为仿真验证；本板 BLE 收发实测结果见本页开头和 `reports/ble_hardware_20261016.json`。

GAO 实际快照共有 128 个样本，均为 flags=`0x0F`、H5=`0x80`、init=`0x0B`、error=0、补丁片数=120、HCI 命令数低8位=132、ROM=2；即采样时已初始化、已连接、尚未订阅、没有失败。USB1 为 SE0、activity=0、SE0 sticky=1，仅说明被动监测未见跳变，不能据此判断 USB 枚举或故障。原始 CSV 为 `reports/ble_status_20261016_001418_174723_core0_window0.csv`，解析方法见 `debug/GAO.md`。

50 MHz 核心 Fmax=54.156 MHz、核心 setup/hold 无违例；GAO 内部跨独立 JTAG 时钟仍保留 -0.606 ns hold 报告。受保护 GAO 模块的后继同步链尚未核实，没有添加 false-path，也不宣称完整时序或 GAO CDC 签核通过。详见 `reports/gao_cdc_review.md`。

## 手机测试

1. 在手机安装并打开 nRF Connect，允许蓝牙扫描权限；保持手机靠近已接天线的开发板。
2. 配置 FPGA 后等待初始化完成（DONE 常亮）；也可通过下表的 JTAG 状态确认 initialized=1、failed=0、patch_fragments=120。
3. 扫描名称 **RTL8723-BLE**，连接该设备，发现服务 **FFF0** 和特征 **FFF1**。如过了 180 秒，按 SW1 重新开始。
4. 对 FFF1 执行 Read，应得到 20 字节测试数据；点击通知按钮订阅 CCCD（写入 `01 00`）。每约 500 ms 应收到一包，DONE 快闪。
5. 检查每包前 4 字节为 ASCII `BTST`（`42 54 53 54`）；随后 uint32 小端序号、uint32 小端毫秒计数、`00 01 02 03 04 05`，末 2 字节为前 18 字节 CRC16-CCITT（初值 FFFF、小端）。应用通常只能直接看原始十六进制，自动校验可稍后接电脑测试程序。
6. 记录扫描结果、连接/订阅状态、第一包内容及测试时间。只有实际完成这一流程，才能把本板 BLE 标记为验证通过。

## JTAG / GAO 状态

顶层 `status[767:0]` 加有 `syn_keep`，连接 `driver.debug` / `driver.core.debug`；不新增物理调试输出。每字 32 位，字 n 对应 `status[n*32 +: 32]`。需先在 Gowin 输出中确认这些网络被保留，GAO 使用最终网表中的名字；仅存在 RTL 声明不证明调试核已插入。

| 字 | 含义 |
| --- | --- |
| 0 | 魔数 0x42545647 |
| 1 | 调试格式版本 1 |
| 2 | bit0 outputs_active、1 H5 link_up、2 initialized、3 connected、4 subscribed、5 failed、6 session_ended；bits9～11 hci_valid_mask |
| 3 | uptime_ms，enable 后运行毫秒 |
| 4 | bits7:0 H5 状态、15:8 初始化状态、23:16 GATT 状态 |
| 5 | bits31:24 错误码、23:16 last_status、15:0 last_opcode |
| 6 | 已发 HCI 命令数 |
| 7 | 已完成补丁分片数，成功时 120 |
| 8 / 9 | H5 RX / TX 帧数 |
| 10 | 重传计数 |
| 11 / 12 | UART 错误 / 协议错误计数 |
| 13 | 通知计数 |
| 14 / 15 / 16 / 17 | ACL RX、ATT 请求、完成包、应用错误计数 |
| 18 / 19 | 蓝牙地址低 32 位 / 高 16 位 |
| 20 | bits7:0 ROM 版本、19:8 连接 handle |
| 21 | GATT 运行毫秒数 |
| 22 / 23 | CLK_HZ / BAUD，硬件应为 50000000 / 115200 |

错误码：1 初始化阶段传输失败，2 HCI 响应超时，3 HCI 状态非零，4 芯片型号不符，5 ROM 不为 2，6 地址响应长度异常，7 补丁分片回显异常，8 启动后 5 秒仍未建立 H5，9 运行中传输失败。观察错误码时同时记录 last_opcode、last_status、H5 状态及 UART/协议错误计数。
