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

RTL8723DS 业务命令、内置音频录音与二阶无损下载（A25D / Android0.2.10）：[example/RTL8723DS_PROTOCOL](example/RTL8723DS_PROTOCOL/README.md)，含25K实板验收；APP源码位于仓库根`clients/android`。

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

## 138K对接控件（2026-10-19续验）

远程导入前的本地README已单独备份并保留在Git stash，导入正文和来源清单保持。完整设备工程已经补齐，原“只有说明、缺源码”的记录属于导入前状态。

已确认职责保持：Push直接接138K，25K连接触摸板与SPI屏；138K统一初始化音源，25K负责触摸转MIDI、本地移调和外围。当前138K Host为Full-Speed，设备USB HS/FS单元测试不代表主机已支持HighSpeed。CNN扒谱／引导仍为Push专有。

`example/MIDI_KEYBOARD`顶层默认`HOST_PANEL_CONTROLS=1`，实际应用使用新`gw138k_panel_performance`接入已确认映射：16键48–63、On100／Off0；滑条Pitch Bend左低右高、中心8192、释放回中，沿用原滤波并加可调中心死区；E1每物理档CC7变化1、短按CC89=1；E2按73／40／56／12／0循环Program、短按仅CC88=127。两个长按没有分配功能，Host页面期间旋转和短按继续工作。接入本地音量127／音色73对齐Host初值，不发送重复初始化或重连持音回放。

旧六参数控件、半速编码器和重连清理仍保留在兼容分支`HOST_PANEL_CONTROLS=0`，供历史独立测试和例程复现；该选择是构建参数，不是新增用户菜单。旧本地六卡诊断页面仍未改成专有演奏UI；Host的428×142基础页沿用原PL机制。主机其他控制源改变参数后的完整双向同步仍受现有MMIO／PL字段限制，不能把本地初始值对齐称作全量同步。

用户已确认25K专有方向是EP-133式4×4演奏／效果上下文，D采样器与TF PCM按补充口径保留，禁止直接播放预处理音乐冒充实时合成。效果上下文进入／退出、16键效果表、按住或锁定规则、作用路径，以及移调的最终产品入口／范围／越界仍待定；本批只落实已接受的控件和现有协议配置操作，不新增入口或长按。

测试工具现在支持`sh run_sim.sh --help`与`--output 新目录`，默认把新报告放`results/`，临时可执行文件使用系统临时目录，不覆盖导入报告，也不依赖macOS的`/private/tmp`。新控件测试使用真实USB-MIDI编码和既有MK配置端点；PL与138K生产Host另有真实RTL端点闭环。完整结果、输入哈希、保留的导入清单差异及硬件边界见[设备控件落地报告](../138k/push2_workstation/usb_a/reports/GW25K_CONTROLS_20261019.md)。无板测／烧录，无硬件或引脚修改，无新SYN／P&R／时序实验。
