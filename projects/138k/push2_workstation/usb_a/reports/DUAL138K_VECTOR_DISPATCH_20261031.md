# M7 矢量事件接收组合路径收敛

日期：2026-10-31。阶段：维护 RTL 修改及离线整条 render service 回归。机器可读来源、基线时序及结果见 [verification.json](dual138k_vector_dispatch_20261031/verification.json)。本修改需要后续整机综合、P&R 及实板验证；这里不预记时序或资源收益。

## 真实基线路径

M7 为 `custom138k-workstation-m-demo-v1-0067ea90a6354485`，物理报告位于 `/Users/sphenicidition/.cache/gw138k-dual-20261031/m-demo-base-v7-physical-v1/impl/pnr/custom_138k_integration.tr`。音频同步最差路径 Path10 为 `runtime_effects.effects/dma_fault_sync` → `u_native_usb/input_owner/settle_wait`，slack −1.885 ns，13 级逻辑。数据路径的 cell 为 4.773 ns、route 为 9.620 ns，音频目标周期仍为 13.021 ns。

实际路径经过 `compute_fault_s2` → `service/requested_rate_s2` → `runtime_configuration.config_accept_s3` → `core_ce_s2` → `n3485_s8/s7/s2` → `u_events/room_s2` → USB owner `n2029_s5/s3/s0` → `n2032_s1`。这条路径把本拍的渲染／配置许可通过矢量 ready 接到事件缓冲 ready，再回传给 USB。

Path11 的相同前缀通向 `held[76]`，slack −1.869 ns；后段经过 fanout 257 的 `n3485_s16` 和 fanout 128 的 `n6530_s5`。报告和路由网表 SHA256 均保存在 JSON，保持与原 M7 来源绑定。

## 最小修改与等价条件

只修改维护源码 `rtl/audio/gw138k_event_workstation.sv` 的普通矢量 NoteOn／Off 接受与延音释放游标前进两处。运行时矢量引擎的原握手保持为：

```text
vec_event_ready = vec_ready && !core_ce
dispatch requires (!pending || runtime_config_busy) && !sample_ce_i
core_ce requires (pending || sample_ce_i) && !runtime_config_busy
```

因此 `dispatch` 与 `core_ce` 必然互斥：`sample_ce_i=1` 时 dispatch 为零；`sample_ce_i=0` 且 pending 为一时，dispatch 需要 busy 为一，而 core_ce 需要 busy 为零；pending 为零时 core_ce 为零。JSON 枚举了全部八种 pending／sample／busy 组合。

两个调用点都已经由 dispatch 限定，故可在 `RUNTIME_RATE_ENABLE=1` 时直接使用 `vec_ready`，同时保留实际矢量引擎内部的 `vec_event_ready`。非运行时调用继续使用原表达式。没有增加寄存器或延迟，也没有改动 18-bit 事件、参数提交、PANIC、生命周期、32 声部、音频停钟或取消边界。

## 验证

完整双率 render service 使用真实 A/B/C 各 32 声部、八声部矢量、完整效果、实际延迟 DMA 与有序 DDR 模型。增加的断言每拍核对 dispatch 与真实 engine sample 互斥、dispatch 下的状态 ready 等于原真实矢量 ready，以及 held／释放游标推进确有引擎握手。新增用例覆盖矢量延音释放与新采样率请求交叠，以及生命周期在第二轮释放扫描中取消。

| 验证 | 结果 |
|---|---|
| 完整 render service | 48,653 请求／48,653 唯一响应，4 次取消 |
| 独立定点湿声模型 | 48,645 帧完全一致：48 kHz 24,323 帧，44.1 kHz 24,322 帧 |
| 实际矢量边界 | 2,058 个 dispatch 周期，10 个真实接收事件，2 类释放交叠用例 |
| 原 A/B/C 与矢量、换率、PANIC、迟到响应、故障关闭覆盖 | 全部通过，无 UNOPTFLAT |
| USB 停钟 fence | 3 次 hold 停钟／3 次 drain 停钟、PANIC、重连与 39 次默认事件；旧事件回放 0；旧实现负对照回放 8 |
| accepted 输入边界回归 | `test_current_workstation_sources.py` 17 项通过 |

完整 service 的最大 steady latency 为 1,168 compute clocks，自动配置为 1,620 clocks，带 loader 为 1,204 clocks；这些值是离线模型测量，不是新物理时序闭合或实体采样连续性的证明。

USB 停钟 runner 原先把 wrapper 参数列表硬编码为仅一个参数，遇到正式转发的 `CNN_FOLLOW_ENABLE`／`WORKER_DEMO` 时在运行前拒绝。此次只修改绑定提取，仍要求 `STOP_CLOCK_QUEUE_FENCE` 恰好出现一次并原样转发；真实队列源码、默认零策略和旧实现负对照均保持。

复现命令：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_runtime_render_service.py --project /Users/sphenicidition/.cache/gw138k-dual-20261031/m-demo-base-v7/workstation/Prj1 --output /tmp/dual138k-m7-vector-dispatch-service-v1
python3 projects/138k/push2_workstation/usb_a/sim/usb2/run_workstation_usb_stop_clock_fence.py --project /Users/sphenicidition/.cache/gw138k-dual-20261031/m-demo-base-v7/workstation/Prj1 --output /tmp/dual138k-m7-vector-dispatch-stopclock-v2 --require-native-opt-in
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
```

这些输出目录已存在，重新执行时须选择新目录。完整来源哈希、测试报告哈希、定点 trace 哈希及停钟负对照结果保存在上述 JSON；实现数据库和波形未加入源码。下一候选应重新 prepare 并获得新身份，再测量实际路由结果。
