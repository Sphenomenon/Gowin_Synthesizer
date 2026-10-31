# W DEMO：真实 performance telemetry 异步释放边界，2026-10-31

W7 实际综合 VG 与 routed VO 均证明 `u_runtime/u_performance_cdc` 的两组三拍释放链符合其原始异步复位协议。独立结构与 SDC 回归各 10／10 通过，八项网表破坏分别全部被拒绝；真实 frozen stream RTL 的 16 组停钟语义及三项语义变异通过。[配套 JSON](DUAL138K_PERFORMANCE_RELEASE_20261031.json) 记录来源、工具、实际网表和日志散列。

**本阶段仅交付独立审计、仿真和五条 SDC 提案；未接入 `runtime_profile`、未修改已冻结候选或旧 `physical.sdc`，没有新增综合／P&R／SRAM／Flash 验收。** 本轮已经开始的两套整机候选不等待该后续修复。

真实 UART 和 stream 输入分别为版本锁定的 `5df104cd…` 和 `90cb55ac…`，与 W7 被构建消费的 bytes 完全一致。UART 的 WIDTH=448 实例以 `reset50 && audio_reset_n` 作为共同低有效异步断言，source 使用 `audio_clk`，destination 使用 `clk_50m`。实际综合网表中的共同 CLEAR 是 `u_reset/started/Q` 与 `u_audio_clock/audio_reset_pipe_3/Q` 的精确 NAND。接收者是六个 DFFCE 的真正异步 `CLEAR`，没有把上游 DFFRE 的同步 `RESET` 输入当作公共异步复位。

每组三个寄存器 CE 恒开，首级 D 为 1，后级依次连接前级 Q；前两级均只有下一级 D 一个消费者。最后一级分别只复位 342 个 audio 域、343 个 50 MHz 域的本地业务寄存器 CLEAR，无跨域业务消费者、顶层导出或不透明 primitive。其 685 个业务 CLEAR 和四个后级 D 全部保留时序保护。

SDC 提案只从上述两个真实 source Q 到明确列出的六个 release CLEAR 设置例外，四对后级 Q→D 保留 2 ns 最大延迟。审计逐一解析选择器并拒绝缺失、重复、后级 D 或业务 CLEAR 例外。既有 held payload 使用 `get_regs` 的 hold 例外会在名字上命中带 CLEAR 的业务寄存器；审计用其实际显式 source Q 的完整消费者闭包证明该数据源到受保护 CLEAR 没有路径，未把名字相交误记为真实复位路径。

停钟仿真运行实际未改动的 448 位 stream：分别断言 reset50、audio reset，两侧时钟各停高／停低，并交换恢复次序，共 16 组。覆盖 49 次无时钟异步清零检查、102 次本域释放边沿检查、17 个完整新快照，以及接收停钟时新观测丢弃而 held 数据不覆盖。取消异步断言、缩短释放链、目的域使用错误时钟三项真实 RTL 变异均被拒绝。数字仿真不证明模拟亚稳态、最小异步脉宽或物理 recovery／removal。

下一 revision 集成时应只在确实保留该六寄存器的角色安装提案，并重新核对完整来源和实际 SDC、两模式 STA、每级 routed 飞行时间及全部业务复位 recovery／removal。原完整时序失败不能由此局部证明转为通过。

针对全局最差 2000 条 setup 被 audio 路径占满的问题，下批可在被 P&R 读取的 SDC 中追加 `report_timing` 报告命令：clk_50m→clk_50m 的 setup／hold 各 100 条，以及所有→clk_50m 的 setup／hold 各 100 条，均保留 `-max_common_paths 1`。W7 已有 CPU 专属报告在真实 `.tr` 中逐条对应其 SDC，历史 `build_full_song_85_clk50_timing.py` 保留同类 50 MHz 语法；新增命令还需登记严格 SDC 白名单。本阶段没有追加这些报告，也没有改变时钟或例外。
