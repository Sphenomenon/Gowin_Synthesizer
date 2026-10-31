# DEMO 的真实复位边界与专项时序报告接入

2026-10-31。W8 实测仍有 telemetry 三拍释放链的 recovery 违例：`started50 → source_release` −3.183 ns、`audio_reset_pipe3 → destination_release` −1.843 ns。前阶段[真实异步释放证明](DUAL138K_PERFORMANCE_RELEASE_20261031.md)现已接入现有 `custom_board` 的显式 DEMO 分支，下一份 W-DEMO prepare 会消费维护 helper 的五条精确 SDC。非 DEMO 配置的生成路径保持原样；当前 M9、W8 的封存 SDC 未修改。

W 的新增例外仅从两个实际 assertion Q 到六个三拍 release FF 的 CLEAR；四条后级 Q→D 均保留2 ns最大延迟。完整 DEMO 综合门会再次证明真实三拍链、各级时钟／CE／唯一消费者、共同NAND assertion、685个后续业务 CLEAR 和四个后级 D 未被例外掩盖，再核对实际 SDC 选择器。prepare 元数据固定角色、helper bytes 和每一新增行；缺失、重复、角色变更、源文件漂移均拒绝。旧候选继续按其原始不可变闭包验证，不据新源码重算历史来源。

M、W 下一次 DEMO prepare 同时添加四条 `report_timing`：clk_50m→clk_50m 与所有→clk_50m，各输出 setup／hold 最差100条、`max_common_paths 1`。保留原全局及CPU报告；严格白名单只增加这四条完整命令，不放松任何时钟或路径要求。这能直接观察M9仅两个50 MHz违例和W被audio最差列表遮住的路径。

W8实际 VG 与 VO 各12项验证通过（10项真实结构／SDC测试、2项构建选择测试），各8个网表破坏全部拒绝；原完整 SDC 加这组新行的独立外部验证也分别通过。交叉审查补充了行首空格／tab的真实functional CLEAR例外负控，现版会规范化行首后拒绝它们；外部 parser／消费者闭包和运行时依赖也单独封口。它仍须新候选实际 P&R 验证后级飞行时间与全部业务 recovery／removal。

15项 DEMO审计、7项策略、17项 accepted source-boundary、runtime CDC定向及9项真实custom-board回归通过；后者初跑未指定本任务工具环境而失败，明确xPack／Gowin／模型路径后全部通过。交叉审查还发现并补齐了stage helper安装依赖。首次完整prepare由既有recognition SDC封口拒绝：新增行原先位于其输出封口之后。修正组合顺序后，独立M10b／W9b输出均完成完整prepare，实际helper复制、来源锁、元数据、当前源码复现及不可变闭包校验全部通过。原M9／W8仍按旧闭包通过。

新候选身份分别为 `370f528922c4fcb5`／`01aa047a4d25aaf1`，587／644个封存输入、261／284个选中HDL，已分别启动完整综合。两份维护配置各锁821项；当前prepare实际选中M的4条报告及W的5条释放约束＋4条报告。[机器证据](dual138k_demo_timing_integration_20261031.json)记录所有来源和先前失败，本阶段不声称已完成新综合／P&R或任何实板验收。
