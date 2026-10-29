# F02 startup结构检查与DDR hold布局提案（2026-10-30）

F02原位流没有改变。新增版本化结构检查器对同一 routed VO／SDF 的 **114个启动复位端点通过原40ns预算**，最坏settle＋recovery **7.802ns**；7个真实网表／SDF负向修改均被拒绝。原冻结PLL失败、整机setup／hold／routes失败记录保持原样。没有运行新综合或P&R，也没有访问板卡。

证据：[f02_startup_and_floorplan_investigation.json](workstation_task_20261030/f02_startup_and_floorplan_investigation.json)。该记录包含完整逐端点补充结果、原F02全部34份物理证据哈希复核、测试、实际hold时序和待审查布局提案。原 [f02_physical.json](workstation_task_20261030/f02_physical.json) 不覆盖或改写。

## 启动检查器迁出

新维护入口为 [workstation_serializer_startup_audit.py](../tools/workstation_serializer_startup_audit.py)。它从冻结 `check_serializer_startup.py` 迁出原完整检查，不再对检查器运行时字符串替换。native／legacy的TMDS路径和时钟字极性是明确配置；当前native布局固定四条lane、真实差分引脚和`0000011111`时钟字，不能自动猜极性。

实际F02有三处历史中间单元名变化，只替换`pll_stop_s0`不能完成检查：

| 边界 | 实际单元 | 结构解析依据 |
| --- | --- | --- |
| DDR PLL stop反相器 | `…/pll_stop_d_s0` | PLL.ENCLK2唯一驱动；LUT1／INIT2'h1；输入必须为stop_reg[2].Q |
| UI CLKDIV RESETN反相器 | `…/n809_s2` | CLKDIV.RESETN唯一驱动；LUT1／INIT2'h1；输入必须为ddr_rsti_reg[2].Q |
| 负边沿校准时钟反相器 | `…/u_ddr_init/n2497_s2` | 实际校准FF.CLK唯一驱动；INV输入必须是UI divider输出 |
| DLL STEP capture enable | `…/n2474_s0` | 实际capture CE唯一驱动；LUT3／INIT8'h40，精确`!old && recent && dll_lock` |

stop2.Q只驱动该反相器，反相器只驱动DDR PLL.ENCLK2；不能出现新增扇出或旁路。stop三级和DDR reset三级的FF类型、INIT、时钟、使能、数据链和复位关系均核对；stop首级还必须来自原ddr_sync状态FF，复位源必须来自原置位型dll_rst FF。PLL／CLKDIV专用原语和分频、全部PHY primitive inventory、8个负边沿校准FF、8个DLL capture、所有RESET/CLEAR连接及reset例外范围保持原门禁。

原4种source sequence场景的108-cell参考网表、加密IP、检查器和sequence JSON都重核哈希；停止后至少8个50MHz周期、释放到重启至少4周期，故原80ns停止窗口仍是前提。真实路由114端点最大settle＋recovery7.802ns；DDR部分最大7.067ns；DLL STEP的arc＋route＋setup最大7.876ns，均低于原40ns。该补充不替代模拟PLL／DLL行为、复位首级亚稳态评估或板测。

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_serializer_startup_audit.py
python3 projects/138k/push2_workstation/usb_a/tools/workstation_serializer_startup_audit.py --physical /Users/sphenicidition/.cache/gw138k-task-20261030/f02-physical-C11030F2 --json /Users/sphenicidition/.cache/gw138k-task-20261030/f02-startup-structural.json --self-test
```

4项单测检查新旧名字都必须具有相同结构，并拒绝错误极性、输入、类型、额外输入和多驱动。完整真实VO／SDF负例逐个改动：gate INIT、PLL.ENCLK2旁路、stop时钟、额外gate扇出、PHY RESET旁路、reset布线45ns、stop首级D旁路；每项均命中对应拒绝条件。冻结检查器、vendor和baseline均未改。

输出字段`startup_subgate_passed=true`仅对应本补充；`original_frozen_pll_gate_passed=false`、`full_pll_gate_reexecution_required=true`、`all_physical_gates_passed=false`保持明确。后续维护物理门禁应直接调用该版本化入口，同时重新执行全部PLL子检查；本轮没有把旧checker失败记录改成成功。

## DDR hold为何失败

原精确0.800ns min-delay约束仍在，launch／capture仍是直接Q→D；launch来自DDR UI CLKDIV／4，capture来自50MHz。实际位置是`R89C153[0][A]`→`R89C152[0][A]`，彼此紧邻。

fast STA的launch时钟到达1.439ns，CLK→Q0.144ns、数据布线0.248ns，数据到达约1.831ns；capture时钟到达1.893ns，加0.800ns关系、0.035ns不确定度和0.013ns hold，required约2.741ns，故slack **−0.910ns**。SDF slow最大cell＋wire0.708ns不能替代这条含时钟偏斜的fast hold结果。

F02已有原三项DDR硬资源位置（PLL_L[0]、DDRDLLM_BL、LEFTSIDE[4]），只缺历史wloadn区域约束。C1机器记录的SDC SHA256与F02 **完全相同**，都是`bfcf675d98f07dbcb51eaedfa554b59e14b3f9efca0c2b66822e774ef5198354`；[C1报告](WORKSTATION_RESOURCE_A26_PHYSICAL_20261027.md:62)记录相同三硬资源位置及`R[40:50]C[70:90]` capture区域，整体hold最小+0.050ns。

本机没有C1原始physical.cst／VO／SDF，只有版本化记录及其哈希，因此**不能声称字节复现C1布局，也不能从C1余量推断新F02已通过**。历史`derive_physical.py`只允许a18／a19／a23且floorplan只允许a23；不直接扩大其身份白名单或改历史证据。

## 建议的独立物理适配

提案是在新分配身份／新输出中，只向当前F02 physical.cst追加：

```tcl
INS_LOC "u_memory/u_ddr3/gw3_top/u_ddr_phy_top/wloadn_3_s0" R[40:50]C[70:90];
```

这将capture从紧邻launch的位置移开，给原minimum-delay策略提供更长布线路径；变化后的完整时钟偏斜和slack必须新P&R验证。提案CST哈希及全部前置条件在机器记录中。没有生成新候选，也没有启动EDA。

适配归属应为现有 `tools/workstation_custom_board_implementation.py` 的显式可选参数，默认不改变。准备前必须绑定父网表／全部输入哈希，验证精确DFF拓扑、两端时钟、唯一0.800ns约束、目标尚未定位；保留三硬块、所有pin／ULPI声明、SDC字节、自动hold修复和原place2／route0／replicate0。不要套用独立`hdmi_isolation.cst`的R52C59／R17C2布局或复制整个历史工程。

实现后需核对实际CLK／D节点落入目标区域、精确hold含clock skew非负，重新执行全部STA／CDC／PLL／资源／功能门禁。DDR DQS HOLD setup−1.867ns、audio／USB setup及readiness2ns等其他失败仍需分别修复；这条布局提案不能代替整机收敛或允许部署。音频探针B7锁定输入和已接受profile均未改。
