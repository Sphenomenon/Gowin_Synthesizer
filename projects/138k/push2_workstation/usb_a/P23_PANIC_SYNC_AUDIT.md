# P23 PANIC 同步清理源码审计

P22 的电脑键盘连击实体通过后，下一项只处理 PANIC。此前电脑窗口和 Push 的“全部松音”都发送 CC123；音频核心把它解释为正常 All Notes Off，逐个声部进入 RELEASE，因此包络、延迟、合唱和混响尾音仍继续。全局 `held` 会清零，但 Push mapper 的 `held/last_note/last_velocity/event_valid`、AE350 UI 的本地 `gate`、电脑窗口的重复计时器和物理按键锁存属于各自私有状态，原路径没有统一的清理确认。

## 输入、队列和时钟域

| 来源 | PANIC 前的路径 | 时钟与背压 | P23 行为 |
|---|---|---|---|
| 电脑 Tk 窗口 | `keyboard_midi.py` → `midi_serial.py` → SIPEED 串口输入 → 50 MHz UART RX → 单字节 CDC → 76.8 MHz PC MIDI decoder | 115200 bit/s；decoder 和三源仲裁器保持 `valid/ready`，音频忙时背压 | 窗口按钮发送 CC120，并立即取消重复/松键计时器、清本地 held；仍按串口顺序进入原队列 |
| Push pad/按钮 | J18 USB-A 48 MHz Host → `push2_controls` → 事件 FIFO Gray CDC → 76.8 MHz 三源仲裁 | mapper 只有一个待发事件；FIFO 和音频入口均为 `valid/ready` | CC27/29 和断开恢复路径发送 CC120；本地 held、最后音符/力度清零，世代确认到达时丢弃尚未转发的旧事件 |
| AE350 UI | 100 MHz core / 50 MHz bus → 原 CPU 控制 mailbox → 76.8 MHz 音频仲裁 | 原请求/应答 mailbox；本轮不改队列 | 回传世代变化时清本地 `gate/keyboard`；若触摸仍按下，锁存到真实松手后才允许新触发 |
| G1 MIDI | P16 MIDI RX → 76.8 MHz decoder → 同一三源仲裁 | 原 decoder `valid/ready` | 保留；普通 CC123 仍为渐进 All Notes Off，外部明确 CC120 才执行硬 PANIC |

PANIC 没有旁路原仲裁和 `dispatch` 条件，也没有重写输入架构。它在 CC120 被音频域实际接受的那个周期成为状态边界。已进入各来源队列且位于 CC120 之前的事件仍按序处理；本机触发 PANIC 时，来源先停止产生后续重复事件，因此不会在 CC120 后补发本机连击。Push 世代确认还会丢弃一个尚未转发的旧 mapper 事件。没有把 PANIC 做成无序抢占。

## 硬清理与状态回传

`gw138k_event_workstation.sv` 只在接受 CC120 时清 `held/deferred/sustain/releasing`，递增 10 bit `panic_epoch`，清声部分配与处理流水线有效状态，并清效果器的指针、历史长度、增益和混响反馈状态。效果选择、串联顺序、HDMI/DDR 数据路径和输入 PCM 路由不变。效果 RAM 不逐项复位；长度和指针归零后旧内容不可达，避免破坏原 BSRAM 推断。新的 Note On 才解除合成器 PANIC 静音。

CC123 保留旧的逐音符 RELEASE 扫描，模式切换仍可等待正常尾音结束。这样 PANIC 和音乐意义上的 All Notes Off 不再混用。

`panic_epoch` 放在原先恒零的 `control_pitch[31:22]`，pitch 的低 22 bit Q20 格式未变。它沿现有音频控制快照到 50 MHz 管理域，再进入既有 448 bit performance snapshot，送往 Push 48 MHz 域和 AE350/UI；电脑窗口从 E138 expression 回报读取同一世代。没有新增裸跨时钟信号。

Push 内部回传不依赖电脑串口，因此屏幕、灯光 mapper 和待发事件可以在板内同步清理。电脑窗口收到板端发起的 PANIC 仍依赖 U15 回传；当前短窗口一直没有收到 C350/K138/E138，这一方向的实体同步尚不能据此判定通过。电脑窗口自己发起 PANIC 时会先本地清理，因此不依赖回传才停止连击。

本阶段没有修改 Push pad 按住去重、poly-aftertouch、声部分配策略、键盘长按 300/80 ms 参数、三种模式、效果顺序、HDMI、DDR、耳机或 Push 公开屏幕协议。USB IN error 诊断仍为 `null`。完整 routed audit 继续保留 `u_managed/effect_mask_sync_[0..2]_s0/RESET` 三个旧覆盖缺口。
