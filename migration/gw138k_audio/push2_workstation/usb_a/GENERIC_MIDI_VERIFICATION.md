# USB-A 自动识别 Push / MIDI 1.0

2026-09-17；仅离线实现、构建和验证，未访问下载器、USB 设备或板端串口。沿用 VexRiscv + 现有 USB Host/PHY，12 Mbit/s。

```text
2982:9999 / 2982:1967 → 原 Push MIDI 映射 + 屏幕 + LED
其他 VID:PID + MIDI 1.0 IN → 通用 MIDI → 原音频事件 FIFO → 合成器
其余设备 → 应用保持未连接
```

`firmware.c` 保留 Push 的零接口描述符特例、EP2 MIDI、EP1 屏幕、初始化和 OUT toggle。通用分支读取当前配置，查找 Audio/MIDIStreaming、protocol 0、bcdMSC 1.00 的 Bulk IN，从描述符取得端点和最大包长；非零 alternate setting 只发送标准 SET_INTERFACE。不发送 Push 专用命令或应用 OUT 数据。

通用消息：Note On/Off、零力度 Note On、poly pressure、CC、Program Change、Pitch Bend → 现有 `{kind,a,b}`。音高/力度保持 0～127，CC 原样进入合成器控制入口。无 Push 36～99 音域限制、力度加 28、相对旋钮或面板按键转换。沿用现有单乐器模型，各 channel/cable 合并；未增加独立多通道声部归属。Channel Pressure、SysEx、实时消息尚未映射。

`rtl/push2_usb_a_control.sv` 只增加通用事件入口与模式门控；`push2_controls.sv` 的 Push 映射不改。
固件与 RTL 必须使用同一候选构建，旧 RTL 没有通用事件的 `0x54` 入口。

| MMIO 偏移 | 含义 |
|---|---|
| `0x00` | 0=未连接；1=Push；3=通用 MIDI |
| `0x04` | 原 Push 四字节 USB-MIDI 事件，背压不变 |
| `0x54` | 通用合成器事件 `[17:14]=kind,[13:7]=a,[6:0]=b`，FIFO 满则等待 |

通用模式下，Push 灯光/显示状态机保持复位。DATA0/1 去重、NAK 空闲判定和连续 50 ms 无回复后的断开逻辑复用原实现。断开仍通过原 Push mapper 的连接下降沿排入 CC120 PANIC，清理声部、延音和效果尾音；这是已有的全局松音语义，不是按输入来源逐音清理。

本版读取现有 Host 选中的第 0 个配置，选择第一个合格的 MIDI IN；配置描述符上限 2048 字节。支持 FS Bulk 包长 8/16/32/64；越界、截断、非四字节对齐的事件包、HID/AudioStreaming/MIDI 2.0、只有 OUT 的接口均不交给合成器。

## 证据

候选构建：`results/build_20260917_022113_094799`。保留了进入本轮时的 P27 未提交更改；不是另行回退到 P26。`LATEST_BUILD.txt`、`BOARD_CURRENT*.json`、`READY.json` 均未由本轮改写。可用新增的 `--no-update-latest` 构建选项隔离其他会话的发布指针。

- 固件交叉编译：text 13429、data 7、bss 4224 字节，使用原 64 KiB 内存布局。
- `generic_midi_022642_294282/verification.json`：生产固件在 ASan/UBSan 下测试通过；G1 的 101 字节配置、两种 Push PID、动态端点/包长/alternate setting、拒绝畸形描述符、128×128 音高/力度、16 channel、cable、重复包/短包/NAK/断开均覆盖。通用模式 OUT 调用数为零。
- 同组 RTL：生产 C 生成事件向量 → 实际 MMIO/跨时钟 FIFO → 合成器与 PCM。240 条有序事件，12772 个背压周期；覆盖 0/24/100/127 音高、原始力度、正常/零力度松开、延音断开、重连；Push 初始化、力度 2→30 和压力 3→31 保持。
- `cpu_audio_sim_022643_481116/verification.json`：Vex CPU → 原 Push MMIO → 合成器回归，3817 帧 PCM、3430 帧非零；A/B/C、五音色、效果、表达、路由和松音通过，48 kHz 节拍不变，音频错误为零。
- `p27_controls_022624_433493/verification.json`：现有 P27 Push 按键、灯光、曲谱/录音服务、音频控制测试通过。
- `p26_latency_022758_390202/verification.json`：Push 屏幕字节顺序、XOR、填充、重传和背压通过，正常装包仍为 769 周期。Push MMIO 到数字 DAC 观测点为 104.784～124.784 µs（不包含 USB 轮询/物理按垫延迟）；电脑 UART 和 DIN MIDI 路径也完成回归。
- 旧 Push 固件测试保留完整帧、保活、旧帧重启、NAK 重装、ACK-only toggle 和热插拔检查；只补了会禁止 Push 误入通用描述符分支的测试桩。

首次新 RTL 测试在暂停消费后连续写 70 条事件，测试自身堵在 FIFO 满处；改为填充 64 条后断开并恢复消费，复测通过。失败日志保留，不计为通过证据。

完整综合、布局布线与位流生成成功，构建输入哈希未变。setup/hold 违例 0/0，最差 setup 裕量 +0.017 ns；Logic 34897、Register 25638、BSRAM 253/340、DSP 43.5/298。UserCode `0x00006DE8`；位流 SHA-256 `5ae02d9fac533df10f5921272b8243304acb7011d6bacd4877b6bbeb9dbf961f`。绑定见 [候选记录](GENERIC_MIDI_CANDIDATE.json)。

完整路由审计**未通过**：仍停在既有的 `u_managed/effect_mask_sync_{0,1,2}_s0/RESET` 三个未覆盖的复位例外端点，与本轮开始前的 `build_20260917_021137_154460/usb_a_audit.json` 相同。未修改审计器或放宽约束以跳过它，因此审计器后续检查没有执行；不将“时序通过”表述为“全部路由审计通过”。

当前板上仍运行其他会话选择的版本，本候选尚未实机验收。

## 复现

在 `push2_workstation` 目录执行：

```sh
python3 usb_a/build.py --no-update-latest
python3 usb_a/sim/run_generic_midi.py <新构建目录>
python3 usb_a/sim/run.py <新构建目录>
python3 usb_a/sim/p27/run.py <新构建目录>
python3 usb_a/sim/p26/run.py <新构建目录>
python3 usb_a/audit.py <新构建目录>
```

后续实机检查：G1/普通 MIDI 键盘 → 全音域及力度/松键/拔出；再接 Push → 音符、压力、屏幕、灯光和面板控制。USB 线与板子本轮保持原状。
