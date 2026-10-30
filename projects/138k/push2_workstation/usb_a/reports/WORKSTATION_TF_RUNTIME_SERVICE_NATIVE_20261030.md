# TF 原生服务：真实 DDR/WAV 路径联合验证（2026-10-30）

本阶段增加显式选择的 `workstation_tf_runtime_service`，把真实
`tf_audio_ddr_path`、原 reader／DDR DMA／byte FIFO／WAV decoder 与已提交的
85-bit 帧桥接在同一所属服务内。实现手动输出模式、文件率不匹配失败、暂停保位、
取消清流和显式恢复，不自动请求第二路 clock，不重采样。旧 bridge、top、profile、
playlist、识别模块和 DDR 地址分配均未改选；这不是 F04、A03、A06 或 M01/M03 整项验收。

来源身份 `native-tf-runtime-service-v2-e8d01cae0e615a71`（完整闭包哈希，不复用前序仅 service 的调试身份）：

| 输入 | SHA256 |
|---|---|
| 原生 service | `a359be17c8767932f967d6c53cb3c93faa3edb22c2e82c6c9281cb8feadf5179` |
| opt-in path | `19506c0871ad394dcfa7332ec4bbdee410fa6dded26bad607c146f0024cd6030` |
| 不可变 baseline 原 path | `ebbf714a3e1670378fcdfce7b9eae34b6841ae82be37c0e5d7bccf5dd176291f` |
| scope restart provenance | `65aec658fc5b8209555a3ef4b8188112fe399fb100c07c289ff87349e906d337` |
| 本阶段 JSON | `e011ba584d95d877f96002696a356a5577345182c6f928ffa6bccc9443b86fa1` |

完整输入、命令、原始日志哈希、辅助回归和回滚范围在
[机器记录](workstation_task_20261030/tf_runtime_service_native.json)。接口及接线限制见
[所属合同](../rtl/tf_audio/WORKSTATION_TF_RUNTIME_SERVICE_CONTRACT.md)。输出目录为
`/Users/sphenicidition/.cache/gw138k-task-20261030/tf-runtime-service-v16`；编译产物和数据
模型均留在 cache，没有进入源码变更。

## 行为和真实路径中发现的问题

50-MHz 文件拥有者在显式 restart／新 track 时登记 runtime 的实际 rate/epoch，
epoch 是不透明标签，回归包括 0。待真实文件格式确认后才向 compute 授权 route。
不同率、unsupported、DDR fault、card-lost、runtime invalid/fault/busy、已登记流变更、
transport error 均终止当前文件，发一次 generation invalidate 并保持 quiesce。
自动 reader retry 和卡返回不会重新准入失败文件。

后续整机接线审查发现旧 `scope_tf_transport.restart_o` 混合显式用户启动与自动卡返回，
`cancel_analysis_o` 又在进入 TF 时与 restart 同拍。直接接到新 service 会取消首次
进入，或在卡返回时重启失败对象。因此仅在 scope 末尾添加 `explicit_restart_o`
和 `file_cancel_o`：前者标记原用户命令／有效 TF song 请求，后者仅在退出 TF 置位。
所有旧输出与不可变参考逐拍一致；新的 top 尚由后续显式候选接入。

run 下降沿保留 decoder 与桥位置。暂停 ACK 之后不再接受／消费文件 PCM，物理
route 供应明确静音，媒体 busy 继续阻止换率；恢复后逐帧继续，没有跳过已排队数据。
识别与 TF 播放保持互斥，识别 ready 不影响 TF 播放；识别仍从原 path 接受真实
PCM/文件率，并保留 enable/hold/ready 与 capture-on-analysis 语义。

真实联合回归暴露了旧 byte FIFO clear 和 DMA restart 的先后竞态：重启后 DMA
可能等待一条已被 FIFO clear 丢掉的返回。曾尝试局部 reset memory-side DMA/FIFO，
但保留的 capture_done_toggle 会被误当新 EOF，进而遗漏末尾 partial beat；此方案
已删除，没有作为实现留下。

最终只在原 path 末尾增加默认关闭的参数和端口。显式服务启用 hold：先在 memory
域同步阻止新的命令/FIFO 工作，继续接收已接受的读响应；读响应排空和帧桥 quiet
均确认后才 pulse 原 path restart，保持十二个源时钟边沿，随后经同步解除和返回
证明释放读取。分析重启也使用同一边界。原 reader、DMA 状态机、byte FIFO 字节和
地址分配未修改。已接受的读不会被新文件重解释；写命令顺序仍依赖既有 command buffer。

## 离线验证

运行：

```text
python3 projects/138k/push2_workstation/usb_a/sim/tf_audio/run_workstation_tf_runtime_service.py --output <新目录>
```

真实原 path／DMA／byte FIFO／WAV decoder／85-bit 桥与 scope 联合回归，direct 和真实
`tf_audio_ddr_command_buffer` 两种配置各通过 19 个场景：

- 每种配置各 485 个实际文件 PCM 交付；双率完整文件与暂停前后逐帧 golden 对照。
- 暂停期间 6 个明确静音帧，源 accepted 数、消费位置、generation 均保持。
- 识别两次完整重启共 128 个真实 PCM，hold 背压与模式互斥正确。
- 每种配置有界 DDR 模型实际写 210 次、读 201 次；取消期间分别有 82／83 个 memory 周期等待已接受读，
  包含额外 80-cycle 延迟跨重启，断言所有 path restart 都在读已排空且 hold 有效之后。
- 每种配置 11 次失败终态；direct／buffer 分别 42／43 次 invalidate；覆盖实际 rate mismatch、32 kHz、坏 WAV 格式、
  DDR 容量 fault 注入、拔卡、runtime 失效、流代次变化、transport 错误与 quiet 超时。
- 取消后源立即停高／停低各一次；旧 route 不再有效，compute 可证明桥已清流，
  源域 ACK 必须等源恢复。计算域停钟触发终态超时且 busy 不提前释放，恢复后真实 ACK 解除。
- EOF 保留尾帧与 busy，不把源结束当作物理 drained 或文件成功完成。
- 实际 buffer 有 411 次先于下游接受的上游 ACK，4,620 个下游停顿周期；完整文件
  包含末尾 12-byte partial beat，旧写按顺序先于新文件写，读从早期 ACK 到真实响应
  均被 pending 覆盖。两种配置都功能通过，保持既有 buffer 用于保全时序边界。
- 真实 scope 首入 TF、用户 restart、拔卡返回及退出各按合同接线；显式 restart
  共三次、自动卡返回一次，自动事件不重 arm 失败文件。旧输出与冻结参考分别
  44,520／45,978 次逐拍比较一致。

默认参数 0 的 path 从 `resource_rework_route0` 不可变对象精确重建原字节。
除末尾参数／端口及三条恒等折叠表达式外不允许任何差异；双真实 path 用相同 DDR
响应逐拍比较全部列出的 PCM、格式／状态和 DDR 接口，两个实际率共 128 帧、12,531
次比较通过。新端口在默认实例中持续变化，默认行为仍与原参考一致。

scope 移除精确新增输出语句后也与不可变原字节相同，原 SHA 为
`d649b7d52cf39ec2bf28da3a0d54925a2ca4a953f3f03e39f0b3f0c0d12f4a50`。
附加回归通过：`test_current_workstation_sources.py` 10 项；旧 scope transport 21 条
断言／10 次 restart；旧 MP3 path、FLAC path 和 DDR DMA 各一项。编译只有旧模块／
冻结参考未声明 timescale 的继承提示，没有新模块编译警告。
最终所有 runner 输入哈希在运行前后保持。

父级使用 `tf-runtime-service-parent-buffer-scope` 独立重跑同一冻结闭包，direct／真实 buffer 两组各 19 场景、485 PCM 与默认 path 对照全过；运行前后输入哈希一致，父级证据已纳入机器记录。

## 仍未覆盖及交付边界

SD/FAT 在本回归使用 byte-boundary reader fixture，DDR 为有序、有界真实数据模型；
没有仿真实体卡的 SPI/FAT 事务或证明物理 DDR 服务时限。DDR 容量异常在真实 producer
寄存器处注入，没有生成 4 GiB 文件。没有完整 top/profile、CDC 物理约束、综合、P&R、
JTAG、SRAM、Flash 或硬件验收。本服务仍使用原 DDR 播放中转，M03 尚未迁移。

EOF 只有 `eof_seen`；尚无有序 EOS 和最后物理帧完成协议，尾帧耗尽可触发 runtime
既有 underrun，必须由显式取消／退出结束 busy。没有成功完成声明。failure 状态尚未
进入正式 CPU MMIO；全局复位和独立 DDR 恢复时外部 arbiter 的旧响应清理仍须整机验证。

后续接回须保持现 `tf_audio_ddr_command_buffer` 与原 owner，连接新的 compute TF
接口、两个域的 quiet/busy 和 50-MHz runtime 状态；明确区分用户 TF restart 与自动
reader retry。旧 profile 继续使用未改选的旧 bridge；只有新候选登记本阶段源码哈希。
回滚仅撤销该阶段的 service/path opt-in 适配和测试；没有部署操作需要回滚。
