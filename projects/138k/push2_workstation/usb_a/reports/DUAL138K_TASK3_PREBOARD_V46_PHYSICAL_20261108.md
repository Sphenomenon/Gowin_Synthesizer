# v46 物理门禁结果：未通过，上板继续禁止

源码检查点为 `d49c314f`。M/W 完整综合审计仍为 29/29、26/26 通过；本报告增加真实物理结果，不继承整机验收。

| 板 | 来源尾号 / UserCode | 物理资源 | 布线与时序 |
|---|---|---|---|
| M | `ae6090a0ca3e94c4` / `D21108AF` | BSRAM 253/340；CLS 60416/69120；FF 58695；Logic 90709 | 默认路由失败，2595 unrouted；无最终 STA/SDF/有效位流。 |
| W | `a6e2dbc2c10da5fd` / `D21108BF` | BSRAM 287/340；其余见 JSON | 完成 P&R，但 setup/hold/recovery/removal 为 −3.299/+0.123/−0.527/+0.284 ns。 |

W 位流 SHA256 为 `45799b91ec274c76339e3f13d874c8088b6f14dee80eb21dc01b3fb158a542d2`，仅为失败候选产物，不能加载。W 使用 task3 工作树维护审计器后，PLL/startup 与保留 mailbox 子门禁通过；这不等于完整物理 CDC。第一次缺少 Gowin 仿真库、第二次误用主工作树旧审计器的失败记录均保留。

最新网表定位：W 仲裁 read pointer 经 owner-veto、native bridge、FIFO pop 和完成选择到 `completion_kind` / `completion_generation`，最差 −3.299 ns。另一条路径从跨板接收 payload bit71 经录音取消校验及 ingress 到 BLE recording result payload CE，最差 −3.225 ns。DDR reset 源位于 R105C179，57 fanout；到 R65C23 初始化 CLEAR 的数据延迟 8.455 ns，recovery −0.527 ns。其余输入时钟和例外均未放宽。

缓存投影验证已完成：完整录音完成元组的最终 fault cofactor 在六组捕获／时钟比例下逐周期比较通过，另有 8192 个二态／四态任意边沿；录音 CANCEL padding 与 active key 分字节比较通过 17441 项实际表达式四态比较。这些仍是投影诊断，未宣称已纳入新完整候选。W flat VO 同步器投影通过，并拒绝故障源断接；维护检查器须加入精确的 flat net 绑定后重新审核。

M 另启用 P2R1 做一次已诊断默认详细路由失败的算法对照；VG/CST/SDC 与失败 P2R0 完全相同，仅 UserCode 与路由算法变化，1800 秒仍停留在详细 maze routing 后超时（exit −15），无有效位流／最终 STA；峰值 footprint 约 2.29 GB，不是内存不足。没有继续轮换路由算法。

[结构化证据](DUAL138K_TASK3_PREBOARD_V46_PHYSICAL_20261108.json)绑定日志、报告、实际位流及诊断。task2、单板、历史回退保持不变。未操作板卡，SRAM/Flash 均未写入；[SRAM 清单](DUAL138K_TASK3_SRAM_CHECKLIST_20261108.md)仍仅为后续步骤。
