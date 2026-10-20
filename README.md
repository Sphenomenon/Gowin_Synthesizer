# Gowin Synthesizer

这是运行在 Gowin GW5AST-LV138PG484AC2/I1 和 NEO Dock 31005 上的 FPGA 音频工作站。主工程位于 [`projects/138k`](projects/138k)，Push 2 连接板载 J18 USB-A，不经过 CH569。

当前实体通过版本为 P28，UserCode `0x00000028`，位流 SHA256 为 `a6544465c4aad1bb7a07abfb6158f1a787927442698eaf8193e9bad080f2fbb1`。P28 已关闭旧 `effect_mask` reset 审计缺口，完整 routed audit、通用 MIDI 和音频回归通过；从 `0x00006DE8` 只写 SRAM 并读回，Flash 未写。用户已确认 Push、连续压力、屏幕与灯光、MIDI、电脑键盘、HDMI、耳机、效果链、曲谱和录音控制正常。通用 MIDI `0x00006DE8`、P27 `0x00000027` 和 P10 继续保留为回退版本。

P29 USB IN 诊断已完成离线构建和完整审计，能分别回读传输/协议错误、重复 DATA、正常 NAK 和失联次数。候选 UserCode 为 `0x00000029`，SHA256 为 `b43d9e981cde16d571caeeea1ca2ca7e2031c556202cab48fa95eed6e6940581`。本会话按用户要求没有下载或读回 P29，也没有写 Flash，因此当前实体稳定版本仍记为 P28。

## 工程目录

一个 Git 仓库管理两个同级板级工程，公共规划留在仓库根目录：

```text
fpga/                         Git 根目录
├── projects/                 板级工程的共同父目录
│   ├── 138k/                 138K 主机，现有完整源码与本地构建资料
│   └── 25k/                  25K 面板，设备端源码、独立例程与硬件资料
├── clients/android/          安卓控制端、协议与可靠录音下载
├── 整机接口规划.md            跨板职责、消息与待定接口
└── migration/gw138k_audio -> ../projects/138k
                              旧路径兼容链接
```

新代码和文档使用 `projects/138k/`、`projects/25k/`。旧路径链接用于历史命令、绝对路径和验收记录；实际源码只有一份。25K 目录已导入设备端源码、独立例程、硬件资料和已有验证摘要；138K 联调状态仍以各工程记录为准。各目录职责见 [projects/README.md](projects/README.md)。

## 入口

- [25K 面板工程](projects/25k/README.md)：设备端源码、构建入口、独立例程与对接边界。
- [整机接口规划](整机接口规划.md)：138K／Push／25K分工、已确认MIDI映射与默认值、现有协议差异及待确认项。
- [`push2_workstation/usb_a`](projects/138k/push2_workstation/usb_a)：当前 USB-A 工作站源码、仿真、审计和版本记录。
- [`Prj1`](projects/138k/push2_workstation/results/workstation_20260911_174045_306332/Prj1)：冻结的 Gowin 工程源码基线。该目录名保留了来源，但 `impl`、`build` 和位流不进入 Git。
- [`ae350/scripts`](projects/138k/ae350/scripts)：AE350 辅助脚本。
- [`RTL8723DS BLE`](projects/138k/push2_workstation/usb_a/rtl/bluetooth/README.md)：138K 蓝牙驱动、J8 接线、独立/工作站集成构建和验证记录；模组实体测试待完成。
- [`Android 控制端`](clients/android/README.md)：0.2.10，支持25K业务协议、内置音频录音、可靠PCM/WAV下载及显式协商的二阶无损传输。
- [`25K蓝牙协议实测工程`](projects/25k/example/RTL8723DS_PROTOCOL/README.md)：已固化A25D，电脑有效PCM吞吐14.1→22.1 KB/s；含协议、RTL、APP适配及验收证据。该结果来自25K，138K主机业务顶层与硬件验收仍独立。
- [`touchboard_test`](projects/138k/push2_workstation/touchboard_test)：QT2160 触摸板独立信号测试、接线资料、仿真和调试记录；采样异常仍待解决，实板触摸尚未验收。

## 构建

仓库保存了构建所需的冻结 USB Host 源码、输入清单和 DDR 审计参考网表。先准备工程副本：

```sh
python3 projects/138k/push2_workstation/usb_a/build.py --prepare-only
```

完整构建会在 `usb_a/results/` 中创建新目录：

```sh
python3 projects/138k/push2_workstation/usb_a/build.py
```

构建产物、捕获文件和位流留在本地。正式版本通过 UserCode、SHA256、SRAM 写前/写后读回和实体结果记录，不靠 `LATEST_BUILD.txt` 判断。

## 已知缺口

旧 `effect_mask_sync_[0..2]_s0/RESET` 缺口已在 P28 关闭。USB IN error 诊断已在 P29 离线候选中实现并通过完整 routed audit，尚待以后单独 SRAM 下载和实体检查；P28 板端记录仍为 `null`。

版本边界、忽略规则和提交范围见 [`GIT_SCOPE.md`](GIT_SCOPE.md)。

后续工程收口、谱面引导、3D 空间混响、物理建模音色、录音和连接方向见 [`ROADMAP.md`](ROADMAP.md)。
