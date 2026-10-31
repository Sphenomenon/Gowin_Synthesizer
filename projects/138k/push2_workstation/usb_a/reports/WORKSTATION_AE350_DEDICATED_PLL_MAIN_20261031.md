# AE350 原生 PLL 修正的主树整合复验

2026-10-31，作者提交 `43aaa112b86411a1c060c0d7095f419c73dd0f82` 以 `200a925` 合入；`3cce72e` 将六份 fresh native profile 的来源锁更新到同期已验证的 ROM128 兼容工具。更新只涉及实际改变的维护存储 RTL、RV32 模型和容量／调用图工具哈希，普通 profile 仍使用原 16／64 KiB 容量。用户修改的 task.md 保持未提交。

[源码阶段](WORKSTATION_AE350_DEDICATED_PLL_20261031.md)将官方要求的 `u_cpu_pll/PLL_inst → PLL_R[0] → CLKOUT1 → CORE_CLK` 带入维护中的原生装配。新物理门禁分别核对唯一 active CST、实际 routed PLL 位置和直接硬核时钟连接，遇到未解析语法、额外驱动、歧义或缺失证据即失败。独立审查补齐了嵌套端口表达式遗漏和 Verilog escaped identifier 同名的负例。冻结 baselines、vendor 及 accepted 选择不变；旧候选继续使用其原来源工具核验。

主树使用显式 xPack GCC 15.2 和三份锁定网表完成两个新的实际 prepare：

| profile | 新候选身份 | staged／enabled |
|---|---|---:|
| AE350 business revision 3 | `custom138k-workstation-ae350-business-v1-60960c9725e08e89` | 613／271 |
| 默认 native revision 5 | `custom138k-workstation-v1-8a8105661ada8b07` | 603／260 |

两者都记录 requested PLL_R[0]、placement 尚未验证、hardware_tested=false。主树独立通过 97 项有效检查：新门禁 8（包括实际 C9 正例／C8 错位负例与真实 prepared 元数据篡改）、默认来源及闭包 21、business 来源及闭包 8、物理 PLL 工具 21、implementation preparation 22、accepted 来源 17。两个历史 opt-in 条件未运行，分别为旧的 unprofiled native 候选和完整物理 manifest，不补称通过。

作者交付父包 `native-ae350-pllr0-delivery-v1` 的 verifier 已由主代理复验，34 文件／3,545 固定输入，seal `d3ed4e43053a3602b0875a25003c10e0304ac8a602d2a2ea5a5552dfdbc54dac`。主树父包 `/Users/sphenicidition/.cache/gw138k-task-20261030/native-ae350-pll-main-parent-v1` 的 verifier 也已通过，458 份来源快照、1,333 项直接外部文件，seal `7ed422795fa4a930e0066823933b6d33f71ff1261ec613be4469b0be02e3340b`；[机器记录](workstation_task_20261030/ae350_native_pll_r0_main.json)绑定候选、ROM、配置、测试日志及来源身份。

本阶段没有新综合、P&R 或板卡操作。实际 C9／C8 是隔离探针对门禁的正反例，不是上述两个原生候选的物理证明。native RTC 仍继承 50 MHz，下一批单独接入已维护的 32.768 kHz 源，再生成新身份做实际综合；完整资源净收益、Cache／DMA、手机流式音频和整机硬件验收仍未完成。
