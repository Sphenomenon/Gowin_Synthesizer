# P2/P3/P4 candidate patch

本轮只生成新的候选构建目录，不改冻结输入、队友 Dev 仓库或旧位流。

- P2：`feedback_renderer` 的低音捕获使用原始过零滞回，超时从 256 提升到 2048 sample。MIDI 36 周期约 735 sample，避免下两排按键在过零前反复自动起捕。
- P3：`stereo_effects` 的输出寄存级按 `dry -> delay -> chorus -> reverb` 串行计算；HDMI 仪表盘显示 `CHAIN MIX>DLY>CHR>REV>ROUTE>DAC`。
- P4：AE350 score player 的 32 位 LED mask 经 USB 时钟域两级同步，曲谱运行时映射到 Push 前 32 个 pad（绿色），按下的实际演奏灯优先。

曲谱仍需通过 AE350 score MMIO 写 cue、写 length、写 START 才会有指引；自检结束后的停止状态会清灯。下一步可把一个 Push 未使用按键绑定到 score start/stop，但不在本补丁里引入菜单或新协议。
