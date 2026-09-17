# Gowin Synthesizer

这是运行在 Gowin GW5AST-LV138PG484AC2/I1 和 NEO Dock 31005 上的 FPGA 音频工作站。主工程位于 [`migration/gw138k_audio`](migration/gw138k_audio)，Push 2 连接板载 J18 USB-A，不经过 CH569。

当前实体通过版本支持 Push 2 和通用 USB MIDI 1.0，UserCode `0x00006DE8`，位流 SHA256 为 `5ae02d9fac533df10f5921272b8243304acb7011d6bacd4877b6bbeb9dbf961f`。用户已确认通用 MIDI 与现有 Push、显示、音频和效果链工作正常；随后只读检查仍为该 UserCode。该次下载由用户自行完成，仓库没有可核对的写入记录，因此 SRAM/Flash 写入方式记为未知。P27 `0x00000027` 继续作为上一实体稳定回退版本。

## 目录

- [`push2_workstation/usb_a`](migration/gw138k_audio/push2_workstation/usb_a)：当前 USB-A 工作站源码、仿真、审计和版本记录。
- [`Prj1`](migration/gw138k_audio/push2_workstation/results/workstation_20260911_174045_306332/Prj1)：冻结的 Gowin 工程源码基线。该目录名保留了来源，但 `impl`、`build` 和位流不进入 Git。
- [`ae350/scripts`](migration/gw138k_audio/ae350/scripts)：AE350 辅助脚本。

## 构建

仓库保存了构建所需的冻结 USB Host 源码、输入清单和 DDR 审计参考网表。先准备工程副本：

```sh
python3 migration/gw138k_audio/push2_workstation/usb_a/build.py --prepare-only
```

完整构建会在 `usb_a/results/` 中创建新目录：

```sh
python3 migration/gw138k_audio/push2_workstation/usb_a/build.py
```

构建产物、捕获文件和位流留在本地。正式版本通过 UserCode、SHA256、SRAM 写前/写后读回和实体结果记录，不靠 `LATEST_BUILD.txt` 判断。

## 已知缺口

完整 routed audit 仍会在 `effect_mask_sync_[0..2]_s0/RESET` 三个旧端点失败。USB IN error 诊断尚未实现，记录值仍为 `null`。这两项不能写成已通过。

版本边界、忽略规则和提交范围见 [`GIT_SCOPE.md`](GIT_SCOPE.md)。

后续工程收口、谱面引导、3D 空间混响、物理建模音色、录音和连接方向见 [`ROADMAP.md`](ROADMAP.md)。
