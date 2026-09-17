# GW5AST-138K 音频工作站

这里是 Gowin Synthesizer 的 138K 主工程。芯片为 GW5AST-LV138PG484AC2/I1，底板为 NEO Dock 31005。Push 2 固定连接 J18 USB-A，D+ 为 H13，D− 为 G13；网口旁 USB-C 和 CH569 不在当前演奏或音频路径中。

板上当前为待实体回归的 P28，UserCode `0x00000028`，位流 SHA256 为 `a6544465c4aad1bb7a07abfb6158f1a787927442698eaf8193e9bad080f2fbb1`。完整 routed audit、通用 MIDI 回归和音频回归已通过；P28 从 `0x00006DE8` 只写 SRAM 并完成前后读回，Flash 未写。上一个已实体通过版本仍是通用 USB MIDI `0x00006DE8`，P27 `0x00000027` 保留为上一代理控制的实体稳定回退版本。

当前版本的说明、资源、时序和验收记录在 [`push2_workstation/usb_a/README.md`](push2_workstation/usb_a/README.md)、[`GENERIC_MIDI_VERIFICATION.md`](push2_workstation/usb_a/GENERIC_MIDI_VERIFICATION.md) 和 [`BOARD_CURRENT_GENERIC_MIDI.json`](push2_workstation/usb_a/BOARD_CURRENT_GENERIC_MIDI.json)。构建入口是 [`push2_workstation/usb_a/build.py`](push2_workstation/usb_a/build.py)。

```sh
python3 migration/gw138k_audio/push2_workstation/usb_a/build.py --prepare-only
python3 migration/gw138k_audio/push2_workstation/usb_a/build.py
```

每次完整构建都会创建新的 `usb_a/results/build_*` 目录。构建目录、位流、实现数据库、仿真波形和捕获文件不提交；版本 JSON 保存 UserCode、SHA256、SRAM 读回和实体结果。需要发布可直接下载的稳定位流时，应把它作为 GitHub Release 附件，并保留 P10 回退版本。

P28 已关闭 `effect_mask_sync_[0..2]_s0/RESET` 的旧缺口，完整 routed audit 通过。USB IN error 诊断仍为 `null`，是下一项工程收口；P28 的实体回归完成前不记为稳定版本。其余历史目录只是本地参考，不代表当前板上版本。
