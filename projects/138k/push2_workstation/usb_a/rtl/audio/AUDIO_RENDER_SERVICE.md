# 请求驱动的 48 kHz 合成／矢量 render service

`workstation_audio_render_service.sv` 是常开计算域的单请求服务。它包装原 `gw138k_event_workstation`、真实 oscillator／vector／effects 和 `workstation_frame_delivery`，仅显式选择 `TIMING_OPTIMIZED=1`、`EXTERNAL_MASTER_VOLUME=1`、`REQUEST_DRIVEN_RENDER=1` 与 48 kHz。没有自由运行的 1600 周期发生器。

这不是最终音源选择或最终 PCM owner。返回为既有合成／矢量效果链及左右 route 后的 Q1.31 立体声；TF 选择、一次最终 CC7 主音量、PCM16 量化和完成帧 tap 由后续原 owner 接入。已有 `master_volume_o` 直接透传唯一 `workstation_parameters` 的状态，不另存公共参数或增加 TF 选择器。外部 PCM 混入仍走原 effects 输入，按接受时的完整立体声对保持。

## 请求和完成

所有端口属于 `clk_i`，delay-memory 端口保持原有独立时钟契约。`rst_ni` 是计算域公共复位；禁止接串行器局部复位或采样率切换复位。

- `render_ready_o` 表示服务的唯一请求槽可接受。`render_request_i && render_ready_o` 每次接受一笔；忙时的额外 request 只增加饱和拒绝计数，不覆盖当前请求。
- 接受 48 kHz 请求的当拍只产生一次 `sample_ce_o`，直接登记原工作站的 `pending`。已有 pending 阻止后续业务 dispatch，并等待已开始的 Note On load／当前 ready 条件完成，保留原来的采样优先权。
- `render_done_o` 是单周期响应，伴随 `render_left_o`、`render_right_o` 和 `render_error_o`。服务不保存或重写 rate／epoch／sequence；调用它的帧桥必须继续保留原请求身份至完成。
- PANIC／生命周期取消及 PANIC muted 请求复用原 frame delivery 的显式零响应；一笔请求最多响应一次。返回零后 `render_busy_o` 仍保持，只有响应已经交付且 `render_idle_o` 为真才释放请求槽。迟到结果不能启动第二次响应或套给下一个请求。
- 当前 `render_44k1_i=1` 只返回一次显式零／error 并计数，不发 `sample_ce_o`，不推进 48 kHz DSP。它不是采样率适配实现。
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

退出条件：原生 runtime oscillator 接入其真正覆盖全部 valid 的 `quiescent_o` 后，替换 legacy 尾窗；vector／effects 的切换历史清理和新的整机 profile 必须独立验证。此组件不切换现有 profile，也不改冻结或 vendor 来源。

## 验证入口与范围

```sh
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_render_service.py \
  --project <实际 prepared Prj1> --output <不存在的新目录>
```

测试编译实际 prepared 的 oscillator、vector、effects、存储原语和控制依赖，将未改的 prepared event 模块只做唯一模块名替换，以便和原生 service 并行。第三个 current-default event 实例在整个运行中逐拍对照旧源，保护 `REQUEST_DRIVEN_RENDER=0` 的旧行为。正常 service 对照覆盖 A／B／C 各 32 声部、vector 八声部、五音色、八种效果 mask、六种顺序，以及填满 chorus／reverb FDN 后的真实湿声。取消扫描把默认分支等价与 opt-in 分支的隔离合同分别检查，不要求新取消调度复制旧的不安全尾部。

测试将 `ECHO_SAMPLES` 明确设为 32，以在每个短用例中验证真实 delay FIFO、湿声和反馈；生产默认仍为 9600。其 memory-side history／flush marker 模型没有证明实际 DDR ready、带宽或尾延迟。正常固定 1600 周期只存在于对照激励，不能因此宣称两颗实体参考无频差、桥 CDC／最终处理已经满足预算或 44.1 kHz 已实现。

机器证据和阶段结论见后续 dated report；综合、P&R、CDC／PLL、DAC、SRAM 及整机硬件验收均不由此离线回归推导。
