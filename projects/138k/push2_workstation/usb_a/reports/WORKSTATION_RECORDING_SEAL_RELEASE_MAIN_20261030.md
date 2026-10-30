# 录音封存本地释放父级复验（2026-10-30）

接入 [封存桥修复](WORKSTATION_RECORDING_SEAL_LOCAL_RELEASE_20261030.md)：common reset 两域异步断言、各自两级同步释放；memory ready 先寄存再发布；source hold 保持到真实终态，失败码保留到下一次接受。CPU observer reset 不取消 backend，也不使待完成 seal 提前放行。

父级重跑桥测试 2 项（11 场景／12 突变），真实录音 runtime 14 个正向场景／五个负控，全部通过；严格 Verilator lint 零警告。四份来源锁只更新三项既有输入并增加三项验证／契约输入，保留前阶段 PCM v2 的三个来源锁。accepted 17 项、Profile 20 项通过；Profile 中一个旧默认候选可选项因未提供独立 legacy prepare 而跳过。

四种实际 prepare 各 12 项来源测试通过。enabled `d2c211c35c4817a9`／no-CNN `dc14ab12fd19353e` 的 571／572 项 staged 字节完全不变；R00 `c76a67b45b07366f`／no-panel `925724eb1ed13487` 的 584 项中，仅 `rtl/services/workstation_recording_seal_bridge.sv` 改变。没有重建或修改旧 stage。

父级逐项核对 agent 封存的八个非 profile 文件，四份 profile 与当前 PCM v2 来源合并后也重新验证。证据见 [recording_seal_local_release_parent.json](workstation_task_20261030/recording_seal_local_release_parent.json)，包含日志、完整 runtime 结果及 prepare 的路径与 SHA256。旧桥在新增 CPU-reset/pending-seal 场景中失败的独立反例保持原记录。

本阶段未综合或 P&R；前阶段 `7d1c3b9b464ff722` 综合未包含本次修复，不能继承其网表。新 release FF、registered ready、hold/result 的实际综合网表闭包及完整 CDC／reset／STA 仍待验，无物理或硬件接受，无 SRAM／Flash 操作。回退可恢复本阶段桥／测试／契约及对应来源锁后重新 prepare。
