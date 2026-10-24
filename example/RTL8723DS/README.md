# 138K RTL8723DS：BLE + Wi-Fi 扫描

面向 `GW5AST-LV138PG484AC2/I1` 与 Hardware 中的主扩展板、RTL8723DS 无线子板。BLE 参考 `../GW_25k/example/RTL8723DS_BLE`，原始驱动、30,147 字节 ROM-v2 补丁及其 MANIFEST 保留。Wi-Fi 使用新增的原生 1-bit SDIO 通路。

本例包含 BLE 广播、GATT 读取/通知、Wi-Fi SDIO 识别，以及通过 JTAG/SDIO 桥执行的主机侧 Wi-Fi 固件下载和 2.4GHz 被动扫描。扫描可读取 SSID、BSSID、信道及安全类型；尚未实现连接路由器、IP 或 TCP/UDP。

**2026-10-23 板上 Wi-Fi 扫描已收到真实信标。** 最终脚本覆盖 1–13 信道的一次实测收到 282 个接收包，识别 15 个 BSSID，其中 11 个有名称、4 个隐藏 SSID，见 `reports/wifi_scan_final.json`。此前一轮曾识别 16 个 BSSID，见 `reports/wifi_scan_verified.json`；各轮可能因漏收信标而不同。这是板上 RTL8723DS 的接收结果，电脑仅经 JTAG 控制和解析数据。固件 ready、SDIO ID 或零收包均不会算作扫描通过。

**2026-10-23 虚焊修复后，按原引脚实板验证通过。** BLE H5 握手成功、ROM=2、120 片补丁加载完成；电脑扫描到 `RTL8723-BLE`，连接 FFF0/FFF1、读取及连续 10 条通知均通过，CRC 正确、序号连续、间隔均为 500ms。Wi-Fi SDIO 识别 `024c:d723`，功能 1 ready。没有反转引脚或排线映射，也没有修改 RTL/位流。原始结果见 `reports/jtag_after_repair_original.json`、`reports/ble_after_repair_original.json`、`reports/jtag_after_repair_gatt.json`；最终运行状态见 `reports/verification_after_repair.json`。

## 硬件连接

使用本项目主板 J2 与 FPC3；子板 FPC1 与主板 FPC3 按 `n ↔ 25−n` 对应，排线接触面需与实际连接器一致。Bank5 供电必须为 3.3V。

| 顶层端口 | FPGA 球号 | 方向/含义 |
| --- | --- | --- |
| clk_50mhz | V22 | 核心板 50MHz |
| restart_n | V13 | 主板 DIP_SWITCH_0，低有效；正常运行置 OFF，内部上拉 |
| module_uart_tx | W12 | 模块 UART_OUT → FPGA 输入 |
| module_uart_rx | T14 | FPGA 输出 → 模块 UART_IN |
| module_bt_dis_n | AA9 | 低复位、高运行 |
| module_wl_dis_n | AA13 | 低关闭 Wi-Fi、高运行 |
| wifi_sd_clk | V10 | FPGA 输出，默认 250kHz |
| wifi_sd_cmd | W11 | 双向命令线 |
| wifi_sd_dat[0] | AB12 | 识别镜像只读；扫描镜像双向，传送 CMD53 数据 |
| wifi_sd_dat[1] | Y12 | 只读，保留上拉并报告线态 |
| wifi_sd_dat[2] | W10 | 同上 |
| wifi_sd_dat[3] | Y11 | 同上 |
| debug_uart_tx | U15 | BL616 接收端，115200 / 8N1 状态输出 |

模块 BT_HOST_WAKE_DEV 保持由子板 10kΩ 上拉，不主动驱动。PCM 线不分配、不驱动。核心板原参考工程的 AB13 按键不能直接沿用为复位，因为本版扩展板把 AB13 接到模块 HOST_WAKE；本例改用主板 V13 拨码复位。

其他 USB、HDMI、LCD、摄像头、音频 DAC、TF 管脚没有在本例中主动输出。构建保留 JTAG，下载脚本仅支持 SRAM Program+Verify。

## 启动和 BLE

1. 配置后约 1024 个 50MHz 周期完成 POR；DIP_SWITCH_0 应保持 OFF。
2. BLE 的 BT_DIS# 拉低 200ms、释放后等待 2000ms。
3. 使用 UART **115200 / 8E1、H5/HCI** 握手、检查 ROM-v2、下载 120 片完整补丁并配置广播。
4. 扫描 `RTL8723-BLE`；服务 `FFF0`，可读、可通知特征 `FFF1`。
5. 读取应为 20 字节，通知约每 500ms 一条，包含 `BTST`、序号、毫秒计数和 CRC16。

这不是 8N1 AT 模块。模块 UART 的 8E1 与电脑状态串口的 8N1 不同。

本版板级实例设置 `SESSION_MS=0`，生成的核心适配把它定义为持续运行并使 uptime 饱和，修正原始包中 0 表示立即到期的行为；vendor 原件没有改动。正数会话参数仍保留原语义。

BLE 服务保留参考包的断线行为：断开后不会自动重新广播。需要再次连接时，将 DIP_SWITCH_0 置 ON 至少 20ms，再置 OFF 至少 20ms，重做完整初始化。失败后也使用此方式重启。状态串口独立于拨码复位运行，保持复位时仍会输出诊断帧。

## 板上 Wi-Fi 扫描

扫描使用独立的 `wifi_scan_top` SRAM 镜像（UserCode `13802303`），原引脚不变，BLE 核心持续自主运行。FPGA 提供 128-bit JTAG 邮箱、2048 字节缓冲及带 CRC16 的 1-bit/250kHz CMD53 引擎；Python 提供最小 Wi-Fi 初始化、信道调谐和信标解析。此镜像的 U15 状态 UART 保持空闲，使用 JTAG 邮箱读取状态，不使用下方旧镜像的 GAO/状态串口工具。

在本目录运行已验证镜像：

```sh
python3 program_sram.py --manifest reports/build_20261023_211729_194831.json
python3 tools/wifi_scan.py --dwell 3 --output reports/wifi_scan_new.json
```

镜像 SHA256 为 `2882bec533aa126786d42cd7f54f8c7dc50fd854e89e4754ba68f08538eb0fab`。下载只写 FPGA SRAM；Wi-Fi 固件也只下载到模块 RAM，不写 Flash 或 eFuse。使用本机 Gowin Programmer 的 D2XX 库；不能同时运行占用同一 FTDI 通道的 Programmer/GAO 程序。有多个 FT2232 时用 `--location` 明确选择。

初始化顺序：枚举 `024c:d723` → CMD52 电源时序 → CMD53 读写核对 → 只读工厂 eFuse（本板晶振 cap=19、S1 天线）→ NIC 固件校验和下载 → MAC/BB/AGC/RF 表 → RX DMA/过滤器 → S1 接收 IQ 校准 → H2C active 唤醒 → 逐信道接收。**固件 ready 后仍须显式发送 active 电源模式命令**；此前缺少此步骤时 RF 信道读回与内部 IQ 校准通过，但没有收到信标。

每个 BSSID 合并为一个结果，空 SSID 表示隐藏网络。报告保存最多 64 个原始接收包、固件状态、工厂参数和 IQ 校准结果。仅从管理帧推断安全类型，`WPA2/RSN` 表示存在 RSN IE，不进一步区分 WPA2/WPA3；未输出未经校准的 RSSI。低速桥可能漏收信标，扫描列表不是穷尽结果。

扫描结束或接收阶段异常时停止 Wi-Fi MAC 并交还天线控制权给 BT；这不是完整的 BLE/Wi-Fi 并发 PTA 调度驱动。当前 RX IQ 校准仅支持已实测的工厂 S1 配置。默认扫描 1–13 信道，每信道 1 秒；`--channels 1,6,11 --dwell 3` 可指定范围与停留时间。

退出处理实测见 `reports/verification_wifi_ble.json`：扫描后 BLE FFF1 读取与 10 条通知均通过，CRC 正确、序号连续、间隔 500ms。仅还原扫描前寄存器会留下 Wi-Fi MAC 和无 PTA 调度的复位状态，曾导致 BLE 连接超时；最终脚本显式停止 Wi-Fi MAC、给予 BT grant 并将天线控制权交回 BT。

重新构建扫描镜像及运行传输/解析检查：

```sh
python3 tools/gowin_build.py build_wifi_scan.tcl
python3 tests/radio.py
python3 -m unittest discover -s tests -p 'test_wifi_scan.py' -v
```

构建后使用对应的新 manifest 下载，不要误用其他构建更新的 `last_build.json`。Wi-Fi 初始化表、NIC 固件来自 `lwfinger/rtl8723ds` 固定提交，来源、SHA256 和 GPL-2.0 许可证见 `vendor/wifi/provenance.json` 和 `vendor/wifi/COPYING`；BLE 原包仍保留。

## 原自主镜像：Wi-Fi SDIO 识别

原自主识别镜像（UserCode `13802301`）使用 `sdio_command.v`，在 SD_CLK 下降沿改变命令，上升沿采样响应，生成/核验 CRC7，检查帧格式、响应命令号、超时及 R1b busy。此镜像数据线始终为输入，不发送 CMD53。

`sdio_identify.v` 执行：

1. WL_DIS# 拉低 200ms，释放后再等 200ms，加至少 80 个空闲时钟。
2. CMD0；CMD5 查询 IO OCR、功能数和共同工作电压。
3. CMD5 以 3.2～3.4V 范围轮询 ready，有限重试。
4. CMD3 获取非零 RCA；CMD7 选卡并等待 DAT0 结束 busy。
5. CMD52 function 0 读取 CCCR 版本、卡能力、common CIS 指针和 function 1 接口码。
6. 有边界地遍历 CIS NULL/未知 tuple，读取 MANFID，并核对 Realtek `024c:d723`。
7. 先读 IOEx，保留其他功能位，置 bit1；轮询 IORx bit1。只有功能 1 ready 才设置 `done=1`。

`identified=1` 只表示 ID 已匹配；若功能 1 未就绪，仍会失败，不能当作完成。遇到其他产品 ID 会报告实际 ID 并返回 `unexpected_vendor_device`，不会默认为 RTL8723DS。

默认 SD_CLK 为 250kHz，保持在识别阶段的低速范围。CMD/DAT 先经过 50MHz 两级同步，再在 card rising tick 使用；只切除外部端口到第一级的异步路径，级间与后续路径正常检查，不使用多周期放宽。同步延迟远小于 2µs 半周期；提高 SD_HZ 时必须重新核对同步延迟与板级时延，本版不是高速 SDIO 数据通路的签核。

## 构建、仿真和下载

在本目录执行：

```sh
sh run_sim.sh
sh build.sh
python3 program_sram.py --manifest reports/last_build.json --check-only
python3 program_sram.py --manifest reports/last_build.json --frequency 2.5MHz
```

依赖 Python 3、Icarus Verilog 与 Gowin EDA。默认 EDA 路径为 `/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE`，可用 `GW138K_IDE_DIR` 覆盖。构建在新建 ASCII 临时目录中分进程综合与 PnR，结果写入 `builds/<时间戳>/`，索引为 `reports/last_build.json`。下载前检查器件、SHA256、UserCode、保护位及 setup/hold 违规数。

回归包括参考包原版 5 项、存储适配版 5 项、新增 SDIO 正常/异常场景、262 字节状态串口完整帧/快照一致性，以及连续 BLE 会话设置。SDIO 测试使用引脚级卡模型，核对主机命令 CRC 和参数，覆盖坏 CRC、超时、帧错误、R5/R6 错误、电压不符、CIS 异常、错误产品 ID 与功能 1 不就绪。

## 实板状态串口

U15 接到核心板 BL616 接收端；需要 BL616 透传固件及对应 USB 接口，或外接 3.3V USB-TTL 接收 U15 并共地。FT2232 的第二通道不等于该串口。以下端口名仅为示例，应替换为实际接收端：

```sh
python3 tools/status.py --port /dev/cu.usbserial-31201 --seconds 15 --output reports/status_new.json
```

工具只依赖 Python 标准库，同时保存 `.raw` 原始串口记录。每行格式为 `RF13 ` + 32 个 8 位大端十六进制文本字 + LF，无字间空格；每 500ms 间隔发送一致快照。前 24 字保留 BLE 调试 ABI，后 8 字为 SDIO：

| 字索引 | 内容 |
| --- | --- |
| 0 | BLE 签名 `42545647` |
| 2 | bit0 active、1 H5 link、2 initialized、3 connected、4 subscribed、5 failed、6 session_ended |
| 3 / 5 / 7 | BLE uptime / 错误-状态-操作码 / 补丁片数 |
| 8～13 | BLE RX 帧、TX 帧、重试、UART 错误、协议错误、通知数 |
| 20 | 低 8 位为 ROM 版本 |
| 24 | SDIO 签名 `5344494f` |
| 25 | 高 8 位错误码；bit19:16 DAT 线态；15:10 step；7:4 state；bit3 failed、2 identified、1 done、0 WL enable |
| 26 | IO OCR |
| 27 | RCA[31:16]、CCCR revision[15:8]、card capability[7:0] |
| 28 | function 1 接口码[31:24]、CIS 指针[23:0] |
| 29 | 厂商 ID[31:16]、设备 ID[15:0] |
| 30 / 31 | 最后响应 / 已完成命令数 |

错误码说明见 `tools/status.py` 的 `ERRORS` 表。串口工具只有在 BLE 初始化成功、Wi-Fi 身份匹配且功能 1 就绪、两者均无失败时才返回成功。

BLE 空口检查使用参考工具：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r tools/requirements-ble.txt
.venv/bin/python tools/ble_check.py --output reports/ble_new.json
```

BLE 原包的权利和固件来源见 `vendor/rtl8723ds_ble/NOTICE.md`、`firmware_manifest.json` 与 `MANIFEST.json`。历史 25K 的实测结论不等于本板实测，138K 的验证结果单独记录在本目录 reports 中。


## JTAG 实板诊断（2026-10-23）

已完成普通与 GAO 镜像的 SRAM Program+Verify。`reports/production_build.json` 保存原普通镜像；`reports/last_build.json` 指向最近一次成功构建（可能为普通、GAO 或扫描镜像）。GAO 不需要 BL616 串口；以下命令先构建 GAO 镜像，再立即使用它的 manifest：

```sh
python3 tools/gowin_build.py build_gao.tcl
python3 program_sram.py --manifest reports/last_build.json --allow-gao
python3 tools/jtag_status.py --manifest reports/last_build.json --output reports/jtag_status_new.json
```

修复前的历史结果 `reports/jtag_status_20261023.json`：JTAG 捕获有效，50MHz 时钟、POR 和拨码复位正常；BLE H5 link-start 超时（错误 08），有效接收帧为 0、固件片数为 0；Wi-Fi CMD5 无响应（错误 11），OCR、RCA、厂商/设备 ID 均未读出。内部 TX 计数在失败后仍会增长，但物理 UART 输出已高阻，因此该计数不能当作全部实际发送的证据。

修复前 GAO 另记录启动以来 UART 接收下降沿 2 次、合法 8E1 字节 1 个（FE）、早期错误 29 次，之后为高电平空闲；这些历史数据不能当作 H5 应答。用户随后修复无线板虚焊，重新下载完全相同的原引脚镜像即通过。

修复后首轮 JTAG：BLE RX/TX 帧为 270/272，补丁片数 120，驱动 UART/协议错误均为 0；SDIO OCR=`90ffffff`、RCA=`0001`、ID=`024c:d723`、20 条命令完成、错误码 00。空口测试后 JTAG 通知计数为 10，与电脑接收条数一致；RX/TX 帧增长至 322/324。独立原始 UART 监视器仍保留早期启动错误 29 次，未增长；它与 BLE 驱动的有效接收统计不同。

因此本次无需执行用户授权的“原引脚失败后再反转”分支。当前原图 `主板 FPC3 n ↔ 子板 FPC1 (25−n)` 映射得到 BLE 双向通信与 SDIO 识别的功能性验证；没有做逐针通断测量，也没有据此宣称 4-bit SDIO 高速或 Wi-Fi 网络通信已验证。原故障在修焊后消失，具体哪个焊点导致仍未单独定位。

另通过 `../AK4493_AMP/reports/jtag_vccio5.json` 的内部 ADC 独立测得本核心板 VCCIO5 约 3.375～3.402V、1418 次有效转换且无超时，排除 Bank5 处于低电压档位。该读数不代表无线子板电源或连接已验证。
