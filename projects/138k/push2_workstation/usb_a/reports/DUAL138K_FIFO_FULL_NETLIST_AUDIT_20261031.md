# 双 138K：完整综合网表的 FIFO 复位与实际写准入审计

2026-10-31。M9、W8 都保留已完成综合的原候选身份及封存输入；本次仅修正外部审计器对实际综合网表映射的识别，未改 RTL、固件、SDC、编译选择或候选内的工具／manifest。W8 完整综合门重新通过，原失败审计与旧工具 hash 保留；外部当前工具 hash 另行封口。没有新建身份、重写历史输入或伪称重新综合。

W8 `custom138k-workstation-w-demo-v1-d1109d2f36e8e171` 的实际 VG 为 `f50efd53ba976a644a9128b537dfda4e3424508da7534020aec7c7d84f89178c`。共享 parser 漏认 owner→FIFO 的 escaped scalar formal aliases，造成实际 CEA 的虚假独立切口；复用已有 `PcmNetlist` 的严格 named-port lexer 后，608911 个端口、543 个 escaped 端口均从原 VG 精确解析，VG 不重写，共享 parser 不改。实际 CEA 在 4096 组独立切口赋值中均满足“USB 末级 release 为 0 时不能写”。

该 W8 映射把 producer bit0 的实际 D 编译为 `ALU_MODE=0` 的 SUM。审计仅允许真实 Q0／真实 packet-memory CEA 两个操作数、CIN/I3=GND、producer CE=VCC，并记录全部实际 pin 与四行 next-Q 真值。依据是安装的 GW5A `prim_sim.v` 第329、334–336行的 ADD 方程，文件 hash 写入证据。未扩展通用 ALU 解释器，也没有 carry-chain 或时序豁免。

M9 `custom138k-workstation-m-demo-v1` 对应完整候选身份及 VG hash 见 JSON。其实际 Q0 保留 LUT 映射，使用原有效 next-Q 布尔证明；CEA 组合锥因 owner 吸收暴露19个独立 frontier。没有提高 `Graph` 原16输入枚举上限：固定唯一 USB 末级 release=0，沿9个实际 INV/LUT 逐锥计算保守余因子，共88组局部赋值，每个 LUT 至多64组；其余输入始终独立任意，实际 CEA 的可能值严格为 `{0}`。另以独立 Graph 求值核对一组 release=1／CEA=1 的具体 frontier 见证，防止恒零空通过；该见证不声明顺序可达性。

两套实际综合网表分别验证13个生产指针 FF、两拍 USB release、真实 USB／audio 时钟、异步断言、首级唯一消费者、实际 memory CEA、Q0 有效增量和原两级 audio reset。W8 的9个负控包含旧 escaped-formal 解析误报复现、三项 reset／clock 破坏、真实 CEA 旁路、保留所有真实输入而把 CEA 驱动 LUT 的 INIT 改为全1，以及 ALU mode／CIN／operand 三项破坏。M9 的8个负控用真实 Q0 D／CE／LUT INIT 破坏替代 ALU 三项；CEA LUT INIT 负控明确到达余因子 oracle，不能靠“缺少 release frontier”提前通过检查。所有负控均拒绝。M9 实际映射未触发 W8 的旧 parser 缺陷，回归器据实记录，不强迫两套 VG 具有相同编译形式。

独立 FIFO／真实 owner v6 再次通过停 USB、停 audio、双钟停转、六边沿 hold＋六边沿 drain、热插拔／PANIC 和首写指针回环；2个 RTL 与5个小综合网表负控均拒绝。6项策略、22项 DEMO 和17项 accepted source-boundary 测试通过，`git diff --check` 通过。M9 早先两次回归器失败是 W8 专用测试预期误用于不同映射，原 JSON／hash 和修正原因保留；实际正门没有因此放宽。

[机器证据](dual138k_fifo_full_netlist_audit_20261031.json)包含原失败、两套实际网表完整正负控、独立 v6、现用工具与原封存快照差异及 W8 完整综合门的路径／hash。W8 已另行准备 `D2103108` 的默认 CST／SDC＋显式 ULPI LVCMOS33 物理实现；本报告不预报其 P&R 或资源／时序结果。未操作板卡、SRAM 或 Flash，也不提升物理 CDC、时序或硬件验收。
