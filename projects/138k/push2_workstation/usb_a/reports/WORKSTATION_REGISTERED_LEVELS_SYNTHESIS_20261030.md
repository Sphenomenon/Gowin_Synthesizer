# 注册控制输出候选：整机综合与局部时钟／CDC（2026-10-30）

[控制 level 修复](WORKSTATION_RUNTIME_RATE_CONTROL_LEVELS_20261030.md)的独立候选 `custom138k-workstation-v1-1aea3c01fa6c1b14` 已完成 Gowin 整机综合，退出码0，耗时501.347秒。570项登记输入在运行前后及父级复核时均保持，四项综合输出和日志也重新核对 SHA256。没有 AG 组合环诊断；其余警告逐码保留于[机器证据](workstation_task_20261030/runtime_registered_levels_synthesis.json)，未用退出码替代时序或功能接受。

| 身份 | SHA256 |
|---|---|
| candidate input | `1aea3c01fa6c1b14d28977f61d8b227786e80f816664e3db336e3b6b642d9f38` |
| profile configuration | `22e5a857a1aa7424a52078212a13f60aadc558d31b8a8f55e21b234f95afd8ea` |
| synthesis process | `650f4ac5dad19cdf4ba86e04e87bc6a52e980bd9e9cdc3e33a0c95e7a6b5cecf` |
| actual VG | `b8bd2a02e7f073593a9c8e5d7ee8cd15379c779acbbe152a1b901664d5f724b3` |

综合估算 Logic121,604（93,838 LUT、18,490 ALU、1,546 RAM16）、Register61,346、BSRAM268。它们不是CLS、物理BSRAM或布线拥塞结论；综合报告的自动时钟估算也不是实际安装SDC的routed STA。

父级在这份实际VG重新执行静态时钟审计和四项回归／23个负控，得到 `runtime-clock-source-audit-v1-5e98fc19dbd7c3e7`。已核对七个可见PLL、一处DCS及其FALLING模式、两路参考／选择寄存器／串行器连接、十六条时钟声明。DDR不透明IP内部UI分频、实际全局时钟树、Gowin查询解析及动态DCS行为仍未由此接受。

原Gray／媒体／USB fence检查器在新VG的已安装SDC模式通过，身份 `runtime-cdc-gray-media-fence-source-v2-bdaca012a45c9af5`；父级完整回归27项、77个负控通过，无跳过。覆盖仍是21组／400位Gray，以及已审查的媒体停止、hold、BLE release和USB停钟队列边界；没有扩大成全部payload、单bit或reset接受。错误legacy fixture路径导致的一次主动中断未计入通过结果，正确fixture的完整重跑日志另行绑定。

PCM/context检查器对新注册源及变化的消费者闭包按预期拒绝旧映射，尚在独立精确适配；没有删除失败项或将旧f1be审计转移到新网表。观察RAM内部CLK→DO数据弧、同域RAD setup／hold、异步复位recovery／removal、完整CDC／PLL及两模式物理时序均仍待完成。

原件位于 `/Users/sphenicidition/.cache/gw138k-task-20261030/runtime-registered-levels-synthesis-1aea3c01`；输入、工具、输出和全部父级检查日志的路径／哈希在机器证据内。该候选没有P&R、位流、板测或SRAM／Flash部署。后续明确选择的[no-CNN候选](WORKSTATION_CONDITIONAL_NO_CNN_SOURCE_20261030.md)属于不同输入，必须重新综合、检查实际网表和物理实现；上述接受范围不自动继承。
