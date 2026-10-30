# R00 FD：路由失败与资源复核（2026-10-30）

R00 候选 `custom138k-workstation-r00-v1-b9a2e0fdf36970be` 的 FD 物理实验已结束，工具退出码为 **1**，报 `PR0004`：**2,754 条网络未布通**。未生成 `.tr`、`.sdf` 或 `.fs`；setup、hold、recovery、removal、MPW 全部记为 **null**。这是一项已核验的失败阶段证据，不能据此宣称旧 FC 的 `/147`／ADSR 关键路径已经消除、时序闭合或可以部署。完整摘要、参数和证据哈希见[机器记录](workstation_task_20261030/r00_fd_route_failure.json)。

物理身份为 `custom138k-r00-render-reset-resource-experiment-C11030FD`，UserCode 为 `0xC11030FD`；源综合网表 SHA256 为 `f71d0328da2a5dc2c5487ece298d38ab59761aa97ca76c6bdb80d6bce7f9dc80`。它消费已封存 R00 网表与原 SDC，另使用维护的 nominal ULPI-only CST 附加约束及 P&R Tcl；place=1、route=0、replicate_resources=false、timing_driven=1、correct_hold_violation=1。没有放宽时钟／例外、删除功能或新增 DDR 位置约束。该来源与物理实验身份仅属于 FD，不绑定后续工作区改动。

P&R 于 `2026-10-30T10:22:11.435868Z` 开始，`10:40:23.514427Z` 结束，耗时 1,092.079 秒。独立复核验证了 25 项物理输入、584 项冻结 staged 输入和 6 项已记录输出的哈希闭包；本报告写入前再次重算全部独立封存文件及 6 项输出。部分 post-P&R `.vo` 的 SHA256 为 `512bf847fae4e7782d561af9e9aaac5b25fa5754e7681836117e1645d2d8286c`，它不代表路由完成。

| FD 失败尝试中的物理资源 | 使用量 |
|---|---:|
| Logic | 104,774 / 138,240 |
| Register | 63,006 / 139,095 |
| Logic Register as FF | 63,006 / 138,240 |
| CLS | 63,358 / 69,120（92%） |
| BSRAM | 274 / 340 |
| DSP | 121.5 / 298 |
| SSRAM RAM16 | 1,397 |
| PRIMARY / LW | 8 / 8；8 / 8 |
| PLL | 7 / 12 |

物理 BSRAM 为 274，不能用综合阶段的 246 等效计数代替。其它时钟资源为 GCLK_PIN 15/24、CLKDIV 2/24、DCS 1/20、DDRDLL 1/4、DQS 4/23。与旧 FC 相比，观测到 CLS +1,548、Register +11,884、BSRAM +2、DSP −5；FC 为 571 项 staged 输入，FD 为 584 项，期间存在 R00、流水线、reset、来源及物理配置变化，因此这些差值不是单项改动的净收益或路由因果证明。

独立寄存器核算按真实 DFF primitive 和精确层次路径计数。相对旧 R00 `4b1436d83219e765`，综合 Register 从 53,530 增至 63,006，增加 9,476；两者均含同一 `u_memory/u_ddr3` 的 5,459 个加密 DDR 寄存器。8 个 `/147` helper 共保留 8,413 个 DFF，其中 tag 4,013、算术与 valid 4,400，分别解释全局增长的 88.78% 与 42.35%。tag 占 helper DFF 的 47.70%，是显著部分，但不是多数。oscillator pitch 和 attack 两处合计 3,857 个 tag DFF，占 helper tag 的 96.1%；vector phase 实际只保留 114 个 tag DFF，不能按名义位宽乘级数替代实际统计。部分 post-P&R `.vo` 独立数得总 DFF 63,006、helper 8,413、tag 4,013，与上述核算一致。

现有文本／HTML／工具日志仅给出 `PR0004` 的 2,754 总数，没有逐网络失败清单；部分 `.vo` 也没有未布通标记。保护的 `.p`／数据库未作解密或逆向。**失败网络的 owner 分布保持 null**；FF 层次归属不能改写成“这些模块造成布线失败”。完整时钟／reset、CDC、RAM 数据弧、STA 及功能保持门禁仍未接受。

证据位于本机 `/Users/sphenicidition/.cache/gw138k-task-20261030/r00-FD-independent-physical-review-v1/`，下列哈希为原封存身份，不随本报告改写：

| 独立证据 | SHA256 |
|---|---|
| `FD_REVIEW_SEAL.json` | `f422cdf960dac2038b2f8c16f2f350655caea33d420270767c808b43b70d41a5` |
| `fd-results/SUMMARY.json` | `0b979acb00180e962920bae8ad0db879bd745a52d9f0d34e2b39fcf53a6c891d` |
| `REGISTER_ACCOUNTING.json` | `e8475d8df300e0d1912cd8f64ad100f7652ab8796447030fe4b08e536704ec61` |
| FD `physical_inputs.json` | `815100822697a6453c27823d091ede27c3ff49c186ca60397d83ceb47000506d` |
| FD `pnr_process.json` | `2cff722c0f5b764e01eb4a6b4d832fb3bfec153cfbf0577371dd606b4b35a984` |

下一候选计划是评估宽 tag 的同步本地 RAM 存储，保持除法算术、18／13-clock 延迟、valid 和 flush 语义，再以新来源身份验证实际推断、资源、路由与时序。用户也已选择 no-local-panel 后续方向；其实现、配置接入和验证尚在进行，不能记录为完成，亦不属于本 FD 候选。本报告不把两项后续工作写成已解决路由或已获物理接受。

本阶段只交付报告与机器记录，没有新增 EDA 或板卡操作。FD 没有硬件测试、SRAM 下载或 Flash 写入，`physical_gates_passed`、`hardware_tested`、`deployment_allowed`、`release_ready` 均为 false。既有部署证据保持原身份；本报告不推断此刻板上的 SRAM／Flash 内容。后续若需回退，须另选有日期的部署身份并核对实际读回，不能用 FD 或本地 latest 指针代替。
