# 显示候选综合时序：跨域路径解释更正

固定 `222fb761` 的综合表中 `57.039 MHz` **不能证明同步计算逻辑不满足 76.8 MHz**。此前显示综合报告及任务历史记录将它直接表述为计算时序不足，结论超出了该表能支持的范围。原报告字节保留，本报告更正解释；也不据此宣称时序通过。

父级对只读审查完整重放通过：VG `f621fcbecb79012c0486e248a1cc686437b9d11ab887c22b2c8554a62f8b49af`，编译源码 `9bc8fc5063f34c914553e725264a0566eba7cea0`。三条实际最慢路径的 setup relationship 均为 **0.104 ns**：

| 路径 | 域 | Slack |
|---|---|---:|
| held_reply epoch bit0 → serializer have_next CE | compute76.8 → selected DAC | −6.906 ns |
| launched_epoch bit0 → TF quiesce 第一级 D | source50 → compute76.8 | −6.867 ns |
| held_reply epoch bit0 → request_sequence bit2 D | compute76.8 → selected DAC | −6.765 ns |

前后两条 PCM 路径的实际 sink 在静态字符串检查中均匹配已有 `set_max_delay 13.020` 和原 hold 例外；完整回复组的 263 个真实依赖 sink 全部静态覆盖，295 个 selector 另含已核对的成对 D／CE 目标。**实际工具查询是否解析、例外是否传播到 routed 分析仍未验证**，不能从字符串命中或本综合表反推其已经生效。TF quiesce 第一级 D 未命中现有精确例外，时序核算仍未关闭。

完整、未按域筛选的图闭包也已重放：reply epoch bit0 有 230 个 selected 域 D／CE；launched epoch bit0 有 759 个 FF pin，其中 758 个 source 本地域、1 个 compute 域，另有 24 个原语端点；quiesce 第一级 Q 只驱动第二级 D。不能把 759 个 pin 都称为跨域目的地。

后续源码修正分开实施。TF 注册 held-level quiesce 应移除组合译码的跨域发布，但保留取消、generation 和 source hold 的同边沿语义；新 Q→first D 仍需新网表／物理验证。PCM 接收端增加 98-bit 本地捕获至少多一个 selected MCLK（81.380208／59.051398337 ns），边界到达可导致错过整帧期限，当前暂缓该修改；不能用原始 payload 旁路、提前 ACK 或停采样掩盖它。

本阶段只修正分析，未改 RTL、SDC、时钟、profile 或固定 C2103102 输入，未新增例外，未运行 EDA 或操作板卡。C2103102 实际 P&R 在独立阶段运行；完整 STA、CDC／reset、PLL、功能和硬件仍未接受。

机器摘要为 [display_load_timing_interpretation_parent.json](workstation_task_20261030/display_load_timing_interpretation_parent.json)。只读交付 seal 为 `0caa72f12e09268bd4ba2578c3771ac7061b79a81a6136c6de4137a3df6388b9`，13 项本地／44 项外部输入均重新哈希；父级完整重放日志位于 cache `display-load-222-plan-root-replay-v1.log`。该来源的定点解释不转授其他候选物理接受。
