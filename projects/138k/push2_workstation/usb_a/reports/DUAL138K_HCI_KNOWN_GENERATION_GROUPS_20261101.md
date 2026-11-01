# HCI known generation 比较维护阶段

实际host_rx owner将stored/live generation比较分成4个保留边界的8位组，替换action/full drift两处相同谓词。没有新状态或周期，所有clocked bytes保持，credit／lease／disconnect／generation／即时fault和优先级不变。新RTL SHA256 `6547173e42b6057dedb9ec5fe22ba3dbcda957c7f6344fcda98a39643be7fc88`。

W16far实际VG/VO逐位确认32个mode3 carry比较`generations[1][31:0]`和`known_generations_i[63:32]`，末端直达action_owner_drift。实测到offer_handle CE为21级／−4.536ns、20ns关系／数据24.276ns；cell7.721＋route16.249＋C2Q.306。default的tx_header→generations WRE路径还有transport/flow上游比较，不属此局部改动，不承诺同时闭合。

新专项通过精确inverse、128位任意known-mask/value表达式UNSAT、完整owner17674周期／33输出／41状态miter、HANDLE_SLOTS1/2/16共208896实际模块四态检查及4RTL负控＋2来源负控。原action160228检查／147464四态／3负控、identity twins和11负控、完整native268检查／11负控及实际UART8E1/H5模型均通过（patch253、bootstrap4、returns10、notifications3、reconnect1，无skip）。这些是离线仿真，不能转授真实蓝牙验收。

主线程重验393证据、4owned和1395冻结W16工具及原网表，全部匹配。逐文件来源、命令和独立operand复核见[机器报告](DUAL138K_HCI_KNOWN_GENERATION_GROUPS_20261101.json)；seal `567f5fbc6d67f7a2b36204d4389fffc5615a86033cc81e1b2fb87f08f92db831`。旧action/identity来源逆向链保留，新测试重构不生成生产RTL。真实资源／时序需新候选综合/P&R；未操作硬件或写SRAM／Flash。
