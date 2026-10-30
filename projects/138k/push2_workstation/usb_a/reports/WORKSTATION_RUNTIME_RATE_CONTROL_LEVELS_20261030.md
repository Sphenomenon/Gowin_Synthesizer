# 采样率事务跨域控制输出注册（2026-10-30）

实际 f1be 网表审查发现，`quiesce` 等输出由多位二进制 state 组合译码，不能将源域叶节点同属 50 MHz 理解为无毛刺。合法 PREFILL(7)→RESUME(9) 在明确的数字 bit-skew 模型中经历 7→5→1→9，quiesce 短暂重断言。真实 serializer 走完 1028 帧预填后，两级同步器可将该脉冲采为一周期，导致预填缓冲在非帧边界清空，并再次请求同一序号。

该复现采用实际 VG 的 LUT/INV 译码和人为 1/3/5 ns 位延迟，属于数字反例，未测量真实布线/PVT 下毛刺的发生概率或宽度，也未声称已发生错误物理 PCM。旧实际 VG、12 项 reset 审查产物和原 PCM 交付均保持封存。

修复只改 `workstation_sample_rate_switch` owner：三个跨域状态控制输出 quiesce、DAC mute、stream flush 由寄存器发布。唯一 `transition_to(target_state)` 同时写原 state 和三个目标译码；reset、正常、fault/recovery 共12处目标转移统一调用，没有第二套 state 或额外一周期延迟。QUIESCE 期间仍等待真实完整帧排空，随后才 mute/reset。

父级五项独立复验全部通过，包括原实际译码 skew 对照和三种 epoch 政策下的官方 GW5A DCS 事务回归。新增版本化[长期回归](../sim/test_workstation_rate_control_levels.py)直接实例化实际 transaction 和 serializer，不依赖私有旧 VG/cache：48/44.1 kHz 两模式均得到 wrong_target=0、pulses=0、sync_quiesce=0、unexpected_empty=0、request_count=1。严格锚点恢复旧三条组合输出的负控，两模式均被拒绝，结果分别为1/1/1/3/2。该回归使用 force 模拟合法 state 位传播，仍是数字模型。

现有真实时钟域两项通过（含三组相位、失钟/恢复）；真实 I2S 组合一项通过，覆盖 48→44.1→48、PDN4/启动1028帧、完整 CDC drain/prefill/running 和物理解码。profile **20/20**、来源 **12/12**、accepted **10/10** 无 skip。新 prepare：

```text
candidate: custom138k-workstation-v1-1aea3c01fa6c1b14
candidate_input_sha256: 1aea3c01fa6c1b14d28977f61d8b227786e80f816664e3db336e3b6b642d9f38
configuration_sha256: 22e5a857a1aa7424a52078212a13f60aadc558d31b8a8f55e21b234f95afd8ea
prepare_artifact_sha256: b76e2152a26a12420901f21ff3c67c149a56227d39d305aefd31a30ae671ea4e
product_sha256: 5b550ace18c8830f5675d633f77f325030206e7d1caf6c019bf6ad58b5f2c9be
```

来源为316锁/739 snapshot/570 staged/259 enabled；相比 `9993a3602be582fa`，仅实际 switch RTL 一项 staged 改变，SDC 保持320行。长期回归为非编译工具，不混入产品编译。完整来源、旧网表反例、seal、命令及父级日志见[机器证据](workstation_task_20261030/runtime_rate_control_levels_main.json)。新 prepare 已复制到独立 `runtime-registered-levels-synthesis-1aea3c01` 启动综合，结果另记；本检查点不宣称综合或物理通过。

新寄存器会改变 PCM checker 的源身份及组合消费闭包。旧检查必须继续 fail closed，须在新实际 VG 上重新审核并更新精确策略/负控，不能沿用 f1be 接受。prefill/context-ready 组合 level、功能 reset 的3/44/322异步pin、RAM payload、完整 CDC/reset/PLL 与双模式 routed timing 仍待证明。没有新增异步 reset cut、降频或放宽时序，没有 SRAM/Flash 操作。

回滚须同时恢复 switch RTL 及其 profile 来源锁并撤回新回归；旧组合实现保留为反例，不作可部署修复。当前已部署板卡未改变。
