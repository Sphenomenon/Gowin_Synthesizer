# TF byte FIFO clear 协议只读审查（2026-10-30）

当前 runtime TF 的四个 byte FIFO Gray 路径不能仅凭普通单步 Gray 约束获得
restart 接受结论。clear 会把非零指针多位跳到零；清零没有显式完成 ACK，且
memory 时钟在 quiet ACK 后暂停再恢复时，入口会早于 DMA restart 完成重开。
真实 direct／command-buffer 两种接线都观察到旧 DMA byte 被写入已清零的
playback FIFO。后续 WAV 解析器重新找到 RIFF，64 帧 PCM oracle 仍通过；
本报告只宣称确定的旧 byte 污染与协议隔离缺口，不宣称输出 PCM 已经错误。

这是未修改产品 RTL 的审查与 cache 探针证据，不能用于物理接受。

## 已选来源与实际协议

| 源 | SHA-256 |
|---|---|
| `rtl/tf_audio/workstation_tf_runtime_service.sv` | `c61e4cbdfa1b204cd95cf6d0d282feccb446c272ec716034fe07038ebc2604e2` |
| `rtl/tf_audio/storage/tf_audio_ddr_path.v` | `19506c0871ad394dcfa7332ec4bbdee410fa6dded26bad607c146f0024cd6030` |
| `rtl/tf_audio/storage/tf_audio_ddr_dma.v` | `ac90bd9a06eea44162727169de24e887196b5746fbc29467e299caf9a66aa911` |
| `rtl/tf_audio/storage/tf_async_byte_fifo.v` | `e9a7c01f7e5a13569de361b4615099f56706e4bcb93701005938639b45c28148` |
| `rtl/display_data/tf_audio_ddr_command_buffer.sv` | `c4b4a3e2ad17a50e2a59091d9f93f7c368c33c89956cd4d048734a3ef1f1f552` |

runtime service 显式选择 `NATIVE_RESTART_HOLD=1`，path 的 source 为 50 MHz，
memory 为 100 MHz。native hold 使 DMA mem_ready 为假、capture FIFO 对 DMA
呈 empty、playback FIFO 对 DMA 呈 full；已接收读响应继续返回。service 先等
已接收的唯一有序读响应及帧桥 quiet，然后发 path_restart，固定等待十二个
source 边沿，撤销 memory_stop，最后等 gate-open 返回。该 quiet 不包括 DMA
私有 read_buf、FIFO clear、指针同步流水线或 DMA restart_seen。

path 的 `soft_restart = restart边沿 || track_change || reader_fault`，会在本地
重置 decoder/playback，并翻转 restart_toggle。track_index 目前由 service
直接传入；因此外部换曲及 reader_fault 可在受控 path_restart 之前启动 clear。
capture_switch_hold 根据 reader playing 的低→高生命周期释放，不是 FIFO ACK。

两个 FIFO 共用该 toggle：capture 的 write／read 域为 source／memory，playback
为 memory／source。每域只有 clear_meta 和 clear_seen；检测两者不等时，本地
binary／Gray 指针、接收的远端 Gray 两级寄存器和 read valid 立即归零，clear_seen
更新。**clear_meta 第一同步级直接扇出到功能比较／清零选择**；memory 域没有
额外 clear_sync 资格级。seen 没有端口，path/service 也不检查它，因而没有协议 ACK。

四组接收 Gray 第一级 D 由综合器映射为 `Gray AND (clear_meta XNOR clear_seen)`
的 LUT3。这是同步逻辑 clear 的实际输入选择，不是跳零隔离证明；非 unit 的
pointer clear 与普通逐字节 +1 必须分别论证。

## 被动探针与暂停时钟实证

reproducer 为本机 cache 脚本与生成 TB，使用真实维护 path、DMA、FIFO、WAV 和
实际 command buffer，仅增加时钟暂停控制与层次观察；产品文件没有改动：

```sh
python3 /Users/sphenicidition/.cache/gw138k-task-20261030/tf-byte-clear-audit-v2/run_normal_probe.py
python3 /Users/sphenicidition/.cache/gw138k-task-20261030/tf-byte-clear-audit-v2/run_probe.py
```

机器证据：[tf_byte_clear_protocol_audit.json](workstation_task_20261030/tf_byte_clear_protocol_audit.json)。
完整 compile argv、探针和脚本 hash、log 均保存在 JSON 与该 cache 目录。

普通 22 用例仍各自完成 677 帧 PCM；每组发生 43 次 clear：

| Gray 来源组 | 指针归零前多于一位为 1 的次数 | clear 同沿本地 en／valid 活动次数 |
|---|---:|---:|
| capture write，source | 26 | 0 |
| capture read，memory | 26 | 0 |
| playback write，memory | 23 | 1 |
| playback read，source | 22 | 0 |

两条 memory clear-group 的 gate 尚未置位计数为 direct 28、buffer 26，分别等于
14／13 个事件各计两组；这是 hold-before-clear 证明缺失的观察，不把每项计数
当作独立输出故障。理想同沿 FIFO clear 优先可吞掉同沿旧写；不能据此推导不同
同步链／物理延迟下的隔离。

暂停用例在同曲重启时先让 read_buf 持有旧响应剩余 byte，等真实 quiet ACK 和
path_restart，再暂停 memory 30 个 source 周期。source 的固定 settle 已完成后
才恢复 memory。结果：

| 事件 | direct | 实际 command buffer |
|---|---:|---:|
| 暂停时旧 read_buf 剩余 byte | 29 | 28 |
| memory FIFO clear | 11,355 ns | 11,415 ns |
| gate 已开而 DMA restart_seen 仍旧 | 11,360 ns | 11,420 ns |
| DMA restart 同沿旧 byte 写入 FIFO 地址 0 | 11,365 ns，`0x46` | 11,425 ns，`0x24` |

gate 在恢复的第二个 memory 边沿打开，FIFO clear 也在该沿发生；DMA 的 meta、
sync、seen 检测在第三沿才处理 restart。在第二／三沿之间旧 read_buf 的 emit
重新变真，第三沿 playback FIFO 已离开 clear 分支，遂将旧 byte 写入新零地址。
DMA 同沿清自己的缓冲不能撤销该 FIFO 写入。其后新文件仍输出正确 64 帧，这
恰好说明普通 PCM oracle 无法替代 clear 隔离检查。

PCM/analysis 准入由 service state／invalidate 控制，受控 QUIESCE 和
RESTART_SETTLE 不向 bridge 或 analysis 接受旧 PCM；decoder/playback 的本地
soft_restart 会更早清状态。但这些屏蔽不提供 byte 指针完成 ACK，也不阻止上述
新清零 FIFO 接收旧 byte。compute 停钟、memory 停钟、reader 自动故障和两次
toggle 合并仍需独立事务证明。

## 后续最小边界与验证计划

需要显式 hold／drain／clear／ACK／release 协议，不能增加固定 source 拍数：

1. 在 service 保存 pending track，只有受控 restart 时才提交给 path；reader
   fault 先关闭两域准入，不能绕过握手直接翻转 runtime clear。
2. accepted DDR read response 先真实 drain；同时停止 source capture／decoder
   准入和 DMA 读写，处理已注册 FIFO 请求、valid 与私有缓冲。
3. 向 FIFO 四域及 DMA 发布一个保持的 clear/restart 请求。first stage 只进入
   第二同步级，不扇出功能逻辑；各本地域确认零指针、无 rd_valid 和同步流水线
   settle 后才回 ACK。DMA 自己确认清掉私有 read_buf、write_buf 和等待状态。
4. service 收齐四个 FIFO ACK 与 DMA ACK 才释放，memory 停钟必须保持 busy／
   gate，不因 source 时间经过而重开。释放也须本地域资格确认。

若采用独立 runtime FIFO，应从上述原第一方 FIFO SHA 迁移并记录 provenance；
该文件与 `resource_rework_route0` baseline 完全相同。当前维护 DMA 的 SHA 为
`ac90...a911`，**不同于** baseline DMA `2470b63c24812d8e4d00d93e8a1f30e8f97232e1e14a9dc5bf6265c3155ee6bf`，
新 runtime DMA 必须明确从当前维护版本继承，不能把两个来源混称一致。
只在 runtime opt-in path 选择新唯一命名模块；保留默认／冻结 baseline 字节、
DDR 分配和命令顺序。新增源码／profile 锁由独立来源阶段重新登记。

定向回归至少覆盖四指针多位跳零、各相位与 stopped-high/low memory、hold 前后
单 byte 在途 valid、DDR read 延迟、真实 command buffer queued-read、外部换曲／
reader fault／重复 restart／取消、analysis backpressure、clock stop 时超时仍不
释放，以及新文件第一个 byte、完整 PCM 与 generation。旧实现应在明确的 ACK／
无旧写不变量处被拒绝，不依赖 WAV 是否偶然重同步。最后才做新网表 FF 识别、
Gray flight/skew、保持数据及 routed reset／CDC 验证。

## 独立固定输入复现

父级从 `26a93f7` 提取全部参与编译的维护源到独立 cache snapshot，避免随后正在修改的 live 产品源码覆盖缺陷证据；四个 WAV fixture、实际 DDR 地址头文件、生成探针和 legacy scope reference 均记录并校验哈希。普通与暂停两项各跑 direct／command-buffer，共四次，全部 AUDIT／PASS 行逐项等于上述子代理证据。记录见 [父级复现](workstation_task_20261030/tf_byte_clear_protocol_parent.json)。这确认的是该固定输入的缺陷；新 clear 握手修复必须另行验证与登记，不继承本报告结论。
