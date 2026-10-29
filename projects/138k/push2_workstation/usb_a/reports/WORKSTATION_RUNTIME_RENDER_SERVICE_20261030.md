# Native event/render service 两率事务，2026-10-30

本阶段将已独立验证的 native engines 与完整 native effects 接入现有 event/render service。完整分支需同时显式开启 `RUNTIME_RATE_ENABLE=1` 和 `RUNTIME_EFFECTS_ENABLE=1`；两者默认均为 0。没有选择新的 top/profile、修改 locks、冻结/vendor 输入或公共 18 位事件；没有综合、P&R、烧录或板级接受。最终完整回归的源码身份、输入 SHA256、命令、warning 和结果在 [runtime_render_service.json](workstation_task_20261030/runtime_render_service.json)。此前阶段报告保持其当时的验证范围。

## 改动与事务合同

- `gw138k_event_workstation.sv` 保持 session/parameters/队列 owner，增加完整 engine+effects 配置屏障。广播边沿阻止事件碰撞，等待真实静止后同时接受 engine 与 effects 配置；等待有序 DDR fence 期间恢复原 loader/mix/vector 背压，使 NoteOff/PANIC/lifecycle 能处理。一个已登记 pending render 在全部 ACK 前不启动。
- engine rate、三个 effects rate 和完整 effects ACK 必须匹配目标，才更新公共 `applied_rate_44100_o`。Delay 的 rate/transaction 投影仍是私有部分状态，不能当作全局 epoch 或成功 commit。PANIC 不能撤销已经广播的配置；失败必须 sticky closed，公共 reset 协调恢复。
- `workstation_audio_render_service.sv` 继续只有一个请求槽，保存接受时的 rate、立体声 PCM、取消 epoch 和 intentional-mute 身份。不同 rate 的请求自动使用同一事务；外部 config/history 仅在空槽与实际排空时接受。新 external API 为 `config_valid/config_rate/config_ready/config_applied`、`history_clear/history_ready/history_done`、`quiescent/fault/applied_rate`，并透传 DMA peer heartbeat/fault。
- 旧自主 history done 与新 external config 同拍时不能充当新 ACK，服务也检查真实配置 busy，防止过早释放槽。故障使 ready 保持低；未完成请求只收到一次 zero/error，迟到 fence 不能恢复。
- native 分支在接受时已经 PANIC muted 的新 slot 是确定静音，等待真实 core 完成后返回 good zero；期间 NoteOn 不改变该 slot 身份。接受后新的 PANIC/epoch 改变仍取消为 zero/error。`workstation_frame_delivery.REQUEST_EPOCH_SNAPSHOT` 默认关闭；native 开启后，接收新 slot 当拍建立当前 epoch 基准，不能消费旧 slot 遗留的 epoch 脉冲。legacy muted/error 行为保留。
- 取消响应不等于排空。一个已响应请求仍保留到真实 engine/effects/config 空闲，旧结果不会借新 slot 返回。串行 schedule、最终 PCM owner、桥和 clock-switch 的 ACK 仍属于各自边界。

旧 effects 实例迁入 `legacy_effects.effects`，相应现有 TB 的四组层级访问已更新；native 位于 `runtime_effects.effects`。旧 engine 层级没有变动。

## 最终完整回归

复现入口（output 必须不存在）：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_runtime_render_service.py \
  --project <实际 prepared Prj1> --output <新目录>
```

本次 prepared 项目来自任务的 clean rev2 candidate，完整输入哈希记录在机器证据。legacy oscillator/vector/control/存储依赖从该项目读取，native engine/effects/service 与 FIFO 从版本源读取。生产 Delay 保持 14 位环、9600/8820 帧，对应两率各 200 ms。DMA/FIFO 都是真实 RTL。memory 模型精确提取已提交 effects TB 的前置模块，先接受命令、再执行 posted write，fence 在有序读 RESPONSE 后才返回；它不代替 DDR 电气或仲裁带宽验证。

最终 v5 结果：

| 指标 | 结果 |
|---|---:|
| 接受请求 / 响应 | 48,652 / 48,652 |
| 独立整数 effects PCM 对照 | 48,644 帧，两率各 24,322 |
| 完整配置 ACK / history done | 16 / 25 |
| 取消响应 | 4，均为 zero/error 且不重复 |
| 实际 posted DDR 写 / 有序 fence 返回 | 12,160 / 27 |
| 实际 oscillator physical-Hz 半相位 LSB 约束检查 | 49,780,416 个 slot |

两率都先热身 12,000 帧，再检查六种效果顺序 × 八种 mask 的真实湿声/maintenance；每个输出与独立整数 Delay/Chorus/FDN 模型一致。另覆盖 A/B/C 各 32 声部、vector 八声部的正反切换和 held state，接受后刻意改变外部 PCM，检验当前帧仍使用接受时的立体声身份。

控制边界覆盖：首次 render 自动配置、显式双向配置和 history、真 fence 挂起时的 NoteOff、配置期间的 PANIC/lifecycle、忙时额外 config/history 拒绝、intentional mute 后 NoteOn、muted slot 再次 PANIC、旧自主 history done 撞新 config、缺失/迟到 fence、sticky failure、计算/memory/DMA 协调 reset。全部输入在运行期间保持一致。

延迟从 request offer 后到 service done 统计，单位为计算时钟；不包含外层 router/CDC/serializer：

| 情况 | 最大周期 | 触发范围 |
|---|---:|---|
| 已配置且无既有 loader 的 render | 1146 | 两率正常顺序/mask、A/B/C/vector |
| 接受时已有 NoteOn loader | 1182 | 保留原 loader 背压后启动 |
| 首次自动切到 44.1 kHz | 1598 | 配置广播、真实有序 fence、全部 ACK 后再 render |

1598 不能当作 steady render 预算，也不能据此宣称整个 1600 周期 serial deadline 已闭合。完整 clock/bridge/最终 PCM 联合预算由独立组合回归记录。

## 默认来源回归与局限

完整 1600-phase sweep 在最终 native mute/ACK/epoch 小补丁之前通过，且输入稳定：默认请求/响应 59,378/59,378，native-engines+legacy-effects 59,360/59,360；每种各覆盖 CC PANIC 6400、lifecycle 6400、loader 205，以及五音色、A/B/C/vector、八 mask/六顺序、真实 wet/FDN 与 4096 事件压力。最大正常延迟均 1183 周期。

最终源对上述两种编译又运行 `--phases 1`：默认 8170/8170、native-engines 8152/8152，逐周期 prepared 等价、960 normal case、4096 warm frames、205 loader 取消与 4096 事件压力均通过，输入稳定。该最终运行没有重做 1600-phase 全扫描；最终补丁在完整 native 参数分支和新默认关闭的 delivery 参数内，旧默认行为仍由最后一轮逐周期对照约束。

另用 Icarus 运行新 `tb_workstation_request_epoch_delivery.sv` 的旧 epoch/接收碰撞、后续 PANIC、late result、连续接受和 epoch wrap；原默认 `tb_workstation_frame_delivery.sv` 的 4119-cycle/4096 随机用例也通过，141 次预期 duplicate fault 没有被隐藏。`sim/test_current_workstation_sources.py` 10 项通过。

最终完整编译无 `UNOPTFLAT`；保留的 warning 是 prepared 未使用模块端口、TB 未观察输出和既有算术宽度等，具体计数在 JSON，没有用抑制 ready 组合环的方式放行。本阶段没有宣称 top/profile 已选择这条路径，没有实际 DAC/模拟音频、CDC/PLL/route timing、资源、SRAM 或 Flash 接受。

父级以独立输出目录 `runtime-render-service-parent-final-v5` 复跑最终完整回归，48,652 请求、48,644 独立模型对照及三类最大延迟均复现；56 项输入哈希结束后再次复核一致，来源回归 10 项通过。机器记录保存该独立验证文件身份。
