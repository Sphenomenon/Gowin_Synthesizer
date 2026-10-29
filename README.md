# Gowin Synthesizer

这是运行在 Gowin GW5AST-LV138PG484AC2/I1 和 NEO Dock 31005 上的 FPGA 音频工作站。主工程位于 [`projects/138k`](projects/138k)，Push 2 连接板载 J18 USB-A，不经过 CH569。

## 架构与状态入口

- [全链路架构与工程收敛](docs/architecture/README.md)：实际运行链路、模块与状态归属、构建／验证／发布流程、风险与分阶段整改。后续开发先读此文和根目录 [AGENTS.md](AGENTS.md)。
- 最近记录的工作站配置 Flash 部署为 full85／`0x85`（2026-10-12），仍有全板时序、Push 重连和物理断电启动等验收缺口；见[部署索引](projects/138k/push2_workstation/usb_a/LATEST_WORKSTATION.json)及其证据。这不代表已重新读取当前 SRAM 内容。
- 最新记录的资源时序离线候选为 T24／`0xC1102024`，尚未板测或部署；见[候选清单](projects/138k/push2_workstation/usb_a/RESOURCE_TIMING_CANDIDATE.json)。离线候选、已验收基线和实际部署不能统称为“最新版”。

## 早期 P28／P29 验收记录（历史）

早期实体通过版本 P28 的 UserCode 为 `0x00000028`，位流 SHA256 为 `a6544465c4aad1bb7a07abfb6158f1a787927442698eaf8193e9bad080f2fbb1`。P28 已关闭旧 `effect_mask` reset 审计缺口，完整 routed audit、通用 MIDI 和音频回归通过；该轮从 `0x00006DE8` 只写 SRAM 并读回，Flash 未写。用户已确认 Push、连续压力、屏幕与灯光、MIDI、电脑键盘、HDMI、耳机、效果链、曲谱和录音控制正常。通用 MIDI `0x00006DE8`、P27 `0x00000027` 和 P10 继续保留为历史回退版本。

P29 USB IN 诊断当时已完成离线构建和完整审计，能分别回读传输/协议错误、重复 DATA、正常 NAK 和失联次数。候选 UserCode 为 `0x00000029`，SHA256 为 `b43d9e981cde16d571caeeea1ca2ca7e2031c556202cab48fa95eed6e6940581`。该轮没有下载或读回 P29，也没有写 Flash；此处保留其历史适用范围，不作为当前部署说明。

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

- [独立板级例程](example/README.md)：本版主板的 BLE/Wi-Fi 扫描、AK4493/功放与 RGB LCD 测试，含接线和独立验收记录。
- [25K 面板工程](projects/25k/README.md)：设备端源码、构建入口、独立例程与对接边界。
- [整机接口规划](整机接口规划.md)：138K／Push／25K分工、已确认MIDI映射与默认值、现有协议差异及待确认项。
- [`push2_workstation/usb_a`](projects/138k/push2_workstation/usb_a)：当前 USB-A 工作站源码、仿真、审计和版本记录。
- [`Prj1`](projects/138k/push2_workstation/results/workstation_20260911_174045_306332/Prj1)：冻结的 Gowin 工程源码基线。该目录名保留了来源，但 `impl`、`build` 和位流不进入 Git。
- [`ae350/scripts`](projects/138k/ae350/scripts)：AE350 辅助脚本。
- [AE350 硬件与软件参考](docs/ae350/README.md)：官方主频、RAM／ROM／Cache、DSP／浮点／NN、启动方式与现有工程配置，含官方原始 PDF、资料版本及校验清单。
- [`RTL8723DS BLE`](projects/138k/push2_workstation/usb_a/rtl/bluetooth/README.md)：138K 蓝牙驱动、J8 接线、独立/工作站集成构建和验证记录；模组实体测试待完成。
- [`Android 控制端`](clients/android/README.md)：0.2.10，支持25K业务协议、内置音频录音、可靠PCM/WAV下载及显式协商的二阶无损传输。
- [`25K蓝牙协议实测工程`](projects/25k/example/RTL8723DS_PROTOCOL/README.md)：已固化A25D，电脑有效PCM吞吐14.1→22.1 KB/s；含协议、RTL、APP适配及验收证据。该结果来自25K，138K主机业务顶层与硬件验收仍独立。
- [`touchboard_test`](projects/138k/push2_workstation/touchboard_test)：QT2160 触摸板独立信号测试、接线资料、仿真和调试记录；采样异常仍待解决，实板触摸尚未验收。

## 构建

当前完整工作站从 [可版本化输入闭包](projects/138k/push2_workstation/usb_a/baselines/README.md) 重建 accepted／timing85／资源时序基线，不再依赖本机忽略的历史暂存树。清单绑定来源和哈希，缺失或改动明确失败；需要重建 USB 固件的路径仍须准备 RISC-V bare-metal 工具链。先按 accepted full83 输入策略准备工程副本：

```sh
python3 projects/138k/push2_workstation/usb_a/build.py --current-workstation --prepare-only
```

资源时序候选是另一套输入策略，仅准备、不烧录：

```sh
python3 projects/138k/push2_workstation/usb_a/build.py --resource-rework --resource-timing --prepare-only
```

不带整机选择参数的 `build.py` 保留早期构建路径，不是当前完整工作站默认入口。完整构建需显式选择策略并分配新的 UserCode；详见[架构中的构建流程](docs/architecture/README.md#8-统一研发与交付流程)。构建产物、捕获文件和位流留在本地。正式版本通过输入清单、UserCode、SHA256、SRAM 写前/写后读回和实体结果记录，不靠 `LATEST_BUILD.txt` 判断；准备／构建不会自动授权板卡操作。

## 早期 P 系列缺口（历史）

旧 `effect_mask_sync_[0..2]_s0/RESET` 缺口已在 P28 关闭。USB IN error 诊断已在 P29 离线候选中实现并通过完整 routed audit，尚待以后单独 SRAM 下载和实体检查；P28 板端记录仍为 `null`。

版本边界、忽略规则和提交范围见 [`GIT_SCOPE.md`](GIT_SCOPE.md)。

后续工程收口、谱面引导、3D 空间混响、物理建模音色、录音和连接方向见 [`ROADMAP.md`](ROADMAP.md)。
