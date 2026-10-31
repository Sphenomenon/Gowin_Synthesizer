# USB 实际写许可的共享组合关系证明

2026-10-31。W10 全量综合后的首次严格门拒绝了 packet RAM 的 CEA 写许可。旧 frontier 同时将一个 NOR 的输入与输出当作独立自由变量，产生 `$1_4=0, $1_5=0, n1969_4=0` 的假反例；实际 LUT2 INIT=`4'h1` 强制 `$1_4=~($1_5|n1969_4)`，该三元组不能同时成立。原严格失败日志和 W10 的 VG／全部封存输入保持不变。

维护 `workstation_usb_fifo_reset.py` 在原直接证明不足时，完整展开实际 INV／LUT 的共享组合锥，用精确 BDD 证明 `!final_release && actual_CEA` 恒为零，同时要求存在 release=1 的非零 CEA 见证。W10 实际为46个 INV／LUT、44个任意 terminal（43个寄存器Q及1个独立 ALU 输出）、1190个 BDD 节点；没有可达状态假设。完整 final release 闭包的354个 FF 均为 USB 域，唯一 opaque 消费者为实际 packet RAM 的 CEA，没有顶层导出。原13个功能写指针、本地两级释放及真实 CEA→producer Q0 增量检查保留。

全局 Graph／parser 和16输入真值表上限未改。原 M10b／W9b 仍走原直接真值表证明；独立完整组合 SMT 及6类变异与 BDD 结果一致。最终 v2 的19个结构／写许可负控全部拒绝，包括旁路实际 CEA、常零／常一、移除真实 NOR 关系、错误 release、未知 LUT pin、错误 clock／reset、额外消费者及实际 Q0 ALU 增量破坏。v1 的18／19拒绝结果保留：新增坏 pin 可先走原直接路径，v2 因而在两种证明分支前均检查精确 INV／LUT pin 清单。

工具 SHA256 `5ec63ef6bee7f1bcc9a14d7d58de810e625e87ab9d9a4fcaf3d5402f6df9ff20`，测试 SHA256 `a875bc1307bede18a5c71b69f62b220fdb7ba954dfb98d4f7dfc84c2d0bab106`。新的外部完整严格门通过，审计 JSON SHA256 `367831fb673a9993a7edfb6b8a4210c625d5dc1f701306ed4628a776b7c4f0a6`；其独立新审计器身份不追改原失败结果。W10已以 `D2103116` 启动默认完整 P&R，VG／SDC 不变，CST仅有原审查过的 ULPI IO 补充，无 DDR far region。

[机器证据](dual138k_usb_shared_cea_20261031.json) SHA256 `5325d8a4702f4f484d902cf28c57a106f1e6df9e8906a271891478d0352006ac`，固定原失败、最终全部负控、旧两份直接路径、独立 SMT 及新完整门。该修正不产生 RTL 或 SDC，不证明完整 CDC／STA、真实 USB 外设或硬件验收。未下载 SRAM、未写 Flash。
