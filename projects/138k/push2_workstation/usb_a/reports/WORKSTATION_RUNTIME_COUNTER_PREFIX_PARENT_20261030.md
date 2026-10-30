# Runtime 并行 Gray 解码父级组合（2026-10-30）

已将版本化 native counter `c921ff58…` 合入四种显式 runtime profile，以五级并行前缀代替 31 级串行 XOR；源 Gray、两级目的同步、三拍复位释放及目的组合输出保持，目的时钟延迟增加零拍。最高位直连以保留四态语义。原锁定 `1b6ff697…` 字节仍暂存、编译关闭；accepted／pinned／resource parent 和未选 profile 的默认来源保持原选择。

父级重跑精确 RTL GF(2) 全 2^32 输入等价、三组异步／停钟／复位／回卷比较、四证明负控、七来源选择测试及 17 accepted 来源测试通过。新实际 prepare 的 GPRJ、replacement、copy、integration 和 prepared enabled／staged 身份均明确选入新源；旧 serial277 CDC scope 对该实际候选正确拒绝，未被保留的禁用旧文件掩盖。独立审额外六证明／12 实际选择负控，以及 source 停低的两组异步配置通过。

父级真实 PCM observation 三组相位通过；完整 controlled 的 1,078 物理帧与 1,078 观察帧匹配、两次采样率切换及 1,077 个显示效果原子 tuple 通过。末次 physical／display 丢包且没有后续源时钟、两次停源、四次公共复位与 wrap 的 health 回归通过。enabled profile 20 项（一个可选历史项跳过）通过。交付及独立审的 focused 显示流水线 128,702 tuple 检查通过；完整 HDMI 入口仍因旧 provenance 不匹配而失败，原门禁和失败证据保留，未宣称完整 HDMI 通过。

四份父级 prepare 各 12 项来源通过：enabled `fdf9df8a034de035`（573／260）、no-CNN `abe2d4dfb482781c`（574／260）、R00 `52c2626c46974204`（586／267）、no-panel `c7d66b419868f7f4`（593／269）。相对 TF 前序只增加 native counter／契约两文件并改变 GPRJ；新源一对一替代旧编译项。四 profile 冲突只在来源 SHA map，按两方已审查内容的并集合并，所有业务配置／revision 未变。SDC 不变，未将 XOR 层数等同 LUT 或物理收益。

本阶段同时封存收到的 TF 独立审（原双初值／两负控，新增四负控及独立双向 GF(2) 证明）和 FF 完成态独立审（51 输入／六输出／三额外实现产物均保持，1,324 未布通、无位流／STA）。父级逐项核验三套源码交付／独立 seal 共 140 条记录；counter 四 descriptor 的来源 map 合并另行逐项核验，不冒充与交付旧 descriptor 字节相同。路径及 SHA 见[机器记录](workstation_task_20261030/runtime_counter_prefix_parent.json)。

新候选组合 TF quiet 发布 FF 与 balanced counter，后续使用独立复制输出重新综合，再审查实际源 FF／接收两级／完整闭包和关键路径、名义时钟 P&R。新来源不继承 277／FF 接受；当前无新 VG／物理／硬件接受，没有 SRAM 或 Flash 部署，完整门禁与任务方框保持未完成。
