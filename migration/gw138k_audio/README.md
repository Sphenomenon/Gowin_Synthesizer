# GW5AST-138K 音频工作站

这里是 Gowin Synthesizer 的 138K 主工程。芯片为 GW5AST-LV138PG484AC2/I1，底板为 NEO Dock 31005。Push 2 固定连接 J18 USB-A，D+ 为 H13，D− 为 G13；网口旁 USB-C 和 CH569 不在当前演奏或音频路径中。

当前实体通过版本支持 Push 2 和通用 USB MIDI 1.0，UserCode `0x00006DE8`，位流 SHA256 为 `5ae02d9fac533df10f5921272b8243304acb7011d6bacd4877b6bbeb9dbf961f`。用户已确认通用 MIDI 和现有链路正常，随后只读检查仍为该 UserCode。该次下载由用户自行完成，SRAM/Flash 写入方式没有可核对记录，不能写成 Flash 未写。P27 `0x00000027` 保留为上一实体稳定回退版本。

当前版本的说明、资源、时序和验收记录在 [`push2_workstation/usb_a/README.md`](push2_workstation/usb_a/README.md)、[`GENERIC_MIDI_VERIFICATION.md`](push2_workstation/usb_a/GENERIC_MIDI_VERIFICATION.md) 和 [`BOARD_CURRENT_GENERIC_MIDI.json`](push2_workstation/usb_a/BOARD_CURRENT_GENERIC_MIDI.json)。构建入口是 [`push2_workstation/usb_a/build.py`](push2_workstation/usb_a/build.py)。

```sh
python3 migration/gw138k_audio/push2_workstation/usb_a/build.py --prepare-only
python3 migration/gw138k_audio/push2_workstation/usb_a/build.py
```

每次完整构建都会创建新的 `usb_a/results/build_*` 目录。构建目录、位流、实现数据库、仿真波形和捕获文件不提交；版本 JSON 保存 UserCode、SHA256、SRAM 读回和实体结果。需要发布可直接下载的稳定位流时，应把它作为 GitHub Release 附件，并保留 P10 回退版本。

当前仍有两个已知缺口：完整 routed audit 只因 `effect_mask_sync_[0..2]_s0/RESET` 三个旧端点失败，USB IN error 诊断仍为 `null`。其余历史目录只是本地参考，不代表当前板上版本。
