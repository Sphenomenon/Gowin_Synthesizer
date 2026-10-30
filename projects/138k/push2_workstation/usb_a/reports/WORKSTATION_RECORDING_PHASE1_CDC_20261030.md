# owner8 录音 PCM 指针与 APB 邮箱审计（2026-10-30）

父级已导入并复验 owner8 第一批源码／实际网表检查器。固定 e855 网表的 PCM CDC 与 APB 邮箱共 425 个 FF，实际时钟分别为选中 MCLK／memory_clk，以及 ram_clk／memory_clk；APB 源不是 clk_50m。四项测试无跳过，23 个实际 VG 和五个 SDC／selector 负控全部拒绝，公开 CLI 重新核对综合封印、工具源和时钟拓扑后通过。

本批检查覆盖三个 Gray 组的 42 个首级位、两个普通首级位、两组共 82 位保持数据、六组三阶段本地复位释放链。每个首级 D 都要求已声明的唯一注册源 Q 和实际时钟；第一 Q 的完整扇出不能增加消费者。完整源扇出还保留同域 FF、RAM 与不透明 CPU pin，以已审查的端点形状身份拒绝新增或改变的消费者。FIFO 读 Gray 最高位实际是 `read_binary[4]` 的精确别名，不虚构一个已优化掉的寄存器。

源码协议审查区分了数学性质和网表／物理证明：5-bit Gray 检查全部 32 个 modulo 邻接情况，32-bit 饱和 drop counter 按 32 类 carry 推导单 bit 变化；APB 请求在接收第三边采集，响应在 settled ACK 后第四 APB 边采集，payload 保持到往返结束。独立三相位 PCM 数字仿真与 R00 runtime 的 13 正例／五反例另列证据；它们不证明异步 RAM 数据飞行或完整录音硬件。

输出的 35 行窄 SDC 仍为未安装提案：18 个 receiving CLEAR pin、两个普通 first-D cut、Gray／保持字 flight 与 hold、同步级间界限。380 个唯一静态 selector 各匹配一个实际 pin；工具没有执行 Gowin query，不切功能 CLEAR、不切整时钟域，也不切 RAM 数据弧。

seal 模块的 18 个 FF 直接使用 common raw reset，尚无本地释放；其 ready 首级 D 锥同时包含 memory 状态和 clk_50m reset producer，不能当成纯注册 memory 状态来源直接豁免。当前 VG 中未消费的四位 failure code 被消除，实际结果数据只保留 failed bit，未来新消费者必须重审。service、native commit、owner8 slot／ledger、RAM 所有权和数据时序、完整复位仍不在本批接受范围。

使用方式和完整限制见 [WORKSTATION_RECORDING_PHASE1_CDC.md](../tools/WORKSTATION_RECORDING_PHASE1_CDC.md)，父级证据和逐项哈希见[机器记录](workstation_task_20261030/recording_phase1_parent.json)。本阶段没有改写 VG／SDC、生产 source policy 或部署，没有上板。后续 BLE DDR 接线若改变消费者，不继承本次 e855 形状身份；须建立新候选并重审对应来源。
