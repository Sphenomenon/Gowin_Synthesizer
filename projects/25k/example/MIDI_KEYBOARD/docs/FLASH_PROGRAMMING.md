# Flash固化记录

## 本轮仅构建：0x00003BE9，未烧录

2026-10-17完成USB2外部输入画面、E1长按设置与MK/PL共存的完整回归、构建及时序检查。用户明确要求“先完成构建，暂不烧录”，本轮没有Flash写入、重载或实机屏控测试；`reports/last_program.json`仍指向下述0x00005A52。待下载位流与校验见 [BUILD_VALIDATION.md](BUILD_VALIDATION.md)。

## 当前版本：2026-10-17 03:37，0x00005A52

已固化Android Legacy Just Works配对、HCI命令信用/超时恢复，以及两个编码器反向半速。触摸和60 Hz区域显示逻辑保留。

| 项目 | 结果 |
| --- | --- |
| 位流 | [midi_keyboard.fs](../builds/20261017_033415_116117/impl/pnr/midi_keyboard.fs)，7,178,789字节 |
| SHA256 | `91819e9d4c7971c9fb1b53144c3d5822e6ca0b7c100cbed4b9fe6b377e5aa73e` |
| FPGA / Flash ID | `0x0001281B` / `0x0B4017` |
| 下载器 | FT2CH channel0，2.5 MHz |
| 写入与校验 | operation54成功，operation1重载成功 |
| 读回 | UserCode=`0x00005A52`、Status=`0x70022020` |
| USB附带观察 | `GW25K MIDI Screen`，配置1、480 Mbps |

烧录前31个HDL测试台、9项Python测试及73项检查通过，setup/hold违规0/0，输入与位流哈希一致。证据：[本次汇总](../reports/hardware_20261017/flash_20261017_033701_135721/summary.json)、[写入日志](../reports/hardware_20261017/flash_20261017_033701_135721/program.log)、[版本读回](../reports/hardware_20261017/flash_20261017_033701_135721/device_after.log)、[最新记录](../reports/last_program.json)。首次Flash ID探测在写入前失败，[失败日志](../reports/hardware_20261017/flash_20261017_033643_807857/flash_id.log)保留，相同参数重试正确识别后才执行写入。首次受限构建的许可证连接超时，具备许可证访问权限后综合/PnR/时序通过。

用户已从真实Android手机确认系统配对成功、MIDI应用可连接。本轮未实际断电，音符收发和长时间演奏仍未实测确认。bond仅存RAM，复位后需要忘记手机旧配对再重新配对；见 [蓝牙说明](BLE_IMPLEMENTATION.md) 与 [本轮验证](BUILD_VALIDATION.md)。

## 历史恢复版本：2026-10-17 03:13，0x0000F054

按用户要求恢复此前60 Hz区域显示固件，停止G/H排查。64项构建输入已恢复原哈希，诊断源码、工具和测试已归档。复用原已验证位流，本次重新写入板载Flash。

| 项目 | 结果 |
| --- | --- |
| 位流 | [midi_keyboard.fs](../builds/20261017_015947_664453/impl/pnr/midi_keyboard.fs)，7,232,301字节 |
| SHA256 | `07f2c363b463982f3ea7ed300603267951c2e03225a4d0bb105e285faa87d1c4` |
| FPGA / Flash ID | `0x0001281B` / `0x0B4017` |
| 下载器 | FT2CH channel0，2.5 MHz |
| 写入与校验 | operation54成功，operation1重载成功 |
| 读回 | UserCode=`0x0000F054`、Status=`0x70022020` |
| USB附带观察 | `GW25K MIDI Screen`，配置1、480 Mbps |

恢复后回归通过：27个HDL测试台、9项Python测试、65项检查，121项输入哈希匹配，setup/hold违规0/0。证据：[本次汇总](../reports/hardware_20261017/flash_20261017_031320_034194/summary.json)、[写入日志](../reports/hardware_20261017/flash_20261017_031320_034194/program.log)、[版本读回](../reports/hardware_20261017/flash_20261017_031320_034194/device_after.log)、[最新记录](../reports/last_program.json)。首次Flash ID探测在写入前失败，[失败日志](../reports/hardware_20261017/flash_20261017_031259_682500/flash_id.log)保留；相同参数重试正确识别后才执行写入。本轮通过重载确认Flash加载，未做实际断电测试。

## 历史诊断版本：2026-10-17 03:05，0x0000B301

已写入G/H与滑条误触诊断固件，保留60 Hz区域显示、按键映射和演奏配置。新增USB原始触摸读取、可恢复U2扫描暂停；这不是已修复误触的声明。

| 项目 | 结果 |
| --- | --- |
| 位流 | [midi_keyboard.fs](../builds/20261017_030218_654822/impl/pnr/midi_keyboard.fs)，7,339,285字节 |
| SHA256 | `94a588b5135d231ff50f0b045f8ac67d0fe25025b2c6ffc1d4a77319dd3bc1d2` |
| FPGA / Flash ID | `0x0001281B` / `0x0B4017` |
| 下载器 | FT2CH channel0，2.5 MHz |
| Flash | operation54写入及校验成功，operation1重载成功 |
| 读回 | UserCode=`0x0000B301`、Status=`0x70022020` |
| USB | `GW25K MIDI Screen`，配置1、480 Mbps；厂商接口已实际读到G/H诊断 |

烧录预检：29个HDL测试台、9项Python测试、69项检查通过，setup/hold违规0/0，输入与位流哈希一致。证据：[汇总](../reports/hardware_20261017/flash_20261017_030504_479065/summary.json)、[编程日志](../reports/hardware_20261017/flash_20261017_030504_479065/program.log)、[读回](../reports/hardware_20261017/flash_20261017_030504_479065/device_after.log)。首次Flash探测在写入前失败，保持相同参数重试后成功；[失败日志](../reports/hardware_20261017/flash_20261017_030453_383230/flash_id.log)保留。该诊断版本已撤回，按用户要求停止排查；见 [归档说明](TOUCH_CROSSTALK.md)。

## 历史版本：2026-10-17 02:09，0x0000F054

已固化60 Hz场景快照、变化区域更新、50 MHz连续SPI与四像素预取FIFO。全部动态区域RTL仿真11.539220 ms；全屏重画19.450840 ms，当前结论为动态界面60 Hz，不是任意全屏或实屏扫描60 fps。

| 项目 | 结果 |
| --- | --- |
| 固件 | [midi_keyboard.fs](../builds/20261017_015947_664453/impl/pnr/midi_keyboard.fs)，7,232,301字节 |
| SHA256 | `07f2c363b463982f3ea7ed300603267951c2e03225a4d0bb105e285faa87d1c4` |
| FPGA / Flash ID | `0x0001281B` / `0x0B4017` |
| 下载器 | FT2CH channel0，2.5 MHz JTAG |
| 写入 | operation54，起始`0x000000`，工具确认`Program and Verify Flash successfully.` |
| 重载与读回 | operation1成功；UserCode=`0x0000F054`、Status=`0x70022020` |
| USB附带观察 | `GW25K MIDI Screen`，`FB9A:FB9B`、配置1、480 Mbps |

烧录前27个HDL测试台、9项Python协议测试及65项检查通过，Gowin setup/hold违规0/0，源码、构建与位流哈希一致。证据：[汇总](../reports/hardware_20261017/flash_20261017_020854_057435/summary.json)、[写入日志](../reports/hardware_20261017/flash_20261017_020854_057435/program.log)、[读回日志](../reports/hardware_20261017/flash_20261017_020854_057435/device_after.log)、[最新记录](../reports/last_program.json)。

先前一次Flash ID探测在写入前失败，保留于[失败探测日志](../reports/hardware_20261017/flash_20261017_020326_179887/flash_id.log)；相同2.5 MHz重试正确识别后才执行写入。本轮未做实际断电测试、SPI外部波形或LCD扫描帧率测量。显示架构与限制见 [DISPLAY_60HZ.md](DISPLAY_60HZ.md)。

## 历史版本：2026-10-17 01:02，0x0000856D

本轮已将采样起始间隔保护、配置前RESET基线、配置后RESET重配、U2滑条独立诊断和12.5 MHz LCD写入板载Flash。已确认的键序、灯序和反向横屏保留。

| 项目 | 结果 |
| --- | --- |
| 固件 | [midi_keyboard.fs](../builds/20261017_010056_274646/impl/pnr/midi_keyboard.fs)，7,018,285字节 |
| SHA256 | `4e8a93557693e76a241cdf70a23e5a1dcc5afd2f6ff743eb8fe22ca49f2812a3` |
| FPGA / Flash ID | `0x0001281B` / `0x0B4017` |
| 下载器 | FT2CH channel0，2.5 MHz JTAG |
| 写入 | operation54，起始`0x000000`，工具报告结束`0x00D5B00` |
| 写入校验 | `Program and Verify Flash successfully.`，returncode 0 |
| 重载与读回 | operation1成功；两次UserCode=`0x0000856D`、Status=`0x70022020` |
| USB2 | 本轮未在macOS USB树中找到目标；一次不擦写重载后仍未识别，等待检查数据口连接 |

烧录前25测试台、61项检查、9项Python测试及Gowin构建/时序通过，输入与位流SHA256匹配，SecurityBit/Encryption均OFF。证据见[汇总](../reports/hardware_20261017/flash_20261017_010237_271287/summary.json)、[写入日志](../reports/hardware_20261017/flash_20261017_010237_271287/program.log)、[读回](../reports/hardware_20261017/flash_20261017_010237_271287/device_after.log)、[重载后USB复核](../reports/hardware_20261017/flash_20261017_010237_271287/reload_usb_retry.json)。

Flash写入、校验、重载和身份核验已完成；整体`passed=false`仅因USB枚举尚未确认，不能解读为未写入新固件。该轮状态保存在独立汇总中；[last_program.json](../reports/last_program.json)指向最新固化结果。未进行实际断电重启，也未实测触摸噪声改善或屏幕帧率。USB缺项与实物效果不会由历史版本的成功记录替代。

## 前一基线：2026-10-17 00:42，0x00006712

已固化完整A–P映射、NTHR12、按键12/10迟滞和滑条滤波。24测试台与Gowin时序通过；Flash写入校验、重载及UserCode=`0x00006712`、Status=`0x70022020`读回成功，USB设备`GW25K MIDI Screen`，`FB9A:FB9B`、配置1、480 Mbps。

位流为[004004构建](../builds/20261017_004004_496655/impl/pnr/midi_keyboard.fs)，SHA256=`8f44c00003edfa9969a21a4071d3198bc746752ccf23134fd854eeeb1456c5ec`，7,125,673字节。证据见[004235烧录汇总](../reports/hardware_20261017/flash_20261017_004235_132207/summary.json)。此前004205探测失败发生在写入前；随后相同2.5 MHz重试成功。

## 历史版本：2026-10-17 00:28

本轮已固化WS2812按键链序、PCA9685滑条灯、屏幕180°翻转及右侧竖滑条。H–P映射未补全，触摸键序保持原始通道。本轮固化后UserCode为`0x00003D0B`。

| 项目 | 结果 |
| --- | --- |
| 新固件 | [midi_keyboard.fs](../builds/20261017_002202_037686/impl/pnr/midi_keyboard.fs)，7,072,565字节 |
| SHA256 | `d8583b1f128d2b18a8508525cb0cfb43244e7109e286fd93a2e5ff0808e16944` |
| FPGA / Flash ID | `0x0001281B` / `0x0B4017` |
| 下载连接 | FT2CH channel0，2.5 MHz JTAG |
| 编程 | operation54，起始`0x000000`，工具报告结束`0x00D7600` |
| 结果 | `Program and Verify Flash successfully.`，returncode 0 |
| 重载确认 | operation1成功；UserCode=`0x00003D0B`，Status=`0x70022020` |
| USB2 | `GW25K MIDI Screen`，`FB9A:FB9B`，配置1，480 Mbps |

证据：[汇总](../reports/hardware_20261017/flash_20261017_002737_484663/summary.json)、[编程日志](../reports/hardware_20261017/flash_20261017_002737_484663/program.log)、[重载后状态](../reports/hardware_20261017/flash_20261017_002737_484663/device_after.log)、[USB枚举](../reports/hardware_20261017/flash_20261017_002737_484663/usb_after.log)。该历史记录保留于上述独立目录；[last_program.json](../reports/last_program.json)指向最近一次写入及后续核验结果。

下载器重新连接后15 MHz Flash探测曾失败，降低到2.5 MHz后识别、写入、校验及重载均成功；失败与重试日志完整保留。未实际切断板卡电源；显示、触摸及灯光的实物效果未由本记录代替验收。

## 首次固化版本：2026-10-17 00:08

2026-10-17 00:08（Asia/Shanghai）已将完整MIDI键盘固件写入板载Flash启动区，写入后校验通过，并成功从Flash重新加载。

| 项目 | 实测结果 |
| --- | --- |
| FPGA / JTAG ID | GW5A-25A / `0x0001281B` |
| 下载器 | Gowin FT2CH，channel 0，15 MHz |
| Flash ID / 容量 | `0x0B4017` / 8 MiB |
| 编程操作 | operation 54：exFlash Erase,Program,Verify Arora V |
| 起始地址 / 工具报告结束地址 | `0x000000` / `0x00D5B00` |
| 编程结果 | `Program and Verify Flash successfully.`，returncode 0 |
| Flash重载 | operation 1：Reprogram，returncode 0 |
| 重载后UserCode / Status | `0x0000DF05` / `0x70022020` |
| USB枚举 | `GW25K MIDI Screen`，`FB9A:FB9B`，配置1，480 Mbps |

固件为 [midi_keyboard.fs](../builds/20261017_000007_402332/impl/pnr/midi_keyboard.fs)，文件大小7,018,697字节，SHA256为：

```text
17292b440e0070d2605d8bca6d9d8ace2b97812c63a3882288fc6d5e1e380737
```

编程前已核对构建清单、器件型号、SecurityBit OFF、UserCode及实际setup/hold报告。下载器在受限环境中无法访问USB，改用具备硬件访问权限的执行环境后扫描成功。

证据保存在 [汇总JSON](../reports/hardware_20261017/flash_summary.json)、[编程结果](../reports/hardware_20261017/flash_program_20261017.json)、[原始编程日志](../reports/hardware_20261017/flash_program_20261017.log)、[Flash重载](../reports/hardware_20261017/reload_flash.log)、[重载后器件状态](../reports/hardware_20261017/device_after.log)及[USB枚举摘录](../reports/hardware_20261017/usb_after.log)。各JSON保留实际CLI参数，可复核设备与操作。

启动位流已持久保存，板卡配置为从该Flash启动时，上电会加载此版本。本次通过Reprogram验证Flash加载，未实际切断电源；USB枚举不代表音符收发、BLE连接、真实触摸、灯光和屏幕显示均已完成实板验收。
