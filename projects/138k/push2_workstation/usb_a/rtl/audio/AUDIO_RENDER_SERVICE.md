# 请求驱动的合成／矢量 render service

`workstation_audio_render_service.sv` 是常开计算域的单请求服务。它包装原 `gw138k_event_workstation`、真实 oscillator／vector／effects 和 `workstation_frame_delivery`，仅显式选择 `TIMING_OPTIMIZED=1`、`EXTERNAL_MASTER_VOLUME=1`、`REQUEST_DRIVEN_RENDER=1` 与 48 kHz。没有自由运行的 1600 周期发生器。

这不是最终音源选择或最终 PCM owner。返回为既有合成／矢量效果链及左右 route 后的 Q1.31 立体声；TF 选择、一次最终 CC7 主音量、PCM16 量化和完成帧 tap 由后续原 owner 接入。已有 `master_volume_o` 直接透传唯一 `workstation_parameters` 的状态，不另存公共参数或增加 TF 选择器。外部 PCM 混入仍走原 effects 输入，按接受时的完整立体声对保持。

## 请求和完成

所有端口属于 `clk_i`，delay-memory 端口保持原有独立时钟契约。`rst_ni` 是计算域公共复位；禁止接串行器局部复位或采样率切换复位。

- `render_ready_o` 表示服务的唯一请求槽可接受。`render_request_i && render_ready_o` 每次接受一笔；忙时的额外 request 只增加饱和拒绝计数，不覆盖当前请求。
- 接受 48 kHz 请求的当拍只产生一次 `sample_ce_o`，直接登记原工作站的 `pending`。已有 pending 阻止后续业务 dispatch，并等待已开始的 Note On load／当前 ready 条件完成，保留原来的采样优先权。
- `render_done_o` 是单周期响应，伴随 `render_left_o`、`render_right_o` 和 `render_error_o`。服务不保存或重写 rate／epoch／sequence；调用它的帧桥必须继续保留原请求身份至完成。
- PANIC／生命周期取消复用 frame delivery 的显式零响应；一笔请求最多响应一次。默认 legacy 的 PANIC muted 请求也按原语义返回 zero/error。返回零后 `render_busy_o` 仍保持，只有响应已经交付且 `render_idle_o` 为真才释放请求槽。迟到结果不能启动第二次响应或套给下一个请求。
- 默认 `RUNTIME_EFFECTS_ENABLE=0` 时，`render_44k1_i=1` 只返回一次显式零／error 并计数，不发 `sample_ce_o`，不推进 48 kHz DSP。完整两率分支需同时显式启用 `RUNTIME_RATE_ENABLE=1` 与 `RUNTIME_EFFECTS_ENABLE=1`。
- `rejected_request_count_o`、`unsupported_rate_count_o`、`cancelled_response_count_o`、`drained_result_count_o` 是公共复位清零的饱和计数。最后一项表示已响应之后仍完成的内部结果被排空，不把它再次交付。

## 取消后的真实排空

旧引擎 PANIC 先清除 `frame_inflight`／mix busy 和 joined/effect 状态，但部分独立 ROM valid 流水只接公共复位。不能把 `frame_inflight=0` 当作旧 render 已结束。

| 取消边沿之后仍可能存在的旧工作 | 保守边沿预算 |
|---|---|
| slot read 在 PANIC 边沿被 sine 接受；sine 的 s0／s1／s2／s3／out | 5 |
| gain product、envelope product、finalize | 3 |
| quantizer magnitude-low／magnitude／scale-low／scaled／rounded／out | 6 |
| 独立 partial generator 恰在 PANIC 边沿启动；最多 32 次 issue，read／product／output valid，随后 timbre ROM valid | 32 + 3 + 1，加接收／清空边沿余量 |
| vector 与 effects FSM | PANIC／clear 当拍清 state／valid；RAM、DDR FIFO／flush 工作不构成自主 render 完成 |

`LEGACY_CANCEL_TAIL_CYCLES=40` 是这些固定旧流水的取消尾窗，不是正常渲染延时或一般超时。它只在 PANIC／生命周期边沿装载。`render_idle_o` 同时要求 pending／frame-inflight／joined 清空、load／mix 空闲、vector／effects ready 和所有公开 render valid 为空。正常 envelope／quantizer 尾部一直受 frame-inflight 覆盖到 effects 完成。

`REQUEST_DRIVEN_RENDER` 默认 0。只有显式 service 分支在 core-ce 上检查该尾窗；默认事件调度、参数提交、PCM 与 accepted 配置不消费它。不能将组合 `core_sample_ready` 或 `panic_accept` 反馈成服务 ready：这些谓词通过事件 dispatch 依赖本拍 sample-ce，会形成组合环。

`RUNTIME_RATE_ENABLE` 默认 0。显式设为 1 时，event/service 通过 `workstation_runtime_render_engines` 组合原生 pitch／oscillator／vector，render admission 以三者真实 `quiescent_o` 替换 legacy 尾窗；默认分支仍保留上述 40 周期策略。组合模块自身可在真空闲时原子提交 48／44.1 kHz，振荡器的 committed rate 是三者唯一采样率依据，不增加公共参数副本。

仅启用 `RUNTIME_RATE_ENABLE=1` 时，event 的完整旧效果链仍只承认 48 kHz，service 保留显式 44.1 零／error。启用完整两率分支后，旧效果实例位于 `legacy_effects.effects`，原生实例位于 `runtime_effects.effects`；这不修改 profile、冻结或 vendor 来源。

## 完整两率配置事务

`RUNTIME_EFFECTS_ENABLE=1` 要求原生 engine 同时启用，且 Delay 保持生产分配：14 位环、9600／8820 帧，对应两率各 200 ms。完整分支复用同一 session、parameters 和事件队列；没有把 rate／epoch 塞入 18 位事件。

- `config_valid_i && config_ready_o` 接受显式配置，`config_rate_44100_i` 表示目标 rate；valid 必须独立于 ready，并保持目标到接受。`history_clear_i && history_ready_o` 只清历史，保留已提交 rate。它们仅在 render 槽空闲、实际 engine／effects 排空时接受；config 优先于 history。
- 接受一个与当前 rate 不同的 render 请求，也会自动发起相同配置事务。唯一请求槽立即保留接受时的 rate 与立体声 PCM，event 的 pending 等待全部 ACK 后才启动。外部 PCM 后续变化不能重写这一帧。
- 配置广播边沿暂缓业务 dispatch，确保 engine 在无事件碰撞的边沿提交；实际 DDR fence 等待期间恢复原 loader／mix／vector 背压，NoteOff、PANIC 和 USB lifecycle 不会被 pending 请求长期挡住。PANIC 继续使用原 session／delivery 取消语义；已经广播的配置必须完成或 sticky fail。
- `applied_rate_44100_o` 只有在 engine rate、三个效果 rate 和完整效果配置 ACK 一致后才变化；同拍产生 `config_applied_o` 与 `history_done_o`。Delay 私有 transaction 仅是 history/fence 关联号，不对外充当 epoch。自动 render 配置也会产生这些完成脉冲。
- 完整 native 分支对接受时已处于 PANIC mute 的新请求保存确定静音身份，等待真实 core 完成后返回 good zero；期间 NoteOn 恢复声音也不改该帧身份。接受之后再次 PANIC／epoch 改变才返回 zero/error，响应后仍等待真实 drain。`workstation_frame_delivery.REQUEST_EPOCH_SNAPSHOT` 默认关闭；完整分支开启后，接受新 slot 当拍只建立当前取消基准，旧 slot 遗留的 epoch 观察脉冲不能消费新身份。
- `history_done_o` 也反映显式历史清理和 PANIC 历史清理完成；旧自主 clear 的完成与新配置接受同拍时，不投递成新事务 ACK。调用者必须按自己已接受的事务关联完成。`quiescent_o` 同时要求请求槽、配置和实际尾部全部排空，不能用零响应或 config ACK 代替它。
- Delay 的 FIFO／DMA fence ACK 等待旧 read 排空，并在同一有序 owner 路径读回最后接受的写地址后返回。连接 `delay_peer_heartbeat_i` 为 DMA heartbeat，DMA peer heartbeat 为 `delay_heartbeat_o`，`delay_dma_fault_i` 为 DMA fault。两个时钟停一个由存活域检测；两者同时停仍需外部常开监控。
- history／配置和 peer 超时采用 native chain 的默认 1,048,576 个计算周期。错误、rate 不一致或 DMA/stream 故障使 `fault_o` 保持，禁止 ready；未响应 render 只返回一次 zero/error。恢复要求计算和 memory/DMA 公共协调复位。串行输出域继续按原采样计划输出受控零，不得停采样调度。

完整配置仅负责 DSP 配置与历史，不负责 epoch、clock/PLL、桥、最终 PCM owner 或 serializer 的启停。它们的独立握手仍由外层组合负责。

## 验证入口与范围

```sh
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_render_service.py \
  --project <实际 prepared Prj1> --output <不存在的新目录>
```

增加 `--runtime-engines` 可显式校验原生引擎分支的同一 48 kHz 全效果链；不改变 prepared profile。未加该选项的编译不增加 native engine 源，继续验证默认来源隔离。

测试编译实际 prepared 的 oscillator、vector、effects、存储原语和控制依赖，将未改的 prepared event 模块只做唯一模块名替换，以便和原生 service 并行。第三个 current-default event 实例在整个运行中逐拍对照旧源，保护 `REQUEST_DRIVEN_RENDER=0` 的旧行为。正常 service 对照覆盖 A／B／C 各 32 声部、vector 八声部、五音色、八种效果 mask、六种顺序，以及填满 chorus／reverb FDN 后的真实湿声。取消扫描把默认分支等价与 opt-in 分支的隔离合同分别检查，不要求新取消调度复制旧的不安全尾部。

测试将 `ECHO_SAMPLES` 明确设为 32，以在每个短用例中验证真实 delay FIFO、湿声和反馈；生产默认仍为 9600。其 memory-side history／flush marker 模型没有证明实际 DDR ready、带宽或尾延迟。正常固定 1600 周期只存在于对照激励，不能因此宣称两颗实体参考无频差、桥 CDC／最终处理已经满足预算或 44.1 kHz 已实现。

完整原生两率回归另用生产长度 Delay 和真正的 native DMA/FIFO：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_runtime_render_service.py \
  --project <实际 prepared Prj1> --output <不存在的新目录>
```

其有序 memory 模型先接受命令、随后执行 posted write，并延迟 fence read RESPONSE；与独立整数 effects 模型逐帧比较两率湿声。覆盖六种顺序、八种 mask、自动／显式正反切换、held 音符、A/B/C 和 vector、接受 PCM 身份、NoteOff/PANIC/lifecycle、额外配置背压、迟到 fence、sticky failure 和协调复位。它不模拟 DDR 电气时序。

机器证据和阶段结论见 `reports/WORKSTATION_RUNTIME_RENDER_SERVICE_20261030.md`；综合、P&R、CDC／PLL、DAC、SRAM 及整机硬件验收均不由此离线回归推导。
