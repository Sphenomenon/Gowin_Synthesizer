# Chorus 延迟精确窄化父级复验（2026-10-30）

已将 native Chorus 的延迟计算改为精确整数窄化，以处理 c7 综合报告的 Chorus 长组合路径。48 kHz 使用 `480 + ((3*t) >> 11)`；44.1 kHz 使用 `(((144670720 + 441*t) >> 16) / 5)`，在已锁定的 480＋96、1024-slot 参数下与旧算法逐值相同。乘积／分子分别只需 25／28 bit，除五只接收高 12 bit；没有新增寄存器或音频延迟。端口、FSM、存储、LFO、wet slew、配置／history／legacy clear 语义及系数保持。

父级实际调用新旧完整模块函数，对两采样率各 65,536 个 triangle 值共 131,072 项，与独立 64-bit 物理时间公式逐值比较通过。四个实际算术故障、八个来源故障、两项 pipeline／history 故障全部被预期断言拒绝。Chorus 六项、完整效果九项、room 系数五项、accepted 来源 17 项、profile 20 项（一个可选历史项跳过）通过。系数 JSON 用 Homebrew Python 3.14.7 精确再生；独立审保留系统 3.9 的浮点末位序列化失败，没有改系数或门限。

父级完整 runtime audio 实际 DSP／官方 DCS／PCM bridge／I2S 仿真通过 20,192 帧，其中 20,061 帧非零，14 次配置 ACK、八次帧内切换；最大 render 1,204 clocks、完整 slot 1,229 clocks。该压力 fixture 的预期故障／丢弃计数与独立运行完全一致，不能当作产品零丢帧承诺。组合与 fixture 新警告为零，无 UNOPTFLAT，所有实际输入首尾哈希保持。

原 provenance `41babc5e…` 字节不改；新显式 `narrow_exact_rate_delay_v1` 以精确反向适配还原旧 native，再走原基线证明，默认严格入口仍拒绝 changed native。四种 runtime profile 明确记录新来源政策。父级 fresh prepare 为 enabled `b35d8b12b34b80d9`、no-CNN `4945c0a736f9017b`、R00 `11957ce74834b832`、no-panel `6b9610324164f0c9`，各 12 项来源测试通过；最后一项 596 staged／269 enabled。相对对应前序只改变 Chorus RTL，增加适配／helper／契约三文件，编译项目清单和顺序不变。独立交付 48 份相对文件及 665 项绝对依赖均已父级核验。

本阶段没有综合或物理时序收益证据；正在运行的 C2103001 仍是旧 c7，不能继承本变更。后续用新身份重新综合并审查实际路径、资源和 CDC／PLL，再做 P&R。完整门禁和任务方框保持未完成，没有板卡、SRAM 或 Flash 操作。来源与验证 SHA 见[机器记录](workstation_task_20261030/runtime_chorus_narrow_parent.json)。
