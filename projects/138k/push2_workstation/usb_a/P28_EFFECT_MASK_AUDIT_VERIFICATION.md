# P28 效果状态 routed audit 验证

## 构建与静态检查

正式结果目录为 `results/build_20260918_031112_483932`，综合结果来自 `results/build_20260918_024612_204363`。`reused_synthesis.json` 记录除约束外的 Gowin 工程输入完全一致；`boot.elf` 只含非确定性链接元数据，不是 Gowin 输入，实际综合使用的 `boot.mem` 仍逐字节校验。

位流 UserCode 为 `0x00000028`，SHA256 为 `a6544465c4aad1bb7a07abfb6158f1a787927442698eaf8193e9bad080f2fbb1`，大小 42,197,761 字节。P&R 结果：

| 项目 | 结果 |
|---|---:|
| setup 违例 | 0 |
| hold 违例 | 0 |
| 最差 setup slack | +0.063 ns |
| 最小 pulse-width slack | +1.325 ns |
| Logic | 34,895 |
| Register | 25,638 |
| BSRAM | 253 |
| DSP | 43.5 |

音频 PLL 初始化路径最大值为 9.771 ns，端点为 RESET。完整 `usb_a_audit.json` 通过，并证明六个 effect-mask 同步寄存器没有活动复位端点、两级数据关系正确，负向变异会被拒绝。旧 `effect_mask_sync_[0..2]_s0/RESET` 缺口已经实际关闭。

## 必要回归

- `cpu_audio_sim_032137_549287/verification.json`：通过。覆盖 A/B/C、五种音色、七种效果组合、颤音、滑音、弯音、路由、释放、48 kHz PCM 和无音频故障，共 3,817 帧，其中 3,430 帧非零。
- `generic_midi_032137_549581/verification.json`：通过。固件描述符、动态 Bulk IN 端点、包长、事件解析、热插拔、满 FIFO、断开和 Push 保留行为均通过；RTL 共核对 240 个有序事件和 12,772 个背压周期。

这些结果证明数字实现和回归，不代替 Push、HDMI 或耳机的实体检查。

## SRAM 下载

下载记录为 `../results/sram_20260918_032323_026486/result.json`。下载前读回 `0x00006DE8`，只执行 SRAM 操作，下载后读回 `0x00000028`；设备 ID 为 `0x0001081B`，状态码为 `0x00026230`。`fpga_flash_written=false`，Flash 未写。

当前待检查项目是 Push pad 与连续压力、屏幕与灯光、通用 MIDI、电脑键盘、HDMI 三种分析内容、耳机和串行效果链。通过前，P28 只记为候选版本。
