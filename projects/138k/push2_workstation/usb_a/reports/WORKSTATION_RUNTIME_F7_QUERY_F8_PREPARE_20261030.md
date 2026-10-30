# revision5：F7 约束失败与 F8 精确适配（2026-10-30）

F7 离线物理试验返回 1，用时 10.741 秒；SDC 原第 105 行的 BLE release 查询触发 TA2003，尚未进入 placement。原 manifest、输入、日志及 process 全部保留，没有位流或板卡操作。它不属于用户允许裁剪 CNN 前的两次有效资源布局布线尝试。

失败查询为：

```tcl
set_false_path -to [get_pins {u_ble_pcm_cdc/source_release*/CLEAR u_ble_pcm_cdc/destination_release*/CLEAR}]
```

BLE 专属约束在 runtime shared filter 之后追加，因而旧查询仍被保留。封存 f1be 网表中，两组三阶段 release 被综合合并到 `u_managed/observation/drops/source_release*` 和 `u_managed/midi_bytes/source_release*`。独立审查核对了六个实际 DFFCE 的时钟、恒高 CE、逐级移位、共同异步复位及末级 INV 到 BLE ack/req CLEAR 的连接；原第 63 行已经准确覆盖六个实际 CLEAR。

静态展开检查了 431 个 get_pins/get_regs 查询，另有 16 个 get_ports 查询。唯一非 DDR 的整组空查询就是第 105 行，非空查询中没有空备选 selector。17 个进入加密 DDR 内部的查询仍不透明，全部保留；不能以 VG 看不到为理由删除。这是静态连接与名字核对，不冒充工具 query、完整 CDC 或复位接受。

F8 采用独立身份 `custom138k-runtime-physical-resource-experiment-C11030F8`，仍绑定 `custom138k-workstation-v1-f1be50e853d3700a` 的封存综合结果。VG/CST 与 F7 完全相同；SDC 仅将原第 105 行换成说明注释，53 行已审 CDC 和其余约束逐字保持；Tcl 只更换 UserCode，仍为 place2/route0、关闭资源复制。全部 CNN／曲谱及其它功能保持。

```text
VG SHA256: 8fc53d099ebead55ca3926c8d4b2b45b3504fcb1ac1ed5dbcaa1b6e1a1834535
F8 SDC SHA256: aee25f28eb1ca057e635f4392f7a7fa00b786cdf931afb2f579247098ca5bf73
F8 manifest SHA256: 54e72b29c72870a0253733283996c4a5d758f23b48025ca4d0585dae6319fda3
```

适配脚本要求原 SDC/VG、preflight、F7 manifest 的精确身份及唯一完整锚点。9 个负控均被拒绝，覆盖移除真实别名/DDR 约束、放宽 delay、追加宽 cut、修改源身份和缺少 replacement 覆盖。F8 preparer 再核对 570 项封存输入、实际审计来源、23 个注册成品输入；8 个 manifest 负控均被拒绝。父级启动前再次核对 manifest 和全部注册输入。新 prepare 通过，现已启动离线物理运行；**本报告只封存 F7 失败与 F8 prepare，不包含尚未完成的 F8 P&R 结果**。

完整静态 inventory、脚本源码、负控、F7 日志及 F8 manifest 见[机器证据](workstation_task_20261030/runtime_rev5_f7_failure_f8_adaptation.json)。cache 原件位于 `f8-sdc-adaptation-review-v1/`，F8 位于 `runtime-rev5-physical-C11030F8/`，均在 `/Users/sphenicidition/.cache/gw138k-task-20261030/` 下。重现方式是证据中的两个准备脚本，再调用已有 `run_runtime_physical_experiment.py --physical <F8目录>`；已经运行的候选不得重用其 process 身份。

这是有明确来源和退出条件的 cache 资源试验，没有修改生产来源，尚需在维护 composition 中修正 BLE 追加点并建立新候选。F8 不替代主线后续 `60f1c843ad79aa6e`，也不继承整机物理、完整 CDC／PLL、电气或硬件接受；manifest 的部署和全部整机门禁仍为 false。若后续查询失败，必须保留原失败并逐个核实，禁止自动剔除 DDR 目标。本阶段没有 SRAM 或 Flash 操作。
