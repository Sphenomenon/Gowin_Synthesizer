# Runtime 状态 CDC 源域寄存与在途乐谱终态（2026-10-30）

本阶段把 controlled 组合中的三处组合跨域源改为源域寄存器。关键的切换禁止
状态由 50 MHz `switch_busy_50` 寄存公共 clock-owner 的 `busy || quiesce`，
再保守异步断言 compute 禁止状态、经两级 compute 边沿释放。PC drop 与独立
媒体原因仅增加本地诊断寄存，不建立新状态 owner、计数器或切换许可来源。

补测发现，仅在旧两级采样前增加源寄存会新增业务终态漏洞：实际 APB 已在途
的乐谱启动可在首 cue 为 frame 0 时先结束，成功脉冲被门控，但失败也没有
锁存。最终实现及同一精确相位回归已修复该问题。默认／非零 epoch 的完整
两率功能回归、新录音／乐谱边界、源寄存逐沿检查和负对照均通过。

这是维护源码与离线验证阶段；没有证明模拟毛刺、亚稳态、routed CDC 或硬件。

## 来源、配置与身份

- 唯一产品 RTL：`rtl/workstation/workstation_runtime_controlled.sv`。
- 原始 SHA-256：`ce4f7c86e5412673698e4575a65ef312ba93a443f5fba757613a994cfdcb9b51`。
- 最终 SHA-256：`0aca8806baa26742e0571652f89d36cc4303d7e92d405d08c4b536614136e49d`。
- 回归输入集 SHA-256：`8eb196a7d2a77195efae0e525a81eaa9725327758115987592493b1f9b38be51`。
- 非零 epoch：`native-runtime-controlled-offline-v2-nonzero-8eb196a7d2a77195`。
- 默认 epoch：`native-runtime-controlled-offline-v2-8eb196a7d2a77195`。
- 在途首 cue：`native-runtime-controlled-offline-v2-inflight-score-nonzero-8eb196a7d2a77195`。
- 机器证据：[runtime_cdc_source_registered.json](workstation_task_20261030/runtime_cdc_source_registered.json)。

runner 显式使用先前 clean prepare 的 legacy 闭包与当前维护 native 源，并逐项
记录 hash；参考 prepare 身份仍为 `custom138k-workstation-v1-41e653fe462e5ea3`，
不把该旧身份当作当前维护源的新完整候选。控制为 50 MHz，compute 连续
76.8 MHz，memory 为 100 MHz；实际官方 DCS／I2S 覆盖 48 kHz 与 44.1 kHz。
参考准备、测试及本阶段均不更新 profile/source lock 或 accepted 入口。

## 三处生产者审查与实现

| 旧跨域源 | 问题与影响 | 最终源、接收及延迟 |
|---|---|---|
| `busy_o || quiesce_o` → compute | 两个公共电平都组合解码 clock-owner 的多位 FSM；逻辑联合等价于非 RUN，但没有源寄存／hazard 证明。它直接影响 REC abort、score start/stop/done，属于业务门控。 | 50 MHz `switch_busy_50` 先寄存，新增一个源边沿；该源 FF 异步断言 `switch_busy_compute=11`，仅释放等待两 compute 边沿。 |
| `pc_drop != 0` → compute | 源是 32-bit 二进制递增计数器，进位可同时改变多位；组合归约不是安全源寄存。该位仅进入原 PC health 投影。 | 50 MHz `pc_drop_seen_50` 寄存后进入原两级 compute 同步器；新增一个源边沿，保持原非零／wrap 语义，不改为新的 sticky 权威。 |
| `tf_active_i || tf_busy_i` 等 → 50 MHz reason | TF active 包含 generation 比较，busy 包含保守释放与控制快照联合；显式 TF provider 有 active/busy 生命周期约束，但未提供组合源物理无 hazard 证明。reason 仅为诊断。 | compute `reasons_compute[2:0]` 寄存 TF 联合、score、REC 三个独立原因后进入原两级 50 MHz 接收；新增一个 compute 边沿，不宣称原子业务快照。 |

授权切换的 `media_busy_compute` 原先就有源域寄存及保守断言／三沿释放，本阶段
不改它。`switch_block_reason` 仍可以落后于真正 inhibit；PC health、APB map、
448-bit performance、18-bit events、公共参数／会话和录音／乐谱 owner 均保留。
公共 `busy/quiesce` 仍由原 clock transaction 提供；新增寄存器只是 CDC 投影。

`switch_busy_50` 由 `reset_50_n` 异步置 1，目标由 `reset_compute_n` 置 `11`。
两者都来自共同服务复位的本地域释放；CPU `preset_n` 不清这些禁止状态，也不
复位音频。源电平来自单一 FF 后才驱动目标异步置位，解除只移入常数 0，经
两级真实 compute 边沿才允许新操作。此实现的恢复／移除、布线及 FF 识别仍待
新完整候选的物理检查。

## 在途 APB 首 cue 的实际功能边界

定向模式先通过真实 APB 装入一个 `frame=0` 的 cue，再把真实 SCORE_START 命令
送入原 APB CDC。它等命令已经本地捕获但尚未发布 command_valid，选择下一个
50 MHz 请求沿，使实际乐谱启动位于该请求接受后的第一个 compute 沿。此过程
不强迫内部命令、score state 或 ready，不用假的服务 ACK。

| 同一确定相位 | 仅源寄存＋旧两级采样负对照 | 最终保守断言 |
|---|---:|---:|
| clock request accepted | 439,790.001 ns | 439,790.001 ns |
| 实际 SCORE_START 消费 | 439,796.070 ns | 439,796.070 ns |
| compute inhibit 置位 | 439,835.130 ns | 439,810.000 ns |
| 终态 | running=0、done=0、failed=0，拒绝 | 明确 failed=1，通过 |

负对照只在输出目录中生成维护 RTL 的精确临时副本，保留源 FF，恢复旧两级
采样；为直接检验业务终态，它只关闭“必须异步置位”的结构断言，其他输入与
业务路径保持。最终 runner 自动要求它以 `in-flight zero-cue score lost explicit
failure` 失败。这是确定时钟下的功能时延复现，不模拟毛刺或亚稳态，也不是物理
CDC 验收。

## 验证与结果

```sh
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_runtime_controlled.py --project /Users/sphenicidition/.cache/gw138k-task-20261030/native-runtime-profile-rev4-v2/workstation/Prj1 --output /Users/sphenicidition/.cache/gw138k-task-20261030/runtime-cdc-source-register-nonzero-final --nonzero-epoch
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_runtime_controlled.py --project /Users/sphenicidition/.cache/gw138k-task-20261030/native-runtime-profile-rev4-v2/workstation/Prj1 --output /Users/sphenicidition/.cache/gw138k-task-20261030/runtime-cdc-source-register-default-final
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_runtime_controlled.py --project /Users/sphenicidition/.cache/gw138k-task-20261030/native-runtime-profile-rev4-v2/workstation/Prj1 --output /Users/sphenicidition/.cache/gw138k-task-20261030/runtime-cdc-inflight-score-final --nonzero-epoch --inflight-score-boundary
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
```

默认与非零 epoch 两套完整回归结果一致：

| 项目 | 结果 |
|---|---:|
| 真实物理 I2S／compute 观测帧 | 1,078／1,078 |
| 48 kHz／44.1 kHz 观测帧 | 361／717 |
| 显示原子观察／效果上下文核对 | 1,077／1,077 |
| FFT bins，48 kHz／44.1 kHz | 384，128／256 |
| 实际 APB／USB／CPU 事件 | 1,077／33／28 |
| 50 MHz／compute 源逐沿检查 | 1,219,374／1,851,077 |
| switch 源有效变化／原因源变化 | 5／16 |
| 接受切换后保留前一源沿的检查 | 2 |
| 保守异步断言／本地释放检查 | 2／1,818,138 |

完整回归另外验证：

- 音频启动前暂停真实 compute 字节接收端，实际 115,200 baud UART 产生 drop
  `0→1→2`，覆盖计数进位，再恢复 compute 并观察原 PC health 位；没有借此
  制造物理音频丢帧。
- TF busy→active 的真实接口交接保持 inhibit 与诊断原因；运行媒体继续拒绝
  rate request。实际 APB 新录音与切换竞争仍以 code 7 失败，新乐谱启动被拒。
- 独立真实 consumer TB 完成 14 项检查、9 次录音失败、128 FFT bins、完整
  256 cues，并新增 switch 同沿启动、恰好最后 cue 将完成时的禁止，以及解除
  后显式恢复。257 次 LED 更新包含该恢复测试，不代表 cue 容量改变。
- 三套均无新组合／fixture 警告，无组合循环，运行前后输入 hash 保持；
  `test_current_workstation_sources.py` 的 10 项通过，`git diff --check` 通过。

父级另在 `runtime-cdc-source-register-parent-nonzero` 和
`runtime-cdc-source-register-parent-inflight` 独立重跑完整非零 epoch 与在途首 cue
测试；来源身份、所有输入 hash、功能与 consumer metrics 均逐项等于上述子任务
证据，在途旧两级采样负对照也再次被拒绝。JSON 附两份父级输出的路径及哈希。

## 剩余门禁与回退

本阶段未进行新完整 profile prepare、综合、P&R、PLL／routed CDC、SRAM、Flash
或实板操作。新源必须重新锁定，并按新候选身份复核 source FF、异步置位、
释放级、保持字／Gray 和所有实际约束端点；不套用旧网表的端点或验收。
DDR 为有序功能模型，TF 为上下文一致 fixture，未补齐 TF 有序 EOS、长录音或
BLE 录音业务。跨域操作仍要求调用者序列化成功启动；APB ACK 只表明命令接受，
不代替明确失败／成功结果。

不修改冻结输入、原 manifest 或历史证据。回退应使用原先完整登记候选与原始
输入，不能把本源码写回 baseline 或沿用旧接受身份。本阶段经父级独立复验后
提交；新的 source lock 和物理交付继续单独登记。
