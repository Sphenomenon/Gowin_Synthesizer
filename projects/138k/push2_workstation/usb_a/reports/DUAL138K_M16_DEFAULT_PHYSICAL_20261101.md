# M16 默认完整物理实现

M16 `D2110110` 已完成完整 P&R 和六组物理子审计，整机时序仍未闭合。setup 529 个违例端点、最差 −1.222 ns；hold 1 个端点、最差 −3.445 ns，尚未进入部署。物理 BSRAM 235／340、DSP 119／298、CLS 50,976／69,120；FF 46,932、LUT 53,812、ALU 13,092、SSRAM 141，与综合 equivalent BSRAM 195 分列。

候选 `custom138k-workstation-m-demo-v1-5f5ba9978313e96b`，manifest SHA256 `e3fc6eb06cfe82170ea66004f2e29f8734363a7ad62bd0fccca26a9478371662`；VG `4044a2595197d6993dd6c81684af7b63f5af441f5ac3b71edf4cb8fa2f4e468a`；完整 SDC `6fa398b1bf7418d052e6cdc0c98c90512d506cc75931fa952b974f7b7db1562c`；FS `bad83d87c9b81d6b45e81c23a0338b824105f29d0533fac04f42e32b222c8ea7`。[机器报告](dual138k_m16_default_physical_20261101.json)保留配置、命令、来源、全部资源和四类时序。

Gowin V1.9.12，place2／route0，关闭资源复制，保留自动 hold 修复及原 DDR 3.500 ns。P&R 689.962 秒、退出 0，布线与位流均完成。recovery +0.523 ns，removal +0.281 ns。DDR hold 从 R75C9 到 R75C3：arrival 1.958、required 5.403、skew 0.434 ns；同 VG／完整 SDC 的 `D2110111` 仅追加两条 DDR 远区 CST，已启动独立 P&R，不预填结果。

四条实际 clk50 报告为同域 setup +2.282／hold +0.181 ns，全来源 setup +0.860／hold −3.445 ns，各表 100 条上限不冒充完整端点统计。全局最差为 pc_bytes held_data→destination_data（clk50→audio，关系 0.104 ns），随后是 APB request_held→request_local。现有握手数据稳定性、完整真实消费闭包及窄约束仍在核对，原失败保持。audio 同域及 DDRui 同域仍有真实负路径；不能只修约束就宣称整机闭合，也不把源码算术证明转授全网表等价。

实际 VO native 54 项（50 通过／4 跳过）及 45 破坏负控、边界 7 项及 61 负控、官方六 PLL／三 shared tuple／7 负控全部通过。全部任务退出后，主线程再读复验 30 个物理文件及 2937 项完整证据，包含 1374 冻结审计输入、588 staged、875 prepare 来源和 PLL 依赖。完整 seal `m16-audits-v1/default-complete-seal-v1.json` SHA256 `71243397cd509acfebe2061af22f45ce45847c29b16f9facb6ca1ddf3adf2b8c`。

本基础 M 仍无 CNN。后续 TF cofactor 维护源没有混入 M16，W14 外部 boundary 审计修复也不改本候选。无板卡操作、SRAM 或 Flash，完整 HDMI／DAC／Push／25K／TF 声画、CNN 跟奏和双板联合验收仍未完成。
