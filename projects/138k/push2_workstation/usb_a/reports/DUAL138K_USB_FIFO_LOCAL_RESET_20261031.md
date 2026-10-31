# 双 138K：USB FIFO 生产端本域复位释放

2026-10-31。M7／M8 的真实 recovery 违例从 audio 域 `queue_release_5` 到 USB FIFO 生产指针 CLEAR；严格 DDR hold 远区域复验后仍有 −0.515 ns。该修改保留异步断言，使生产状态只在真实 USB 时钟上释放，没有增加指向真实指针的 false path，没有改变时钟或放宽 recovery／removal。

维护 RTL `rtl/workstation/workstation_fifo_write_reset.sv` 提供两拍 USB 本域 release；DEMO prepare 显式选择 `demo_usb_fifo_producer_local_release_v1`。旧 resource timing、accepted／pinned、hotplug 及默认关闭路径不调用新适配器；默认生成 FIFO SHA256 仍为 `2084bead34bf421610fd20489ece66601823b87f72887228be25de5374a956c6`，逐字节不变。冻结 baseline 和原 `event_fifo()` 均未修改。

新 M／W 配置必须声明 `usb_fifo_reset_policy=demo_usb_fifo_producer_local_release_v1`，prepare／profile 封存／实际综合门均据此强制新 metadata、唯一维护源和真实 reset gate。旧 M7／W7 的无字段封存回放已分别验证通过，只允许原 FIFO hash、无新维护源且无新 metadata；不能删除新配置字段或伪造 policy／metadata／语义／验收字段来套用旧路径。

新 `tools/workstation_usb_fifo_reset.py` 固定该输入 hash，并通过五个精确唯一 anchors 改写四组 USB 写状态的复位与一个写准入表达式。封存验证逐项逆变换后重算原 hash，因此音频 `rst_cdc`、Gray 指针、存储、读输出缓冲、owner 的 audio 六边沿 hold＋六边沿 drain 等其余全部字节必须不变。`w_rdy` 在本域释放前保持低，防止未真正写入的请求被当作已接受。生成适配仅用于现有冻结 FIFO；退出条件为维护原生 FIFO 独立证明相同存储、读缓冲、Gray 和取消语义，不能逐渐扩展为新的业务生成器。

真实 Gowin 小综合通过。实际二进制生产指针 7 FF、Gray 生产指针 6 FF 共 13 个真实 FF 的 CLEAR 均来自新模块 USB 末级 release；Gray MSB 仍是原二进制别名。原 `consume_w_bin`／`w_level` 两组未消费诊断在旧、新实际编译中均被消除；源码仍只改上述四组，不借此宣称资源收益。实际门分别验证两拍／USB 时钟／异步断言／首级单消费者、末级复位真值表、实际写准入及原两级 audio reset。写准入绑定唯一真实 packet memory 的 CEA（16 组前沿真值），再证明 producer bit0 的有效 next-Q 恰等于 old-Q XOR 该 CEA（4 组真值）；不依赖会被完整候选优化吸收／改名的 `w_rdy` 端口。完整候选的 input FIFO 审计继续独立核对真实 USB／audio 时钟、原存储及 Gray CDC。

`sim/usb2/run_workstation_usb_fifo_local_reset.py` 使用真实生成 FIFO、维护 owner／MMIO adapter／session 和已有 prepare 的只读支持。门禁通过：

- 实际停 USB、停 audio、双钟停转的三次重复边界；六次异步断言、精确两 USB 边沿释放、四次新数据传输。
- 真实 owner 六边沿 hold／六边沿 drain、停 audio 热插拔、PANIC、重复边界及首个新写的真实指针／缓冲回环；并行 legacy 对照仍复现旧 RAM 重放。
- 单边沿 release 和同步断言两个 RTL 负控分别在对应 oracle 失败；实际 VG 的生产复位旁路、生产时钟错误、release 时钟错误、release 级联短路及 packet CEA 绕过 release 五个负控全部拒绝。
- 六项策略／配置／封存漂移测试（含缺失与伪造字段等子负控）、22 项 DEMO 策略／审计回归和 17 项 accepted source-boundary 回归通过，`git diff --check` 通过。

[完整门禁证据](dual138k_usb_fifo_local_reset_20261031.json) 来自 `/tmp/dual138k-usb-fifo-local-gate-v4/verification.json`，实际综合和仿真日志保留在该目录；证据另附旧完整 W7 的实际 pointer／诊断寄存器清单及配置测试／旧封存回放结果。失败 v1 记录保留：独立 fixture 一度省略 owner 的六 audio 边沿 hold，复现原冻结 FIFO 的读指针／reset 延迟差；恢复既有明确合同后通过，没有为新修复更改音频清空逻辑。

这些证据证明源实现、独立实际综合和针对性仿真；完整 M／W 新综合网表、完整 P&R recovery／removal、SRAM／实板仍需后续证据。没有硬件验收或下载声明，板卡状态未改变。
