# BLE 只读 GAO 观测

`build_gao.tcl` 是独立的可选构建入口；普通 `build.tcl` 不加载调试核。`ble_status.rao` 采用标准 GAO XML v3.0，结构参考 Sipeed 官方 UART 示例的 `src/uart.rao`。首版 427 位 × 512 点在实际布局时因 REG 无法放置失败；2026-10-16 已压缩为 **64 位 × 128 点**，同时更换 GAO_ID。资源适配后的压缩版已实际完成 Gowin 构建和布局，使用 11854 Logic、12316 FF、21 BSRAM（SDPB×1、SDPX×4、pROM×16）；该次生成镜像为 `impl/pnr/ao_0.fs`。

此核只采样用户逻辑，没有任何控制寄存器或额外外围输出。采样时钟 `clk_50mhz` 为 50 MHz；只保留判断初始化进度和 USB1 静态状态所需字段，删除大部分完整计数器。下表按 RAO 捕获顺序排列；将字段顺次拼接时，其位号对应 GAO `data_i[63:0]`，最终以生成网表和 CSV 列名核对。

| 快照位 | RAO 信号 | 含义 |
| --- | --- | --- |
| 63:57 | status[70:64] | 从 bit0 起：active、H5 link、initialized、connected、subscribed、failed、session_ended |
| 56:49 | status[135:128] | H5 状态 8 位 |
| 48:41 | status[143:136] | 初始化状态 8 位 |
| 40:33 | status[191:184] | 错误码 8 位 |
| 32:25 | status[231:224] | 补丁片计数低 8 位，成功值 120 |
| 24:17 | status[199:192] | HCI 命令计数低 8 位，正常单次启动不超过 132 |
| 16:9 | status[647:640] | ROM 版本，目标值 2 |
| 8:7 | usb1_line_state[1:0] | 同步后 {DP,DM}，00 SE0、10 FS J、01 FS K、11 SE1 |
| 6 | usb1_activity_seen | USB1 曾有线态变化 |
| 5 / 4 | usb1_se0_long_seen / usb1_se1_long_seen | 曾持续 SE0 / SE1 至少约 3 µs |
| 3 / 2 | module_uart_tx / tx | UART RX 引脚 / UART TX 逻辑数据 |
| 1 / 0 | bt_enable / drive_pins | BT_DIS# 输出数据 / UART与BT_DIS#共同输出使能 |

TX 引脚三态后的电气读值没有回采，需结合 `tx` 和 `drive_pins` 判断 FPGA 是否在驱动。128 点的纯采样数据为 8192 bit，原配置为 218624 bit，减少约 96%；实际 BSRAM 和寄存器数仍由工具映射决定。

静态触发表达式 `M0|!M0` 始终为真，因此每次启动即获得当时状态的快照；它不依赖初始化成功。未开启 `capture_init_data_enabled`，避免只得到 FPGA 刚启动时的全零状态。128 个 50 MHz 样本覆盖 2.56 µs，适合读状态，不能覆盖完整 115200/8E1 UART 帧（约 95.5 µs）。延迟不同时间重复捕获可判断补丁计数是否前进；如需串口整帧分析，再调整采样方案。

## 本板实测与 CSV 解码

2026-10-16 已通过临时 SRAM Program+Verify（UserCode=`0xEEDB`，状态=`0x70022020`），并实际采集到 `reports/ble_status_20261016_001418_174723_core0_window0.csv`。128 条样本的所有观察字段相同：flags=`0x0F`（active/link/initialized/connected=1，subscribed/failed/ended=0），H5=`0x80`、init=`0x0B`、error=0、patch=120、HCI commands低8位=132、ROM=2，RX/TX/BT使能/OE均为1。USB1 为 SE0、activity=0、SE0 sticky=1、SE1 sticky=0；这里只是被动线态观察，不能证明枚举成功或USB故障。

同次 macOS BLE 实测已扫描、连接并读取 FFF1，随后收到序号 0、1、2 的三个有效通知，CRC全部通过，包内毫秒计数相差500；证据为 `reports/ble_hardware_20261016.json`。快照中的未订阅位只表示那个采样时刻的状态，不否定后续通知测试结果。BLE 功能通过与下文尚未完成的 GAO CDC 签核分别记录。

从本工程目录解码真实 CSV：

```sh
python3 debug/decode_status.py reports/ble_status_20261016_001418_174723_core0_window0.csv \
  --output reports/ble_status_20261016_decoded.json
```

解析器按 CSV 列名读取十六进制数，输出总样本数与连续相同状态段，保留补丁/HCI计数仅低8位的含义；缺列、越界或未知值会报错。CSV 导出的首列虽然标记 `time unit: us`，本文件数值为0～127，**不能据该列推算UART位宽、真实采样间隔或BLE消息耗时**。解码 JSON 原样保留时间标签并标明此限制。

## 时钟约束

可选入口改用 `constraints/ble_bringup_gao.sdc`，保留普通工程相同的 50 MHz 核心时钟和外部异步输入约束；只额外在 GAO 实际生成的顶层输入 `tck_pad_i` 建立 JTAG 时钟。首版网表已确认该输入经过 IBUF 进入 GW_JTAG，再由其 tck_o 驱动 GAO 控制逻辑，因此约束放在真实时钟源。

JTAG 约束周期为 33.333 ns，按 FT2232HL MPSSE 最高 30 MHz 作保守目标；实际采集线速须不高于该频率。没有加入跨时钟 blanket false-path，也没有切断核心同步路径。若后续报告跨域时序失败，应查看具体端点及 GAO 的 CDC 后单独处理。普通 `build.tcl` 和普通 SDC 保持不变。

2026-10-16 的报告显示 50 MHz 核心 Fmax=54.156 MHz、核心 setup/hold 无违例，但总 hold 仍有一条 -0.606 ns：GAO 内 `capture_mem_wr_s1/Q` → `capture_end_tck_0_s0/D`，从核心时钟跨入独立 JTAG 时钟。可见报告还列出 `capture_end_tck_1_s0` 和 `_2_s0`，但 GAO RTL/映射网表受工具加密保护，当前无法核实它们的数据连接和亚稳态隔离。保留原始时序违例，不据名字添加例外；详见 `../reports/gao_cdc_review.md`。该镜像可用于可逆原型观测，但采集结果须与实际 BLE 广播、重复快照交叉核验，尚不能宣称 GAO CDC 或完整时序签核通过。

## 构建后采集

先由根任务构建、检查时序并向 SRAM 下载**对应的 GAO bitstream**。普通 BLE bitstream 不含此核，不能用此 RAO 直接采集。RAO 与 bitstream 的 GAO_ID 必须一致。

在本工程目录执行以下命令即可采样；脚本不含烧录命令，超时为 30 秒：

```sh
python3 debug/capture_status.py
```

原生命令形式为：

```sh
env DYLD_LIBRARY_PATH=/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/lib \
DYLD_FRAMEWORK_PATH=/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/lib \
/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/bin/gao_sh \
  -gao "$PWD/debug/ble_status.rao" -device GW5A-25A -cable FT2CH \
  -out "$PWD/reports/ble_status"
```

`-cable FT2CH` 选择普通 FTDI 通道 0；如果有多根下载器，可加 `-location <工具扫描出的实际位置>`。不要给未经确认的位置值。`capture_status.py` 默认用唯一时间戳前缀，实际文件名为 `ble_status_<时间戳>_core0_window0.csv`；以命令的 `Export ...` 日志为准，避免把旧 CSV 当作新采集。上面的原生命令使用固定前缀，重复手工执行前应自行改成新的输出名。

**本版本 `gao_sh` 是命令行采样程序，不是 Tcl Console。** 不要套用 `gw_sh` 的 Tcl 指令。静态检查当前本机二进制确认其命令参数为 `-gao`、`-out`、`-device`、`-cable`、`-location`，并在完成后调用 CSV 导出；没有发现 CLI 的 VCD 格式选择或 `-h` 帮助处理。没有相应 GAO bitstream 时不应把无法采集解释为 BLE 失败。

## VCD

本机 `gao_sh` 标准模式导出 CSV。需要原生 VCD 时，使用图形 GAO：

```sh
env DYLD_LIBRARY_PATH=/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/lib \
DYLD_FRAMEWORK_PATH=/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/lib \
/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/bin/gao_analyzer \
  -series GW5A -device GW5A-25A -gao "$PWD/debug/ble_status.rao"
```

在界面选择 Gowin USB Cable (FT2CH) 和实际通道，Start 单次采集后选择 Export，格式选 `*.vcd`。该 GUI 命令的参数依据为官方手册；当前没有实际启动或操作该界面。CSV 也可在获得真实文件格式后转换为 VCD，不能仅改扩展名。

## 依据与当前验证边界

- 本机 `SUG114-3.4.4E_Gowin Analyzer Oscilloscope User Guide.pdf`：第 3.1.1 节说明 RTL 调试配置为 `.rao`；第 3.1.2 节说明采样存储和触发表达式；第 4.1.1 节（PDF 页 46 / 印刷页 36）提供 `gao_analyzer` 命令行启动参数；第 4.1.2 节说明 FT2CH、通道和采集；第 4.1.3 节（PDF 页 61～63 / 印刷页 51～53）说明 VCD/CSV 导出。
- Sipeed 官方例程：`/private/tmp/gw25k-official-example-20261015/UART/simple_uart/src/uart.rao`。
- 当前本机 `IDE/bin/gao_sh` 静态符号/选项检查：`main` 识别以上五个参数；`GaoCmdStandardAnalyzer::onReadRamComplete` 生成 `_core%1_window%2.csv` 并调用 CSV 导出。这一项是本机实现检查，不能替代实际设备采样验证。

配置、脚本和文档由子任务维护；根任务已实际执行 SRAM 下载、GAO采集与 BLE收发验证，没有写入flash。调试数据应结合主 README 的 status 字布局解释。
