# USB2 输入 owner 的音频域复位

`workstation_usb2_input.AUDIO_OWNER_RESET_SYNC` 默认是 `0`，保留原有直接音频复位连接。运行时原生顶层在自己的参数分支显式设置 `1`；wrapper 是独立编译单元，不依赖顶层 provider 的宏泄漏。accepted、pinned、未启用 runtime 的新板路径不选择该参数，不改三份锁定源码基线。

启用时，`reset_n && audio_reset_n` 只是平台复位请求。wrapper 的 `audio_owner_reset.release_q` 在该请求撤销资格时异步清零，在 `clk_audio` 三个真实上升沿后释放；只有末级驱动 `owner_audio_reset_n`。音频停高或停低时都能断言，停钟期间不能释放。这个局部信号同时交给 owner 的 `audio_reset_n` 以及音频反馈域的 `feedback_reset_n`，不修改 CPU、DDR、公共参数或 stream epoch 的复位所有权。

顶层仍把 `runtime_reset_n = reset_n && memory_guard_started` 交给 wrapper。计算 PLL 暂时丢失资格或计算时钟暂停不会自行撤销这个请求，不能重造 attach 或重新应用接入默认值；平台复位请求本身仍有权复位输入 owner。`FEEDBACK_AUDIO_DOMAIN=0` 继续使用原来由 `clk_ref` 释放的反馈复位。

## owner 下游清单

这里同时追查了 `push2_usb_a_control` 的全部异步敏感块及两个跨域组件，不只处理反馈计数器。

| 接收状态／边界 | 异步断言来源 | 释放与归属 |
|---|---|---|
| `feedback_divider` | `feedback_reset_n` | 音频反馈配置使用新 wrapper 音频域末级；默认仍保留原选择 |
| `feedback` 保持字 CDC | `reset_n && feedback_reset_n` | CDC 自有三拍 source／destination release；负载、toggle 和有效位使用各自局部末级 |
| USB 域七个状态块 | wrapper 的 `cpu_reset_n` | 原有 `cpu_release_q` 两个 USB 边沿；显示快照、settled／warmup、可选 CNN 状态／刷新计数、映射计数、PANIC 与连接／MMIO 状态不改 |
| `event_release` | `event_qualified = reset_n && audio_reset_n` | owner 自有三拍 USB release；`rst` 撤销 MIDI mapper 与队列资格；新的音频参数经 wrapper 局部末级进入 |
| `audio_release` | 同一 `event_qualified` | owner 自有两拍音频 release，末级生成 `audio_local_reset_n` |
| `online_sync` | `audio_local_reset_n && connected` | 断开异步清零、两个真实音频边沿重新确认；保留短断开取消语义 |
| `panic_sync`／`defaults_sync`、`audio_online`／`panic_seen`／`settle_wait` | `audio_local_reset_n` | 继续由 owner 音频域末级释放；PANIC toggle 与生命周期优先级不变 |
| `queue_release` | `input_reset = rst || !connected || panic_flush` | 原有六个真实音频边沿；停钟不能提前确认 |
| `drain_release` | `queue_fifo_reset = input_reset || !queue_release[5]` | `STOP_CLOCK_QUEUE_FENCE=1` 再等六个音频边沿排空；正常事件继续隔离，生命周期取消独立 |
| `queue_write_release` | `input_reset` | 原有两个 USB 边沿观察 `queue_read_ready`，不把音频排空确认当即时 USB 写资格 |
| 锁定生成事件 FIFO | `queue_fifo_reset` | 原有 USB 写指针异步复位、音频 read reset 两拍同步以及未带独立 reset 的读输出 buffer；wrapper 不改生成字节，继续通过真实读口排空 |

该清单不是完整 reset 接受。FIFO 写侧复位撤销仍涉及音频到 USB 的物理边界，断开／PANIC 的组合断言、平台原始请求到各同步器的 flight／脉宽、所有级间及末级到功能 CLEAR 的 recovery／removal、实际综合结构和布局布线仍须独立检查。新增三拍 release 不添加 false path、宽域 cut、降频或门限放宽，也不声明 FC 的 recovery 问题已物理关闭。

## 离线回归

```sh
python3 projects/138k/push2_workstation/usb_a/sim/usb2/run_workstation_usb2_owner_reset.py \
  --output /absolute/new/usb2-owner-reset-evidence
```

回归使用实际 wrapper、MMIO service adapter、输入 owner、锁定保持字 CDC、生成事件 FIFO 和 `workstation_session`。只替换 USB CPU／ULPI 上游为可控 MMIO 生产者，并模型化持音和音量应用，不运行生产 CPU 固件，不验证 USB 枚举、DSP、串行音频或硬件。

三个音频相位各同时执行默认参数与显式启用配置：四次短／停高／停低复位检查、五次释放、两个接入各 13 个默认事件、一次断开、一次 PANIC、三个停钟队列场景及两个保留事件的顺序。顶层预处理检查 runtime 显式启用、默认分支不启用。六个负控分别绕过局部复位、导出首级、改用参考时钟、取消异步断言、绕过 owner 音频复位与绕过反馈复位，均必须被真实仿真拒绝。

原 `run_workstation_usb_runtime_reset.py` 继续验证计算 PLL 资格短脉冲与停钟恢复不会重建 USB 接入；其旧 PLL 复位连接负控仍须复现额外接入。该测试的 owner 是直接实例化，新的 wrapper 回归另行覆盖本次释放边界。全部结果都保持 `full_reset_accepted=false`，综合、物理时序和板上接受尚未完成。
