# P27 Push 控制绑定验证

2026-09-17：P27 已完成源码审计、定向仿真、完整回归、完整构建、分项 routed audit、SRAM 下载和用户实体验收。板上及位流 UserCode 均为 `0x00000027`，Flash 未写。

## 实现结果

- Push CC85 Play 经原 48 MHz→76.8 MHz 事件 FIFO 和仲裁器切换现有曲谱播放器。AE350 自检后装入 9 条、共 4 秒的 LED 引导；每 24000 个 48 kHz sample frame 将四个绿色 pad 向右移动，末条 mask 为零。曲谱仍只有绝对 sample 时间戳和 32 bit LED mask，不产生音符或预录 PCM。
- CC86 Record 切换现有 256 帧有界 recorder 的 enable。它只改变既有录音状态，不新建文件、音符或播放路径。
- CC62/63 在 A/B/C 间向前、向后循环；仍等待原模式提交条件。
- CC28 切换效果总开关。关闭只把有效 mask 置零，选择和 P10 串行顺序继续保存；重新打开恢复相同 mask 与顺序。
- CC27/29 继续发 P23 硬 PANIC。PANIC 清理范围没有在本阶段扩大。

Push 按下/松开去重、pad held、poly-aftertouch、P20 力度映射、32 声部分配和统一事件背压保持原路径。曲谱、录音和 LED 状态用 34 bit 应答式 mailbox 从音频域传到 USB 域；实体 held 灯优先于曲谱提示。公开屏幕协议仍是 16 字节头加 640 个 512 字节像素包。

## 仿真与构建

最终定向记录：`results/build_20260917_021137_154460/p27_controls_022242_694555/verification.json`。三组测试分别通过 Push 映射/松开/held 去重和灯光、曲谱 RAM/时间/最终零 mask/录音开关/无音符、以及有序面板命令、A/B/C wrap、效果 mask/顺序跨关闭和 PANIC 后保持。

P23 PANIC 回归为 `p23_panic_022242_712744/verification.json`。完整 CPU/USB/音频回归为 `cpu_audio_sim_022242_689512/verification.json`：3817 帧、3430 个非零帧，覆盖 A/B/C、五音色、FX7、颤音、滑音、弯音、路由和释放；48 kHz 精确且无 audio fault。

正式构建：`results/build_20260917_021137_154460`。

| 项目 | P26 | P27 |
|---|---:|---:|
| setup 违例 | 0 | 0 |
| hold 违例 | 0 | 0 |
| 最差 setup slack | +0.041 ns | +0.258 ns |
| Logic | 34971 | 34966 |
| Register | 25380 | 25605 |
| BSRAM | 253 | 253 |
| DSP | 43.5 | 43.5 |

位流 header CheckSum 为 `0xFF04`，SHA256 为 `dcd14a32b18a947ba807ea86a6780762176bbe3fcba1c7c020490b615016c101`。构建器返回 0，综合输入未被工具改写。

首个完整实现 `build_20260917_015832_139391` 的普通 setup 数据路径为正，但新增服务 mailbox 的六条异步复位 recovery 路径未采用现有 CDC 约束，报告 setup violated endpoints 为 6，因此未下载。P27 为该实例补入与其他 `gw138k_stream_cdc` 相同的 held payload、握手同步器和异步清除约束后重新完整构建，最终 setup/hold 均为零。一次复用综合尝试 `build_20260917_021043_991120` 因 `boot.elf` 嵌入结果目录路径而被输入哈希保护拒绝，没有执行 P&R，也不是候选。

正确层级的音频 routed audit `p27_audio_routed_audit_correct_hierarchy.json` 通过。新增服务 CDC 的 `p27_service_cdc_routed_audit.json` 保留全部 34 bit，最大 C→Q+route 为 1.165 ns，双级握手同步器和约束均通过。完整 `usb_a_audit.json` **未通过**，失败仍且只有既有三个 `u_managed/effect_mask_sync_[0..2]_s0/RESET` stopped-clock reset 覆盖缺口。第一次音频分项调用使用默认 `u_audio` 层级而产生的失败文件也保留；正确工程层级是 `u_managed/u_audio`。

## SRAM 与实体结果

下载记录：`../results/sram_20260917_022557_608020/result.json`。写前读回 P26 `0x00000026`，随后只执行 SRAM operation 2，写后读回 P27 `0x00000027`；三步均通过，`fpga_flash_written:false`。用户按清单检查 Play 曲谱灯、Record 状态、A/B/C 左右循环、效果总开关恢复、PANIC，以及电脑键盘、Push pad/连续压力/屏幕/灯光、MIDI、HDMI、耳机和效果链后回复“没问题”。

验收后只读记录为 `../results/readback_p27_20260917_023328_460597/result.json`，仍是 ID Code `0x0001081B`、UserCode `0x00000027`、Status Code `0x00026230`。该操作只读设备代码，没有再次下载，也没有写 Flash。USB IN error 诊断仍为 `null`。
