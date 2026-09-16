# P26 交互延迟优化验证

2026-09-16：源码审计、数字延迟测量、定向仿真、完整构建、routed audit 和 SRAM 下载/读回已完成。P26 UserCode 为 `0x00000026`，Flash 未写。用户随后完成实体交互与既有功能回归并报告“没问题，继续”，P26 已通过验收。

## 定向验证

最终记录为 `results/build_20260916_191636_144481/p26_latency_192818_701320/verification.json`。四种包场景覆盖正常包、不同像素起点、像素读取背压和第 639 包尾部，均验证 512 字节长度、字节顺序、交替 XOR、黑色 padding、NAK 重装和 FIFO 内容。无停顿包均为 769 个 48 MHz 周期。

数字音频测量使用五个样本相位：

| 输入边界 | 到 core | 到 PCM32 | 到 DAC16 |
|---|---:|---:|---:|
| Push MMIO 已接受 | 0.141–13.462 us | 35.568–55.568 us | 104.784–124.784 us |
| 电脑 115200，首起始位 | 256.232–269.278 us | 295.552–311.384 us | 385.596–401.436 us |
| DIN 31250，首起始位 | 944.170–956.734 us | 983.008–998.840 us | 1073.056–1088.876 us |

Push 行不含实体 pad 与 USB 轮询。电脑和 DIN 行包含各自 260.417 us、960 us 的三字节线路时间。完整 Vex CPU/USB/音频回归 `build_20260916_185143_142234/cpu_audio_sim_185626_176002` 通过 3817 帧，覆盖 A/B/C、五音色、FX7、颤音、滑音、弯音、路由和释放；P23 PANIC 回归 `p23_panic_192818_716604/verification.json` 也通过。

## 构建与审计

正式构建：`results/build_20260916_191636_144481`。它复用相同 P26 综合网表，只重新执行带精确 PLL helper 子位置约束的 P&R；综合实际消费的 RTL、ROM、`boot.mem` 和 USB 固件映像均一致。重新链接但不参与综合的 `boot.elf` 哈希差异单独记录在 `reused_synthesis.json`。

| 项目 | P24 | P26 |
|---|---:|---:|
| setup 违例 | 0 | 0 |
| hold 违例 | 0 | 0 |
| 最差 setup slack | +0.087 ns | +0.041 ns |
| Logic | 34848 | 34971 |
| Register | 25381 | 25380 |
| BSRAM | 253 | 253 |
| DSP | 43.5 | 43.5 |

位流 header CheckSum 为 `0x4EA6`，SHA256 为 `b23c31c0b35776ce459a01ef62889845dd58025a2977f705826fa8b8e46c10ba`。独立音频 PLL/mailbox routed audit 通过，PLL_INIT 最大传播 9.945 ns。完整 `usb_a_audit.json` **未通过**，错误仍且只有三个旧 `effect_mask_sync_[0..2]_s0/RESET` stopped-clock reset 覆盖缺口。

## SRAM 与实体结果

下载记录：`../results/sram_20260916_192918_415778/result.json`。实际写前读回 P24 `0x00000024`，只执行 SRAM operation 2，写后读回 P26 `0x00000026`；before/sram/after 均通过，`fpga_flash_written:false`。

用户检查 Push 屏幕操作速度和画面、Push pad/连续压力/灯光、电脑键盘长按、HDMI、耳机及效果链后报告“没问题，继续”。下载后的立即读回已经确认 P26；验收后的附加只读因下载线当时没有枚举而未执行，不能把这次缺失写成额外读回通过，也不改变已完成的写后验证。数字结果和实体结论分别保留。
