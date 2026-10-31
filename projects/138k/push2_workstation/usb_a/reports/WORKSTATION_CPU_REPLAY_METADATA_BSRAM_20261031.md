# CPU业务重放元数据：有界BSRAM替换源码阶段

2026-10-31，基于 `525ead19b244145dbb33b0b4c260488b2f43c2fa` 的独立clone。
身份 `cpu-replay-metadata-bsram-v1`。本阶段无EDA、板卡操作或push；不能据源码容量预记CLS收益。
机器记录：`workstation_task_20261030/cpu_replay_metadata_bsram_source.json`。

## 目标与现状

最新task.md的C06允许共享短队列按净成本使用BSRAM，C04要求同功能完整资源核算。
真实CPU业务owner仍是 `ble_business_owner.c`；S1a邮箱仍只接已验证16B命令与64B结果。
邮箱512-bit并行结果和单周期APB不能直接改成同步RAM。本次不改它的ABI、owner或存储。
录音/下载engine的PCM后备、8KiB transfer四bank以及parser的请求/回复cache已经选择block，
再给它们增加RAM属性不能证明收益。

选中目标是 `cpu_owner/ble_protocol_command.v` 原有32槽重放表：
ID32、时间32、请求长度6、回复长度7，共77×32=2464bit。
native CPU适配层原来明确传 `CACHE_METADATA_RAM_STYLE="distributed_ram"`，
并以异步读在LOOKUP逐拍扫描。旧dated 09ae2f71真实VG中按原名至少可定位
32个cache_time RAM16SDP4、4个req_length RAM16SDP4及4个reply_length RAM16S4。
cache_id被优化重命名，未据名字缺失宣称它没有成本；这些历史命名统计仅证明目标存在，
不是本次同功能before资源结果，也不能换算为物理CLS。

## 实现

在原parser内复用 `workstation_sdp`：32bit ID、32bit时间、16bit长度包各一块，地址5bit。
长度包实际用13bit。native CPU适配改选block路径，原distributed参数路径继续可作为兼容选择。
没有增加请求槽、cache容量或业务owner，也没有DDR地址分配或wire报文变化。

SESSION同步预取slot0；每次LOOKUP比较当前槽，同时预取下一槽。
命中时锁存回复长度供后续完整请求字节比较使用。因此保留每槽一拍、原FSM状态和公共输出时序，
不通过多加等待拍改变60秒过期边界。新ID/时间/长度仍在原CRC末字发布边沿同时写入。
读只发生于SESSION/LOOKUP，写只发生于CRC，二者状态互斥；不存在同拍读写碰撞依赖。

RAM不清零，common reset或enable撤销仍清32个cache_valid及session状态。
有效位继续隔离旧/未初始化RAM；CPU observer reset保留原链路cache语义。
32bit时间使用完整无符号减法，保留回绕。接口、32槽满后替换顺序、ID重用、重放、
请求长度/字节冲突拒绝及过期行为均不改。录音采样没有新增CPU ready或存储背压。

## 实际校验

`sim/services/run_ble_replay_metadata.py` 用哈希固定的真实parent parser作为参考，
同时驱动真实新parser，比较每个公开输出及FSM状态；RAM字节按valid门控比较。
行为模型和官方GW5A SDPB各通过103617次半拍对照、11680个回复字节，32个slot全部命中。
覆盖全32槽替换/被淘汰ID、长度冲突与等长不同字节、59999/60000毫秒、
扫描期间跨过期边界、32bit时间回绕、disable/common reset旧RAM不可见、
LOOKUP slot17在途common reset和observer reset后原cache重放。
四个实际编译RTL负控（旧预取地址、忽略有效位、时间截16位、长度位错移）均被拒绝。
同拍metadata读写碰撞断言在两种真实RAM模型下均未触发。

既有完整C/APB/parser/raw-DDR回归继续通过1701项/12组检查、15个C负控；
136条WIRE/BLOCK消息与锁定legacy参考相等，录音、seal、fetch、codec和下载owner未换。
accepted来源17项通过；business来源四项非profile检查通过。
profile来源检查按预期拒绝旧CPU business锁，三个真实prepare选测未运行：
依父级要求保留base的source锁，交父级合入时统一刷新，不把该检查记为通过。

## 同功能资源比较准备与边界

输出 `cpu-shared-bsram-v1/final2/cell-comparison/{before,after}` 含实际parent/current parser，
相同engine/data-service/mailbox/SDP依赖、所有公开端口、相同16K帧/外部PCM/raw/seal配置，
50MHz SDC和仅run syn的Tcl。两个实际源闭包均用Icarus完成elaboration；未调用Gowin。
该组件对照用于验证metadata映射和增量，不能代替完整工作站C04。

下一步获父级EDA调度后，用这些独立目录测Logic/LUT/ALU/Register/RAM16/综合BSRAM，
要求新metadata实际为3个32/32/16bit SDPB、旁路读、同50MHz、5bit地址和完整byte写使能，
且无distributed metadata残留。若结果不降逻辑或净成本不合适，保留原参数路径回退。
整机需通过现有prepare入口以刷新后的source锁生成新身份，核对只有预期输入改变，
再计程序/数据/邮箱/桥/缓存总成本，做物理CLS/BSRAM、CDC与routed时序。
本阶段仅提供有行为证据的存储候选与可审阅对照输入，不声称已降CLS或已可部署。
