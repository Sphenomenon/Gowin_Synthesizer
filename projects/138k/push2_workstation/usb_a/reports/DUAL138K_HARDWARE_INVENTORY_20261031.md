# 双 138K：本机只读硬件盘点（2026-10-31）

本次盘点于本地时间 17:43 读取 macOS USB、串口、音频、相机和 JTAG
枚举，不烧录、不复位、不重载 Flash，不打开或重配串口，不切换前台应用。
它用于准备后续 M/W 正式镜像验收，不构成声画、蓝牙、录音下载或双板并发验收。

## 当前可见连接

| 边界 | 实际观测 | 验收含义 |
| --- | --- | --- |
| Mac USB 调试器 | 一个 `Dual RS232-HS`，VID `0403`、PID `6010`，USB location `02120000`；无 USB 序列号字符串 | FT2232 的两个接口不能当作两块 138K |
| Gowin cable 枚举 | `FT2CH/0/8257`、`FT2CH/1/8258` | 需逐通道验证器件，不能凭 cable 数计板 |
| 8258 只读器件识别 | operation 0 返回码 **3**；ID、UserCode、Status 均 `FFFFFFFF` | 非有效 138K 识别；日志中的 `Finished.` 不代表成功 |
| 串口接口 A | `/dev/cu.usbserial-21200`，同一 FTDI 的 interface 0 | 与 JTAG 通道共用，不作为本轮 UART 采集口打开 |
| 串口接口 B | `/dev/cu.usbserial-21201`，同一 FTDI 的 interface 1 | 后续 UART 候选口；本轮未打开，未确认业务遥测 |
| 串口占用 | 两个设备均未被 `lsof` 列为已打开 | 只证明盘点时无已知占用 |
| HDMI 采集 | USB 树未发现 UVC／`USB3 Video`；相机列表仅内建 MacBook Pro 相机 | 当前没有已确认的 HDMI 到 Mac 采集路径 |
| 音频输入 | 仅 MacBook Pro 内建麦克风，44.1 kHz | 当前没有已确认的 138K DAC 数字／线路输入采集路径 |
| 音频输出 | FiiO KA3 为 USB 输出，44.1 kHz；QSN-CAB 为 Mac HDMI 输出，48 kHz；另有内建扬声器 | 这些输出不能作为 FPGA 的声音输入或画面采集证据 |

主代理另行读到 8257 上 `GW5AST-138C`：ID `0001081B`、UserCode
`C11028E5`、Status `00022020`。本盘点未对该通道重复操作；其读回需与主代理
独立操作日志一起引用。8258 的失败结果和一个 FTDI 的双接口映射都不支持
“第二块 138K 已连接”的结论。

Push／25K 若接在 FPGA USB Host 口，其枚举不属于 Mac USB 树；本盘点无法判断
板端附件、触摸面板、TF、DAC 耳机或显示器的实际插接。物理声画闭环仍需候选
身份、有效声画观测以及操作前后真实参数一致性证据。

## 只读命令与原始记录

原始记录保留在忽略的缓存目录：
`/Users/sphenicidition/.cache/gw138k-dual-20261031/hardware-inventory/`。
未把原始系统树、采集或实现产物加入源码。

```sh
ioreg -a -l -p IOUSB
ioreg -a -l
system_profiler SPAudioDataType SPCameraDataType -json
lsof /dev/cu.usbserial-21200 /dev/cu.usbserial-21201
/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/Programmer/bin/programmer_cli --scan-cables F
/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/Programmer/bin/programmer_cli --device GW5AST-138C --cable-index 1 --location 8258 --frequency 0.9MHz --operation_index 0
```

`system_profiler SPUSBDataType` 在本机未返回有效设备条目，因此 USB 判断采用
`ioreg` 的实际树。原始文件的 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| `usb.plist` | `dce8cac152175a0974666e0e02e3559c438f6f65c84cdaac0f18b448e6da23a4` |
| `serial-usb.plist` | `6f8dcc8dd6c4eaf19f0b3551767db92016d2115c99a84e04423871cb17a19b0d` |
| `audio-camera.json` | `b5cb3a8aff6a735922e5cae8a4642d4ae5bd9933fde5371f4c9b728135655a23` |
| `scan-cables.log` | `765766e7deab18067d48d446cb04d20ffdd84e170e98e71b7b4aca4d8f939c08` |
| `read-8258.log` | `09be836d4a98212dfb33190f98f5135356cb073c582950405c6836b88b1cf7c9` |

## 可复用的后续采集路径

已有 [2026-10-30 板测报告](WORKSTATION_AUDIO_PROBE_HARDWARE_20261030.md)
记录 Mac 实际 JTAG 为 8257、8258 的 GAO 识别失败，以及匹配 UserCode／探针
布局的重要性。其 B7 静音探针和历史完整 Verify 失败都不能替代 M/W 整机验收。
后续 GAO 应使用新候选自己的配置副本，并在采集前后核对该候选身份；不套用
B7 数据解码器到未知镜像。

`tools/capture_scope_smoke.py` 已有 CRC 遥测解码。`--business-only` 禁止
MIDI 写操作，但只核对业务状态页，不验证 REC／下载实际功能；默认非 exercise
模式也不发送控制业务。脚本在打开串口前设置 DTR/RTS 为 false。后续可在确认
候选 UART 格式和 Python `serial` 依赖后，串行执行新的只读记录，例如：

```sh
python3 projects/138k/push2_workstation/usb_a/tools/capture_scope_smoke.py --port /dev/cu.usbserial-21201 --seconds 15 --business-only --output /absolute/fresh-output.json
```

本轮未执行该命令；系统 `/usr/bin/python3` 当时缺少 pyserial。
`--exercise-controls`、`--exercise-polyphony`、`--exercise-live` 会发送业务请求，
应属于后续正式候选验证操作，而不是只读盘点。

`tools/capture_workstation_usb2_hdmi.py` 的解码逻辑可参考，但采集包装依赖历史
Linux helper、`gdb`、`LD_PRELOAD` 和固定 location 54，不能直接当作当前 Mac
采集命令。板级 I2S／DAC 引脚以 `boards/custom_138k/pinout.json` 为准；内部
样本计数与 JTAG 探针只补充数字证据，不能独立证明实际模拟出声。
