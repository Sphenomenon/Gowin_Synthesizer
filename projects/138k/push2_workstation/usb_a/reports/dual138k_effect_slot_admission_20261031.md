# M11 实测音频使能路径的等价组合分解（2026-10-31）

本阶段仅修改维护源码 `rtl/audio/gw138k_event_workstation.sv` 与 `rtl/audio/workstation_runtime_stereo_effects.sv`：为效果服务增加只读的 `sample_slot_ready_o=state==IDLE && !barrier_busy`，只在原有 `core_ce` 表达式中使用它。完整对外 `ready_o` 和所有其他 `fx_ready` 消费者均保持原式；没有新采样周期，没有移动参数、PCM、取消或立即故障否决的时刻。

原参考是实际消费并完成 P&R 的 M11 候选 `custom138k-workstation-m-demo-v1-b5f6da2e64a82b66`（物理 user code `D2103115`）。其完整 STA 最差 setup 为 −3.762 ns，5619 个 setup 端点违例，最差 hold 为 −3.556 ns。目标路径由 `compute_release_2_s0/Q` 经 `core_ce` 的配置／效果许可逻辑到矢量引擎 DSP B；邻近 `underflow_sticky` 路径为 −3.753 ns。此报告没有把该候选作为可部署镜像，也没有把 DDR hold 的布局实验当作音频 setup 修复。

组合等价关系来自实际接线和原外层条件：

- `!runtime_config_busy` 给出 `busy==0`；`runtime_config_block=!busy && (rate_commit_i || history_clear_i)` 与外层 `!runtime_config_block` 联立，给出两个请求输入均为零。因此实际效果端口 `rate_commit_i && rate_ready_o`、`history_clear_i && history_ready_o` 均为零，相应两项 accept 均为零。
- `runtime_fault=failed || fx_fault`，原外层 `!runtime_fault` 已立即排除效果故障；该否决保留在 `core_ce` 中。
- 实际 `engine_clear=RUNTIME_EFFECTS_ENABLE ? native_clear:panic_accept`，且效果端口接 `engine_clear`。native 分支原外层 `!native_clear` 因而排除了效果 clear。
- 其余条件不变时，完整效果 ready 恰好等于存储状态的 IDLE／非 barrier 谓词。外层条件为假时旧、新 `core_ce` 均为假。legacy 分支仍选择完整原 `fx_ready`。

`prove_effect_slot_admission.py` 从维护 SV 提取上述真实方程、实际配置／历史输入和完整旧 `core_ce` fixture，锁定旧表达式身份。native 与 legacy 两种选择在所有组合状态下均为 UNSAT，无可达状态假设。四项变异都产生真实 `core_ce` 差异的 SAT 反例：删除 slot barrier、删除外层 fault、删除外层 native clear、删除外层配置请求阻断。

完整真实服务回归将 M11 精确旧模块与维护新模块同时实例化，在每个正、负沿比较全部 50 个公共输出和内部真实 `core_ce`：

- 共 115929947 次边沿比较通过，48691 个请求与响应一一完成。
- 48645 帧效果输出另与独立定点模型逐帧比较，其中 48 kHz 为24323帧、44.1 kHz为24322帧；真实 A／B／C 与矢量引擎、完整效果和有序 DDR 模型都参与执行。
- 21 次配置、324 次历史操作、11 次取消、1074 个真实取消边沿、12 组请求／完成边界和12组首个合法后续事件通过；1024 次 epoch 圈回、同沿 PANIC、迟到配置 ACK 与 sticky fault 检查通过。
- 参考模块仅在生成的测试副本中重命名三个模块，以及参考效果 `delay_stage` 实例和它的两个 `defparam` 目标，避免 Verilator 对双模块的同名层次目标冲突。两个 `RAM_STYLE="block_ram"` 保留原值，没有删除或改写运算／握手表达式。共同 DDR 输入由原模型驱动，两个服务的全部 DDR 输出也在50项比较中。

双采样率真实 I2S 回归分别通过：D-only 正式 APB／CDC owner → 原 `core_ce` 取参 → 完整效果 → 一次音量 → DCS／I2S，共1918物理帧、1913次取参、1917显示快照、12次PANIC（10次在途），每采样率143帧dry、32帧drive、32帧crush和547帧wet。通用 APB／CDC／效果／I2S 回归为1454物理帧，1436有效帧和18显式取消／错误帧，覆盖119帧直接PCM、37帧半音量、9次历史清理和446次wet运算。此处的“物理帧”是测试台解码的 I2S 引脚帧，不是实板采集。

最初的证明提取／类型语法和服务端口数量适配失败均保留在外部输出目录。`full-service-miter-v2` 的原始编译失败是 Verilator 对同名层次 `defparam` 目标的冲突；生成参考实例改名后的 `full-service-miter-v3` 通过，没有通过修改生产 RTL 绕过它。完整输入、工具、日志和结果 SHA256 见同名 JSON。

复跑命令：

```sh
/Users/sphenicidition/miniforge3/bin/python3 projects/138k/push2_workstation/usb_a/sim/audio/prove_effect_slot_admission.py --output <新的绝对输出目录>
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_runtime_render_service.py --effect-slot-miter --project /Users/sphenicidition/.cache/gw138k-dual-20261031/m-demo-base-v11/workstation/Prj1 --output <新的绝对输出目录>
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_ae350_pcm_runtime.py --d-only --project /Users/sphenicidition/.cache/gw138k-dual-20261031/m-demo-base-v11/workstation/Prj1 --output <新的绝对输出目录>
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_ae350_pcm_runtime.py --project /Users/sphenicidition/.cache/gw138k-dual-20261031/m-demo-base-v11/workstation/Prj1 --output <新的绝对输出目录>
```

本阶段只证明源码及离线行为等价。新输入仍需以新候选身份完成全量综合、P&R、真实资源／完整 STA、物理 CDC 及实板声画验收；不预记时序或资源收益。回退时恢复完整旧 `core_ce` 并移除只读状态端口与接线，再重新生成候选。本阶段未操作 SRAM、Flash 或板卡。
