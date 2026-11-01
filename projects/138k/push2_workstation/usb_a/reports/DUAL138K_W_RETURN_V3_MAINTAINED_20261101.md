# W 返回邮箱 v3 维护阶段

新 W prepare 显式选择 `independent-demo-w-return-mailbox-timing-v3`，为实际32位返回generation到301个资格D/CE消费者添加有限10.000ns setup与匹配的hold-only规则。296个payload FF对应9928个真实源/消费者对全部被覆盖；新增setup falsepath为0，没有修改时钟、reset或冻结W16。

维护helper检查actual VG/VO的完整解析、payload冻结、pending/ACK、两级同步、32位generation比较、capture、unpack index及所有消费者闭包；只允许经过复核的精确选择器。strict综合入口和物理PLL入口共享此检查；物理入口在lazy import前先封存helper和bluetooth依赖。M与旧W-v1/v2不导入或要求新helper，也不会重放时偷加新规则。六个原有performance/clock/held函数AST与HEAD一致。

实际W16 VG/VO使用cache-only stage/SDC overlay通过19项负控（13原项＋6项SDC补充）；最终mapped负控强制报预期契约错误。来源/旧政策兼容共10项通过，accepted source17项通过；原ActualRelease在没有指定旧netlist时明确skip。部分早期cache VG负控曾因canonical跨层名字被重复加scope而缺driver，它们不能当作该契约的负控证明；最终维护测试改用有效raw binding/常量并检查失败原因。旧证据保留，此处明确收窄其范围。

本次7个owned文件、8个实际冻结输入和51个证据已由主线程独立重哈希；逐文件身份、命令和限制见[机器报告](DUAL138K_W_RETURN_V3_MAINTAINED_20261101.json)。新helper SHA256 `796052f6b78b1cfd194de0ecf10b90774c434713d8c4bf0c48c19d9a5503fe85`；最终seal `fe18223f549d72683bb90f15807fb647a821494e40aa73d9502aea36f4ff2736`。

这是维护实现和离线验证，不是新v3整机。下一步显式刷新来源锁、准备全新身份并重做完整综合/P&R。冻结W16仍使用原v2 SDC，缺失9632条资格路径的结论不变；本阶段未验证新约束的routed slack。native-response可达性仅为命名前提，尚非mapped归纳证明；整机reset/CDC/时序和实板声画验收仍分别保留。未启动EDA、未操作硬件、未写SRAM/Flash。
