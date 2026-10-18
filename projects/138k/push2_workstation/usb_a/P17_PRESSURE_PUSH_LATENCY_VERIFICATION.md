# P17 连续压力兼容与 Push 屏幕调度候选

状态：P17 已完成 RTL、综合/布局布线和 SRAM 下载，等待本轮实体验收。P16 的压力增益、P14 C 模式 32 声部、P13 共享 DDR 显示数据、P10 串行效果链和 P2 低音路径均保留。

## 本轮改动

- Push MIDI 解码同时接受 CIN `0xA` poly-aftertouch 和 CIN `0xD` channel pressure。CIN D 没有显式音符，使用最近仍按下的 pad；两种消息都只更新 expression，不重触发或释放声部。
- 保留原 Push USB-A 屏幕帧格式：16 字节帧头、640 个 512 字节数据包和原 XOR/行填充。固件改为每 16 个屏幕包轮询一次 MIDI、每 32 个包服务一次灯光，并在帧尾补一次灯光服务，避免每个空闲包都等待一次 MIDI IN。

## 仿真与回归

- `push_pressure_kind13_recheck_20260915_0916/simulation.log`：CIN A 的压力 0/127 和 CIN D 的压力 23 均产生 kind 5 expression 事件，held 保持，映射数为 4。
- `p11_shared_101854_755534/simulation.log`：Push 共享摘要和效果 mask latch 通过。
- `cpu_audio_sim_101958_720046/simulation.log`：3696 个音频帧、3574 个非零帧，A/B/C、音色、效果、表达/路由/释放及 48 kHz 时序通过。
- `production_usb_firmware_test.log`：重新枚举、空闲 NAK、重复包、端点 toggle、拔线中断帧及重连后的 640 包帧通过。

这些是 RTL、CPU/USB 模型和固件离线测试，不代替实体 Push、HDMI 或耳机验收；屏幕真实延迟仍需板上测量。

## 综合、布局布线与资源

构建目录：`results/build_20260915_095312_067431`，器件 `GW5AST-LV138PG484AC2/I1`。

| 项目 | 结果 |
|---|---:|
| setup 违例端点 | 0 |
| hold 违例端点 | 0 |
| Logic | 33,820 |
| Register | 25,164 |
| BSRAM | 253 |
| DSP | 43.5 |

现有检查仍报告两个历史缺口：旧 DDR reset 证据源路径缺失，以及 `u_managed/effect_mask_sync_[0..2]_s0/RESET` stopped-clock 覆盖缺口。本轮没有扩大时序例外或改写该结论。

## SRAM

- 位流：`results/build_20260915_095312_067431/Prj1/impl/pnr/Prj1.fs`
- SHA256：`90a3d5563149a5ae40c431647fdb229730e8f3078812be4657e5d22f34fe9e02`
- UserCode：`0x0000F123`
- 下载记录：`../results/sram_20260915_101625_758975/result.json`
- 写前读回：P16 `0x0000C706`；SRAM 写入通过；写后读回 `0x0000F123`；三步均通过。
- `fpga_flash_written` 为 `false`，本轮未写 Flash。

## 实体验收边界

请在 P17 SRAM 上确认：

1. 按住同一 pad 改变压力，耳机声音、HDMI 相关状态和 Push 数值随压力变化；不重触发、不串声，松开仍按原逻辑释放。
2. Push 屏幕的 pad、模式/音色/效果卡片、数值和箭头跟随操作，灯光仍正常；比较 P16 的约 1 秒延迟是否明显降低。
3. HDMI waveform、李萨如图、频谱图、效果卡片顺序/箭头/动画保持正常。
4. C 模式多键、P10 串行效果链和 P2 低音保持正常。

真实屏幕刷新时间和输入到声音/画面的延迟以本次实测为准。
