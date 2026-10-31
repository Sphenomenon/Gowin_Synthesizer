# 双 138K：原生 HCI 池长度比较的等价时序修正

2026-10-31。W9b `D2103112` 四份真实 50 MHz 报告显示，同域建立时序前 100 条路径均从 `owner/tx_header[0]` 发起，最差 −5.967 ns。实际组合锥先做 12 位句柄匹配和 BR／LE 池选择，再进入 16 位长度比较，最后驱动 host_rx 句柄 RAM 的 WRE、bootstrap 计时 CE 等。远置 DDR 版本 `D2103114` 仍有同域 −4.080 ns；DDR hold 修复没有解决该业务组合路径。

维护源 `rtl/bluetooth/hci_owner/workstation_hci_flow_owner.sv` 现并行比较 ACL 长度与 BR／LE 上限，再用原有 LE／共享池条件选择一个比较结果；三处完整 12 位句柄等号改为 XOR 归约相等。没有增加寄存器、样本／命令延迟或更改状态机、信用、错误优先级与接口。未修改 native_transport、固件、候选配置或已封存候选。

## 对照与验证

冻结 fixture 是 W9b 实际消费的完整 flow_owner 原文件，SHA256 `8240975d4f1e119c86b7f5a0dd743f6db96dc67caa688c9992413a5a68e223e5`。测试只改其模块名以便双实例对照；没有手工转写旧算法。新维护源 SHA256 为 `51fb7a96487b4aa27fdf9fce38901c6ee3a5403ce29292bac51ab3c7901fa2c8`。

- 对全部 32 个公共输出、19 组内部标量和 8 个数组元素逐周期比较：118730 个时钟周期一致，包含既有 10000 步随机状态流程与信用／世代／生命周期场景。
- 独立池／句柄语义 oracle：两种池模式、两个句柄分别遍历完整 16 位长度域，再遍历完整 12 位句柄输入域，总计 270336 组。生产双句柄参数为 `HANDLE_SLOTS=2`，三种句柄查询均被检查。
- Z3 对 49 个自由比特的无符号池比较重排、24 个自由比特的完整句柄相等表达分别得到 UNSAT；不依赖具体容量／句柄值。
- 四个真实破坏负控全部被拒绝：选错池、LE 忽略共享池、漏掉句柄 bit0、错误拒绝 LE 上限相等边界。
- 既有 owner／event 回归通过：flow 116780 checks／15 场景／10000 随机步，event 9174 checks／1830 事件／1806 长度模式，11 个破坏负控全部被拒绝，严格 lint 通过。
- 完整既有 native 回归通过，未跳过前置或 UART：集成 268 checks／12 命令／3 分片，11 个破坏负控；UART8E1／H5 仿真完成 patch 253、bootstrap 4、hostreturns 10、notifications 3、reconnect 1。前置 host_rx／bootstrap 链和严格 lint 同时通过。这是实际 UART RTL 仿真，尚未实板。

首轮新增测试器在编译前发现预期端口数误写为 64，实际完整解析为 33 输入＋32 输出；修正期望值为 65 后，使用新 `hci-pool-compare-v2` 目录完成最终回归。没有为通过测试而改变 RTL 行为。

机器证据：[dual138k_hci_pool_compare_20261031.json](dual138k_hci_pool_compare_20261031.json)，SHA256 `c8692c702b84b49ed530a282c8bdd64f25efa9ff64115626b99da1e718726306`。完整独立验证位于 `/Users/sphenicidition/.cache/gw138k-dual-20261031/hci-pool-{compare-v2,owner-v1,native-v1}/`，原始验证 JSON 及其日志身份由机器证据引用。

## 后续边界

本阶段只确认源码功能等价和完整原生链路回归。新输入尚未准备、综合或 P&R；没有预记 LUT、时序或资源收益。必须更新所选 DEMO 源锁并生成新候选身份，再做全量物理验证。原 W9b／M10b 输入和物理证据不追改。本阶段未下载 SRAM、未写 Flash、未做硬件验收。
