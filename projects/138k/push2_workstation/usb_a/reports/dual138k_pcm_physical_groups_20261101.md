# W-DEMO PCM physical epoch 比较分组

2026-11-01。W11 `0xD2110101` 的实际最坏路径由 `compute_epoch[7]` 到 PCM owner `written[2][11]` 的 CE，20 级、data 17.793 ns、setup −5.018 ns。时钟路由为 3.139／3.142 ns，skew 0.003 ns；数据由 cell 5.796 ns、route 11.691 ns 和 C2Q 0.306 ns 构成。综合网表与布线网表确认原 XOR reduction 仍映射成 `ALU_MODE=3` 的串行 NE 比较，不能将等式改写本身当作物理优化已成立。

CE 局部 LUT 按实际 INIT 穷举复核：D=`n5576_9` 是 slot2 的 no-clear permission；CE=`!n5576_9 || (write_index_hit && write_slot_hit)`。`n5576_9` 的实际扇出为 256，随后两条路由为 1.758／1.293 ns。比较结果经共享许可、终态及位图清理锥到达该端点；VG／VO 完整组合 CE 锥分别有 1,214／1,215 个单元，均闭包到寄存器／输入，没有据此声称整锥网表形式等价。位图清理、撤销及同沿更新优先级不在本次修改范围。

维护源只把 `active_physical` 与 `physical_epoch_i` 的 32 位比较分成 `[7:0]`、`[15:8]`、`[23:16]`、`[31:24]` 四个独立结果，再 AND。四条标量 net 使用安装版 Gowin SUG550-2.1E §5.8、PDF 55–56 页明确支持的 `/* synthesis syn_keep=1 */` 语法；它是 net 保留约束，没有增加寄存器。其余 physical 条件和整个状态机保持；严格源码检查将该段反向替换后恢复 W11 原 SHA256 `a28f84ee8ba95e8aa0a3ea7faf764f9c5cbcaf40dc25e13f17f01871ce5645ae`。新源 SHA256 为 `3342a94cfd4e103efbb11808c5753aa8839069634ebf5d78ed80c0dab9cff837`。

新针对性验证覆盖完整 64 位二态输入和 128 位四态符号编码，差异查询均 UNSAT。明确不匹配位支配其它 X／Z；没有明确不匹配时，有 X／Z 则仍返回 X。实际 owner 的 1,536 组四态仿真一致；缺失最高位、末级 OR、缺少 keep、越界改变 rate 条件等四项源码负控均拒绝，两个错误比较模型均找到 SAT 反例。使用现有完整旧 owner miter，7,811 周期逐沿比较 61 公共／状态组、512 个 PCM RAM 字和 4 组位图／帧数，含 6,000 随机命令、7,369 次许可检查、576 组未知格式／ID及四负控，通过。

原 8 项 owner 回归通过，保留默认 48k／44.1k、±2000 ppm 各 576,000 输出帧的完整漂移长度。正式 D APB／CDC→owner→完整效果→I2S 双率／PANIC 仿真通过 1,918 个物理模型帧、1,917 个显示快照及 12 次 PANIC（10 次发生在处理途中）。这些结果使用理想时钟和有序 DDR 模型，不包含 HCI／SBC／真实无线及板卡验收。

[机器证据](dual138k_pcm_physical_groups_20261101.json) 绑定实际 W11 路径、VG／VO 提取、局部 LUT 穷举、手册身份、冻结源码及全部验证。复现新的比较证明使用 `sim/audio/run_ae350_pcm_physical_groups.py --output <新目录>`，需带 Z3 的解释器，例如本机 `/Users/sphenicidition/miniforge3/bin/python3`；完整 owner 与 D 测试命令同列于 JSON。本阶段没有运行新源综合／P&R，不能预记资源或时序收益；由新候选核实四组边界在实际网表中的实现。冻结 W11／M13 不变，未操作 SRAM／Flash，不提升整机或硬件验收。
