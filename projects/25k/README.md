# GW25K 面板工程

本目录于 2026-10-19 从本地 `GW_25K` 导入，保留 `example/`、`prj/`、`docs/` 及硬件资料的原始相对结构。主控为 GW5A-LV25MG121NC1/I0，显示屏为 NV3007 142×428 SPI。

屏幕 NV3007 142*428 SPI

主控芯片[GW5A-LV25MG121NC1/I0](http://www.gowinsemi.com.cn/prod_view.aspx?TypeId=74&FId=t3:10:3&Id=188)

芯片例程 https://github.com/sipeed/TangPrimer-25K-example

USB3300 480 Mbps CDC 回环例程：[example/USB3300_HS](example/USB3300_HS/README.md)

USB1 12 Mbps CDC 回环例程：[example/USB1_FS](example/USB1_FS/README.md)

NV3007 142×428 SPI 屏幕例程：[example/NV3007_LCD](example/NV3007_LCD/README.md)

双编码器与屏幕调试例程：[example/ENCODER_LCD](example/ENCODER_LCD/README.md)

RTL8723DS BLE 广播、读取与通知例程：[example/RTL8723DS_BLE](example/RTL8723DS_BLE/README.md)

完整16键触摸 MIDI 键盘（USB2 MIDI/独立屏幕接口、BLE MIDI、触摸条、双编码器、PCA9685/WS2812与428×142横屏）：[example/MIDI_KEYBOARD](example/MIDI_KEYBOARD/README.md)


## 构建与仿真

从本仓库根目录执行完整 MIDI 键盘工程：

```sh
sh projects/25k/example/MIDI_KEYBOARD/run_sim.sh
sh projects/25k/example/MIDI_KEYBOARD/build.sh
```

构建需要 Gowin EDA，仿真需要 Python 3、Icarus Verilog 与 vvp。各独立例程的具体依赖与入口见对应 README。旧文档中的 `example/...` 命令以本目录 `projects/25k` 为工作目录。

## 导入范围与整机对接

来源与文件校验清单见 [SOURCE_IMPORT.json](SOURCE_IMPORT.json)。源码、测试、约束、构建工具、冻结依赖、硬件设计资料和已有验证摘要进入 Git；`builds/`、`impl/`、仿真缓存、波形、生成位流和普通工具日志留在原本地目录。BLE 原始固件和上游清单要求的报告／日志作为冻结输入保留。源码清单中的旧位流路径及历史绝对路径保留原样，克隆后应重新构建；已有 `verified_build.json` 仅记录历史证据，其指向的位流未随本次导入上传。

公共职责与产品范围以仓库根目录的 [整机接口规划](../../整机接口规划.md) 为对接依据；主机侧 [PL 规范](../138k/push2_workstation/usb_a/GW25K_PANEL.md) 与本工程的 [设备端显示协议](example/MIDI_KEYBOARD/docs/PANEL_DISPLAY_PROTOCOL.md) 应逐项核对。导入保留当前独立工程的本地功能和历史验证记录，不代表已完成 138K 联调或已将公共规划全部接入。原始第三方许可、NOTICE 与来源清单随代码保留；未重新授权。
