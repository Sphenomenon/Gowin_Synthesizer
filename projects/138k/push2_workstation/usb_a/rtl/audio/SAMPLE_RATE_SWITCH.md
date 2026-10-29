# 双采样率切换事务核心（A06 独立实现）

`workstation_sample_rate_switch.sv` 只实现常开 50 MHz 域的有界切换事务，尚未接入当前整机 top、FPC serializer、DSP 或构建 profile。局部仿真通过不构成 A06 整项完成，也不是时序／CDC／实板验收。

## 时钟来源与器件依据

已有 [测频记录](../../../../example/AK4493_AMP/clock_measure/README.md) 保存 K18 标称 12.288 MHz、J19 标称 16.9344 MHz 的六个连续 10 秒相对测量窗口。以未外部校准的 50 MHz 参考折算，两路分别约 12,287,945.73333 Hz、16,934,270.15000 Hz；不是绝对频标或抖动测量。

| 目标模式 | MCLK | MCLK／LRCK | BCK | MCLK／BCK | 每声道 slot |
|---|---:|---:|---:|---:|---:|
| 48 kHz | K18，12.288 MHz | 256 | 3.072 MHz | 4 | 32 bit |
| 44.1 kHz | J19，16.9344 MHz | 384 | 2.8224 MHz | 6 | 32 bit |

44.1 kHz 的 BCK 可用每 3 个 MCLK 边沿翻转的整数除 6，实现精确 50% 占空比；每 32 个完整 BCK 翻转 LRCK，数据按标准 I2S 的一 bit 延迟发送。当前 FPC 的 8-bit 相位计数／除 4 BCK／256fs 不能直接复用为 384fs。此表是可实现的数字时序方案；仍须用实装 AK4493S 正式手册核对引脚控制、ACKS、384fs 自动识别、PDN／SMUTE 及变频时序，不能仅用旧 AK4493 文档代替。

器件依据为 Gowin **UG306-1.0.6E Arora V Clock User Guide**，正文 12–15 页（PDF 21–24 页）：GW5A `DCS` 端口为 `CLKIN0..3`、onehot `CLKSEL[3:0]`、`SELFORCE`、`CLKOUT`。装配要求 `DCS_MODE="FALLING"`、`SELFORCE=0`，未用端输入接 0；`clock_select_o[0]` 选 48 kHz 参考，bit 1 选 44.1 kHz 参考。原语在选中源下降沿撤销门控，切换允许拉长低电平，不截短正常源脉冲。不能把旧系列 UG286 的 `CLK0` 示例端口套到 GW5A。

该手册正文 8 页（PDF 17 页）给出 138K PLL 输入 19–800 MHz；两路音频参考均低于此范围，不能未经器件支持证明直接用它们生成计算 PLL。后续可保留 50 MHz 派生的 76.8 MHz 常开计算域，由选中的 DAC 完整帧请求约束 render 节拍；48 kHz 约 1600、44.1 kHz 约 1741／1742 个计算周期，预算还须扣除 CDC、排队和交付开销并计入实际频差。请求／有界 FIFO 用于跨域和流水线，不吸收永久频差。

## 接口契约

除 `rst_ni` 异步断言外，所有输入均由装配方在常开 `clk_i` 域原子同步后提供。不得把音频时钟域的裸总线／脉冲直接连到此核心。

| 接口 | 所属及语义 |
|---|---|
| `request_i`, `request_44k1_i` | 单周期请求 strobe。仅 `request_ready_o=1` 时可接受；忙时每个 strobe 显式拒绝，不排队、不覆盖当前目标。此处没有 MIDI CC、UI 或 TF／录音忙时产品策略。 |
| `accepted_o`, `applied_o`, `rejected_o`, `failed_o` | 50 MHz 单周期结果。接受和应用分开；同模式有效请求是 no-op，接受／应用同周期，不增加 epoch。启动成功不算命令应用；显式恢复成功有应用脉冲。 |
| `source_qualified_i[1:0]` | 板级常开监测器分别证明两个原始参考有效，需包含频率／稳定窗口，不能只判断电平变化。目标在请求前不合格则拒绝。 |
| `quiesce_o`, `frame_quiescent_i` | serializer 在完整左右声道帧结束后静音并停止接受旧代次，所有交付端排空／作废后再应答。QUIESCE 中核心保留旧时钟和局部复位释放；装配方不应直接把请求当作立即截断 BCK 的信号。 |
| `clock_select_o[3:0]` | 仅 onehot／全 0，交给硬件 DCS。先撤选，等待真实输出停低，再选目标。核心不产生组合时钟 mux。 |
| `clock_monitor_restart_o` | 单个状态周期，通知常开输出监测器重新计数。撤选后和目标选择后分别重新测量，不能复用旧源的有效状态。 |
| `selected_clock_stopped_low_i` | 常开监测器在 restart 后证明 DCS 输出低且连续无边沿达规定窗口。单次采样为低不够。 |
| `selected_clock_qualified_i` | 常开监测器在目标选择后证明 DCS 输出有足够数量的有效边沿／周期，并在丢钟后撤销资格；此状态不得由已停止的输出域生成。 |
| `audio_reset_no`, `stream_flush_o`, `dac_mute_o` | 音频交付／serializer 专用局部控制，禁止连到全局复位、USB、DDR、CPU 或公共参数状态复位。复位在各接收域异步断言、同步释放；flush 必须清除所有旧代次 mailbox／FIFO／在途样本。正常切换的直接静音／局部复位只在完整帧应答后断言；故障进入立即隔离。 |
| `staged_44k1_o`, `staged_epoch_o` | 当前事务的目标配置。装配方在局部复位中装载 DSP／serializer 配置；新流预填充必须携带该代次。staged 不代表对外已经应用。 |
| `prefill_ready_i` | 所有目标域已释放局部复位、使用 staged 配置且预填充到约定水位，第一帧可完整输出。此应答只进入 RESUME／解除 mute 请求，不能用一个固定延时替代真实跨域应答。 |
| `output_running_i` | serializer 对本次请求在完整帧边界解除静音，已输出 staged 模式／代次的第一完整帧后应答。装配方须在每次 quiesce／flush 清除旧应答，不能常接 1 或复用前次状态。直接静音输出必须在 serializer 域按完整帧边界安全释放。 |
| `active_44k1_o`, `stream_epoch_o`, `active_valid_o` | 对外实际应用身份：目标资格、预填充和真实输出恢复应答完成后同周期提交；停止旧流后 active_valid 清 0，旧 rate／epoch 留作最后提交身份。RESUME 阶段首帧使用 staged 身份，消费者不得误标为旧 active 身份。epoch 为 32-bit 模计数，启动为 0，成功切换／恢复加 1；失败不发布 staged epoch。 |
| `recover_i` | 仅故障态有效，重试最后已提交的采样率；需其原始参考合格，先再次确认 DCS 全撤选输出停低。无自动尝试、无隐式整机复位。 |

正常事务：接受 → 请求完整帧静音／交付清理 → 撤选并确认停低 → 选目标／重新资格 → 释放局部复位并预填充 → 按完整帧解除静音／确认目标帧输出 → 原子提交实际模式及代次。`TIMEOUT_CYCLES` 是每个等待阶段的上限，默认每阶段 1,000,000 个 50 MHz 周期（20 ms），不是整次事务总时长；整次上限由各阶段上限和固定过渡周期求和，实际静音时长由整机诊断测量。

拒绝码：0 无，1 busy，2 目标／当前参考未合格，3 已处于故障。故障码：0 无，1 完整帧应答超时，2 DCS 撤选停低超时，3 目标输出资格超时，4 切换／预填充／恢复输出阶段目标丢钟，5 预填充超时，6 稳态运行资格丢失，7 恢复完整输出应答超时。故障码保留至恢复成功；事件脉冲不作累积计数，装配方可按统一诊断契约计数。

## 失钟限制

官方 DCS 模型显示：若旧源停在高电平，其已置位门控无法在下降沿撤销。控制器必须超时、保持 `SEL=0`、DAC 静音／局部复位和 stream flush，不能把 `SELFORCE=1` 当作无毛刺恢复。旧源恢复后可显式 `recover_i` 重试；源永久停高时安全恢复需要器件厂家明确支持的隔离／时钟树重启办法，当前核心保持故障终态。外部源任意时刻物理停振本身可能截短已有周期，故障隔离不冒充“外部失钟仍有完整脉冲”。

## 校验与后续接入

```sh
PATH=/opt/homebrew/bin:$PATH python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_sample_rate_switch.py
```

测试直接编译官方 `gw5a/prim_sim.v` 的 DCS，输出该文件 SHA256。默认使用本机 GowinIDE 路径；其他机器设置 `GOWIN_GW5A_SIMLIB`。缺少官方模型明确失败，不用组合 mux stub 冒充验证。TB 覆盖两向完整事务、正常时钟脉宽、预填充／真实输出应答前不提交、同模式 no-op、连续 busy 请求、目标未就绪／中途失钟、DCS 旧源停高与失败重试、资格／预填充／完整帧／输出恢复超时、启动失败及显式恢复；QUIESCE 中已选源失钟立即隔离，未选目标失钟等待健康旧帧完成。TB 的参考／输出资格监测用于机制验证，尚不是生产频率监测器。

剩余工作：生产原始参考／DCS 输出监测器及 routed DCS 布线；384fs I2S；输出时基驱动的逐帧请求／tagged PCM 与 deadline；48／44.1 的 DDS、包络、LFO、效果、FFT 系数及历史切换；PANIC／Note Off／持音跨切换队列和任务策略；最终 PCM 统一 tap；板级电气、AK4493S 手册、两模式和切换路径的 SDC／CDC／PLL／pulse-width／P&R；SRAM 实测与外部时钟／DAC 检查。当前核心不决定录音／TF 忙时操作规则，不扩大 18-bit MIDI 或旧 BLE／显示格式能力。
