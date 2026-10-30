# 222fb761 公共 CDC 与 TF/counter 父级复验（2026-10-31）

固定候选 `222fb761448fb6c0` 的公共 CDC 与 TF/counter 新范围完成父级复验。编译源码仍为 `9bc8fc5`，VG `f621fcbe…`、process `2b9a71d6…`；后续独立 helper commit `eae4eb6` 的八个全新文件逐字导入主线。两种来源身份分列，生产入口、原 helper、profile、599 staged／269 enabled、SDC 和 CST 保持。

新范围核对 13 组 phase1、42 组 raw 完整扇出，以及 88 条已安装 shared 约束，包含 43 个 false-path 首级位、182 个 Gray 位及 1,308 个载荷位。相对旧 18ed，phase1 四组和 raw 九组闭包有明确的新端点声明；没有借接收 pin 猜测缺失生产者，也未重新安装或放宽约束。TF 八组同步对、36 位 held 数据及取消 gate 的闭包保持；四组 native counter 重新验证，其中录音／显示两组同步输出闭包发生变化，仍在原本的本地域。下游业务 next-Q 等价不在本阶段证明范围。

独立任务完成 17 项新 scope 回归、19 个实际公共边界图负控、276 个实际 TF/counter 图负控及五个 scope 身份负控，全部通过；276 控制后再次证明正向图。旧 scope 仍严格拒绝新候选。父级在主线重跑公开 shared CLI、17 项／19 图负控及 17 项 accepted 来源回归；公开 JSON 与独立结果完全一致，phase1／raw／shared 的完整保存 JSON 仅作明确 checkout 前缀归一后亦完全一致。初次内存 Python 容器与 JSON 容器直接比较失败保留，最终比较未删字段或数组项。

父级另重放独立 `verify_review.py --replay`，重新计算 shared 及 TF 正向结果，并逐项核验完整 receipt；未重复运行 276 个 TF 负控。独立 seal `a3fdeb25…` 绑定 105 文件／1,456 外部输入。父级封存 58 份 root 来源快照，并分别核对原编译 commit 或新 helper commit 的 Git blob；父 seal `d30317be…`，74 文件／1,555 外部输入，最终 hash-only 校验通过。完整身份与范围见[机器记录](workstation_task_20261030/display_load_cdc_scopes_parent.json)。

本阶段只增加固定实验的审计 helper，不是新生产构建入口；另一个候选须将声明纳入有等价负控的维护目录或退休这些副本，不能换 VG 哈希继承接受。原生 Delay FIFO、时钟与 PCM 检查分别有自己的证据，不由本 receipt 继承。完整 CDC／reset、载荷飞行行为、RAM 物理数据弧、PLL、routed STA、物理资源及 owner4 无 DDR 中转仍未验收。

没有运行新 EDA、生成新位流或操作板卡，没有 SRAM／Flash 部署。下一步是用这份新范围及已封存的综合／native 检查，绑定独立 `C2103102` 物理实验；任务方框保持未完成。
