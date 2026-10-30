# AE350 BLE 下载第二批：C 策略归属与完整线消息回归

日期：2026-10-31。父级为 `fd7625dc70fb85bd60ee7842a6e1f3aae1f5606c`，包含首批 C owner、原生 S1a mailbox 优化和独立探针工作。本批在相同显式 profile 的 revision 2 中，将 READ、ACK、combined ACK、resume 和 30 秒传输策略交给实际运行的 C。**这完成的是 BLE 短录音下载的业务边界，不代表 C01/C03 全部迁移或硬件验收完成。**

入口仍为 `custom138k-workstation-ae350-business-v1`，选择 `ae350_ble_business_owner_v2`。默认／accepted 的选择、vendor、25K、R00 API 和 DDR 分配不变；六份 profile 只刷新各自已列源码的当前哈希，非业务 profile 未启用新 owner。[接口说明](../rtl/bluetooth/cpu_owner/CONTRACT.md)和[本批 receipt](workstation_task_20261030/ae350_ble_download_parent.json)记录具体归属与证据。

## 实现边界

`ble_business_owner.c` 是唯一传输租约：OPEN 模式、transfer/object/session、confirmed offset、pending block 的真实 CRC、last ACK identity 和协商长度上限都在 C。READ 先检查当前模式、window-one、对齐、range 和 offset；ACK 在 C 比较实际 pending block；combined ACK 在下一范围有效且**物理 READ 实际启动**后才提交上一块 ACK。若 APB 接受 descriptor 后 link 已断，READ-admitted 为零，不能提交 ACK。CRC 不完整不能生成 pending block；已完成真实 CRC、随后数据面失败的路径保留旧协议语义。

全部 OPEN、CLOSE、CANCEL、ACK 由 C 直接处理，不再反送硬件作业务决策。显式 resume checkpoint 使用新的单调 transfer ID；C 用无符号 elapsed 差处理 32-bit wrap，在首次观察到 30 秒的 pump 过期租约。CPU 暂停不阻断音频和自主 seal，恢复后按已逝时间拒绝过期命令；不宣称业务服务在 CPU 停止时继续运行。

原生 parser 保留完整 32 槽请求字节比较和缓存回复。数据 replay 通过同一个 S1a slot 到 C，物理 service 只锁存 replay flag 和原 cached object，并镜像现有完整 ticket/owner/session/boot key。C 的有界 INSPECT 阶段必须匹配该完整键才能使用元数据。数据 replay 重建原 borrowed tag/模式，不能修改当前租约、confirmed/pending、时间或 ID；失效对象在 primitive 前拒绝。非数据精确 replay 保持原缓存路径。S1a ABI、reserved 字段和外部 wire 格式未变。

physical API 独立 ID 升为 `52434403`、caps `00301002`。新增 immutable flags 以及 actual CRC-complete、READ-admitted、CRC 和 admission-time facts；软件检查身份和保留位。physical engine 删除所有 transfer policy/cursor/ACK/timeout 状态，只接受 START/STOP/CLEAR 和通用 READ。断开／disable 为在途 READ 产生一次明确 completion，禁止晚到 DATA 和永久 busy。保留采集、四字节 PCM CRC、raw DDR、native drain/seal/fetch、Rice、transfer RAM 与 wire framing；受保护编码器、banks 和 frame-byte 代码继续逐字校验。没有 C 采样／编码循环。

R00 的 `f8040000`、object64、首个 64-KiB window 独立保留。BLE 继续使用第二个 64-KiB window、16,384 stereo frames、format-1 48 kHz；没有长录音、44.1-kHz BLE 格式、18-bit event 或新协议的隐含承诺。

## 实际离线验证

最终 `cosim-final-v1` 将实际 maintained C 与 APB CDC、父级优化后 S1a、parser、physical engine、raw DDR/native bridge 链接运行。1701 checks 分为：342 主路径、840 下载与重放、47 断链 admission、316 边界、13 uncertain SUBMIT、15 uncertain COMPLETE、15 实际 APB 撕裂观察、33 零帧以及四个 CRC 字节阶段各 20。136 条完整 WIRE/BLOCK 与锁定旧 RTL 逐字相同；未改写、排除或归一化响应字节。

扩展夹具实际录入 1024 stereo frames，覆盖所有模式长度边界、RAW／codec10／codec11、显式 resume 和 EOF CLOSE、错误 ACK／combined 原子性、较早缓存 READ 重放、失效对象拒绝、downgrade/reopen40、超时后的 raw replay、慢 CPU、elapsed wrap 和重连。15 个实际运行的 C 变异都被同一套行为测试拒绝，包括错误 ACK/combined CRC、提前提交 combined、忽略 confirmed offset、删除超时、replay 修改 cursor／跳过 object identity、忽略 extended limit、提交未启动 READ；保留首批六个任务／身份／uncertain 负控。

**测试时钟修正：**首批 C++ 的 `timeInc(1)` 在 Verilator `1ns/1ps` 精度下只推进 1 ps，使控制周期为 20 ps，memory 周期仍为 14 ns。首批 794 checks 及主线复跑是真实通过这一不利比率，不能解释为预期 20 ns:14 ns。扩展 4096-byte fetch 暴露其固定 control-cycle 预算不足；本批只把夹具 step 改为 1000 ps，原测试和全部新增测试在 20 ns:14 ns 重跑通过。未修改生产 raw store、硬件时钟、deadline 或 golden 字节。重连 HELLO 自带当前时间，夹具将输入 elapsed 置于真实下一毫秒边界的 65536；完整消息仍逐字比较。历史日志保持原样。

最终回归：accepted source 17、default firmware 10、recording API 1、callback closure 4、business source／实际 prepare tamper 8、profile 静态 6（另外 15 个须独立旧 candidate 的用例 skip）、clock 静态 3、Delay FIFO RTL 两时钟比／满深度／wrap／stall／reset 1。实际 source/staged tamper、retired owner 重新引入和 callback proof drift 均 fail closed。没有运行需 Gowin 的 clock STA 或 mapped-memory 测试。raw-DDR 独立回归沿用首批已封存证据；本批未改 raw-DDR 源码，最终联仿仍包含实际 raw-DDR。

## 固件与候选身份

统一 xPack GCC 15.2，实际 cold-ROM/ILM/DLM build、disassembly、stack-usage 和 callback target proof；未知间接调用仍拒绝。四个静态 MMIO adapter、唯一 firmware owner 及构造方式未变，新 `a138_record_data_request_facts` 的间接调用逐项审阅并绑定实际 RV32 JALR 指令。proof 绑定 73 个 actual sites、46 个 reachable functions 和全部实际输入。

| 项目 | 数值 |
| --- | --- |
| cold binary / text / initialized data / BSS | 29,808 / 29,792 / 16 / 608 B |
| boot ROM / ILM / DLM 容量 | 各 65,536 B |
| ILM runtime / DLM static span | 29,200 / 624 B |
| 保守调用链栈 / 保留栈 | 1,344 / 16,384 B |
| binary SHA256 | `a56f396fd8bacc8645d8bd51320190950dbb91287df9ef2aa5cfbbfd97d8a8cd` |
| ROM SHA256 | `98e8d2880f1109391e43a3e7babafd12e62d3a5b2b10730187294e66d2ed6b1a` |
| actual indirect proof SHA256 | `984660e286eca1dc2c01f384bd2211b5056caf6f6aa30927bd74696da9b3ebfa` |

默认 14,428-B 和 recording API 16,100-B 两个 16-KiB build 的 binary/ROM，与首批固定父级的对应输入逐字相同。新增 helper 保持在 `A138_BLE_BUSINESS` guard 内，非业务配置未引入 C owner。

最终 `prepare-final-v1` 固定 612 staged / 271 compiled，候选 `custom138k-workstation-ae350-business-v1-54e6f30a859dc9f7`，配置 SHA256 `7b1e10e64c4b139174c2c2545df08c26c1e10a32080f36c534b30ce45dc7e90b`。源码、实际 ELF/ROM、输入表、stdout/stderr、负控和 prepare 在外部 seal 目录；生成数据库不进入源码提交。

本批没有综合／P&R／板卡动作，也不宣称资源净减少、routed timing／全 CDC、CPU 性能／栈水位、实板 ILM/DLM/cache、实际音频 tap、Android、SRAM 或 Flash 验收。首批 C04 记录为资源净增，不能用“删除 RTL 策略”推断本批节省；仍须对本批完整同功能 candidate 单独综合对照。父级探针与 mailbox 证据不构成本批硬件验收。回退选择父级 revision-1 business source 或已有 no-panel profile／独立部署；不改变 accepted 身份或默认推广。
