# GW5AST-138K 音频工作站

本工程现位于 `projects/138k/`，与 [25K 面板](../25k/README.md) 同级；内部目录保持原结构。旧 `migration/gw138k_audio/` 是兼容链接。跨板接口见 [整机接口规划](../../整机接口规划.md)。以下 P28／P29 内容为原有版本记录，当前离线进度以工作站 README 和接口规划为准。

这里是 Gowin Synthesizer 的 138K 主工程。芯片为 GW5AST-LV138PG484AC2/I1，底板为 NEO Dock 31005。Push 2 固定连接 J18 USB-A，D+ 为 H13，D− 为 G13；网口旁 USB-C 和 CH569 不在当前演奏或音频路径中。

板上当前实体通过版本为 P28，UserCode `0x00000028`，位流 SHA256 为 `a6544465c4aad1bb7a07abfb6158f1a787927442698eaf8193e9bad080f2fbb1`。完整 routed audit、通用 MIDI 和音频回归通过；P28 从 `0x00006DE8` 只写 SRAM 并完成前后读回，Flash 未写。用户已确认完整实体回归正常。通用 MIDI `0x00006DE8`、P27 `0x00000027` 和 P10 继续保留为回退版本。

P29 USB IN 诊断已形成离线候选：UserCode `0x00000029`，SHA256 `b43d9e981cde16d571caeeea1ca2ca7e2031c556202cab48fa95eed6e6940581`，完整 routed audit 和必要回归通过。本会话没有下载、读回或写 Flash，P29 也没有实体验收。

当前说明、资源和时序记录在 [`push2_workstation/usb_a/README.md`](push2_workstation/usb_a/README.md) 与 [`P29_USB_IN_DIAGNOSTICS_VERIFICATION.md`](push2_workstation/usb_a/P29_USB_IN_DIAGNOSTICS_VERIFICATION.md)；板端稳定版本仍以 [`BOARD_CURRENT_P28_EFFECT_MASK_AUDIT.json`](push2_workstation/usb_a/BOARD_CURRENT_P28_EFFECT_MASK_AUDIT.json) 为准。构建入口是 [`push2_workstation/usb_a/build.py`](push2_workstation/usb_a/build.py)。

```sh
python3 projects/138k/push2_workstation/usb_a/build.py --prepare-only
python3 projects/138k/push2_workstation/usb_a/build.py
```

每次完整构建都会创建新的 `usb_a/results/build_*` 目录。构建目录、位流、实现数据库、仿真波形和捕获文件不提交；版本 JSON 保存 UserCode、SHA256、SRAM 读回和实体结果。需要发布可直接下载的稳定位流时，应把它作为 GitHub Release 附件，并保留 P10 回退版本。

P28 已关闭 `effect_mask_sync_[0..2]_s0/RESET` 的旧缺口，完整 routed audit 与实体回归通过。P29 已在源码和离线位流中补齐 USB IN 诊断，等待以后单独 SRAM 下载和实体检查；P28 的板端字段仍为 `null`。其余历史目录只是本地参考，不代表当前板上版本。
