# 实际 18ed Delay FIFO 父级映射复核（2026-10-31）

父级独立重放固定 18ed／VG `c9f88c71…` 的实际映射及全部 476 个负控。两个 native Delay FIFO 各为 65-bit×512、四个 SDPX9B、零 SSRAM；14-bit 物理地址、偶／奇 bank、读写时钟／CE／reset、完整 head 消费者和 post-pop 有效 next-Q 均与独立声明核对。40 个 Gray 首级位的注册生产者／CLEAR／CE、接收移位及完整首级扇出通过声明结构检查。综合 BSRAM 不作为物理占用或路由接受。

两 bank 同时做相同 payload 位交换能够绕过单独的唯一性检查，原缺口明确保留。补充 proof 将各 bank 的 65 位 DI 与独立源端点逐位比较，并证明实际 64 个 write formatter LUT 的反馈／flush marker 真值；pending_id 与 transaction_id 的同复位／同更新源关系单独约束。父级重新运行两 bank 协调交换和 64 个格式化故障检查，66 项完整结果与封存逐字段一致。DSP 算术不属于这项 formatter proof。

完整图检查的 410 项故障也全部拒绝。最初 `verify.py --replay --negatives` 在子进程成功后因 JSON 列表全等失败；原因是 CEA 路径由 set 遍历，两条结果位置 78／79 互换。父级保留失败日志，原脚本在新外部输出重跑，验证 410 个唯一 case key、全部完整 case 内容及其余报告字段都精确一致；比较器只消除列表顺序差异，不删除或改写任何 case、失败原因或原封存。映射正向重放另行通过，原 30 文件／611 外部依赖重哈一致。SHA、原失败和比较结果见[机器记录](workstation_task_20261030/native_delay_fifo_actual_parent.json)。

旧基础 netlist parser 漏读 escaped named formal 的空白连接，本次独立严格解析对象逐项等于维护 PCM parser；实际 729 个此类连接与导出向量别名均纳入图。没有改旧 parser、历史端点、源码或网表来隐藏遗漏。这里接受具体存储／payload 结构和局部 Boolean 关系；完整 FIFO next-state、源 Q 所有跨域消费者、RAM DI／地址／CE setup/hold、输出／碰撞／Gray flight/skew、完整 reset 与 routed STA 仍未接受。没有 EDA、板卡、SRAM 或 Flash 操作，下一物理候选继续保留这些门禁。
