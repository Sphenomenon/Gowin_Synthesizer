# R00 下一组件阶段：独立 owner8 DDR 路径（2026-10-30）

本阶段新增默认未选择的 recording owner8 queues/core/native bridge，并让 PCM DDR 后端在离线 fixture 中通过该真实 owner8 路径运行。当前生产 profile、top、最终 PCM CDC、录音对象业务和 BLE 后备均未接入本组件；R00/R01/R02 仍未完成。原[后端首阶段](WORKSTATION_PCM_DDR_BACKEND_20261030.md)、[同拍命令修正](WORKSTATION_PCM_DDR_BACKEND_COMMAND_PRIORITY_20261030.md)及其 JSON 保留为旧输入证据，不能用旧身份代表本阶段。

## 输入与身份

实现基于 `48a7701016ce62e2d42e9cafa3295564a183d42a`。新增版本化源码位于 `rtl/memory/`，没有改动原 `rtl/timing/`、`rtl/music/`、baseline、vendor、构建来源策略或 profile 选择，也没有另建 builder、完整工程副本或生成式 RTL overlay。原 timing 文件仍通过不可变参考 `728eac7a9888ef617dec0c05a57a8ea24f3ec521` 的字节检查。

```text
native identity: native-recording-ddr-owner8-v1-b60a37ef38f7af32
native source_set_sha256: b60a37ef38f7af324972141c3f071d6a9249873d6e1576001fb252c649f7e26d
backend identity: native-pcm-ddr-backend-v3-756a17b50f33cf44
backend source_set_sha256: 756a17b50f33cf4434a07c626f42f584da620447c77ac3ee43509712a8714261
```

逐文件哈希、编译/运行命令、参数、完整日志、负控拒绝点及 lint 结果分别封存在[原生路径证据](workstation_task_20261030/recording_ddr_owner8_native.json)和[后端 v3 证据](workstation_task_20261030/pcm_ddr_backend_owner8_v3.json)。两组运行期间来源不变，封存后再次核验全部来源哈希匹配。原始 cache 分别为：

- `/Users/sphenicidition/.cache/gw138k-task-20261030/r00-owner8-native-seal-final2/verification.json`
- `/Users/sphenicidition/.cache/gw138k-task-20261030/r00-owner8-backend-seal-final2/verification.json`

## 实现边界

`workstation_recording_ddr_client_queues` 和 `workstation_recording_ddr_arbiter_pipeline` 的 `RECORDING_ENABLE` 默认0，关闭分支直接实例化原同名职责的 legacy 模块。该分支没有新 recording slot、owner/tag 宽度或公平寄存器。启用时仍复用原 `basic_pitch_ddr_client_slot`，owner0..7 的含义保持，recording 独占8；启用分支的 tag entry、reservation、command、response owner 扩为4 bit，grant 为9 bit。`TAG_BITS` 仍表示读返回 FIFO 的索引宽度，默认5对应32项，并非 owner 位宽。

路径明确分开三次接受：producer `valid&&ready` 只表示进入其本地 slot；`core_accept_o` 表示复制到共享 native command buffer；`native_accept_o` 取实际 `app_en` 和已存 `command_owner`，写还必须联合满足 `app_ready`/`app_write_ready`。返回 pulse 与256-bit 数据共同寄存，按实际读接受记录的 owner 路由，不用地址推断 owner。地址仍为32-bit native word，BL8=32 B、步长8；active-low mask 的1保留对应字节。唯一 DDR 地址图未在本阶段再次修改。

`workstation_recording_ddr_native_bridge` 只增加一个 submitted 位。首次本地 slot 接受后停止重复 enqueue；slot 空出、core 接受和用户 cancel/soft reset 均不能清除此位，只有真实 owner8 native 完成才回执后端。桥不复制 payload，源保持 valid/payload 至真实接受是接口契约；fixture 检查 payload 稳定，硬件不宣称能检测所有 payload 位变化。

core 对空返回账本或非法返回 owner 产生当拍及 sticky transport fault；3仅写，9..15未分配。桥对无 submitted 的 native 完成、以及 submitted 时源撤 valid，也在采样沿前组合报告故障并锁存。后端新增默认关闭的 `TRANSPORT_FAULT_ENABLE`，开启时在 CAPTURE、SEALING、READY/下载均可进入 failure9，并立即关闭新请求和输出。sticky fault 在终态仍阻止 clear/create，soft reset 不能恢复；必须共同复位 controller、slots、core/ledger、bridge 和 backend。

故障/取消不撤销已发布 command，不清 tag 或 accepted-read 账本，不伪造 quiet。已接受的旧读真实返回后被排空丢弃，未返回时禁止对象复用。优先级仍为 soft reset、cancel、fault，已有终态不被覆盖。独立取消用例分别把写/读命令卡在本地 slot 和 core buffer 后作废，随后要求该已发布命令恰好一次实际接受；被取消读仍返回并丢弃，期间 clear 不开放。

scan、music_turn、TF audio、display、delay 保持原高优先级结构。背景 recording 与 CPU/writer 轮转，recording 参与 music 的背景竞争判定；这不提供所有 client 的无界最坏服务期限，持续高优先级输入仍可饿死背景组。真实集成仍需定义突发/水位/期限，核验 D01/D04；后端 overflow/命令或返回 deadline 继续显式失败，采样不等待 DDR。

## 离线验证

原生路径共44项：33组正向配置、11个定向负控全部符合预期。`TAG_BITS=2/3/5`、seed=7/31/127 下，queues 与 standalone core（registered grants 0/1）分别检查默认关闭、开启但 owner8 空闲、owner8 活跃。默认/空闲模式逐拍对照所有 legacy 外部输出；开启模式用独立 per-client FIFO、masked memory 和返回 scoreboard，分别记录 slot/core/native 计数。默认 queues 的 core/native 诊断输出不可用时不会冒充真实内部边界，JSON 标明 `core_trace_available=false`；独立 scoreboard 仍观察真实 native 接口。

覆盖包含32个单独 active-low recording mask lane、canary、稀疏 mask、联合 native/write-ready 停顿、满 tag FIFO、wrap、连续/同拍 push-pop、BIST epoch 切换、reset和六组故障/bridge 用例。例如32项队列的 active wrapper 中，owner8 的 slot/core/native 均为655，原 music/NN owner5 均为707；全部client记账排空且内存/返回比对通过。这是合法 client 流量模型，不是完整 CNN 算法实例或任意流量证明。

11个原生路径负控分别破坏 owner8 tag 位宽、mask、三层接受区分、联合写接受、返回数据配对、非法/空 tag 当拍故障、bridge 唯一提交、bridge 过早回执、bridge 故障时延和默认 grant 路径，均在目标断言拒绝。关闭/开启两种参数的严格 Verilator lint 均零 warning。

后端共41项：28组正向配置、13个定向负控全部符合预期。48 kHz/44.1 kHz 均重跑真实采样周期、519帧有界前缀、完整64 KiB容量、尾 mask、故障、取消/reset及同拍命令优先级。竞争 fixture 现为 backend → native bridge → 新 owner8 queues/core → 独立 native memory，保留原 music/NN owner5 与其他 legacy client 并发请求，不再借用owner5承载录音。该 owner5 仍为合成的合法流量模型，没有实例化完整CNN计算算法。

新增 transport 矩阵在发布写、READY、延迟已接受读、最后预取输出四个阶段故障，覆盖当拍 admission/output 关闭、terminal sticky、soft reset 不恢复和共同 reset 恢复；默认关闭参数也单独验证。CASE7 注入真实 core 的空 ledger 返回，经 bridge 把故障送至 READY/download。CASE9 注入真实 bridge 的不可能完成，在 READY 无引用、持引用下载和末字节输出边界检查同拍封锁；延迟一拍的 bridge 负控被组合后端断言拒绝。CASE8 为精确控制本地/core stall，刻意只保留recording与CPU blocker；其他竞争配置要求包括owner5在内的全部client实际运行。

48 kHz有界竞争例中，158条录音命令的slot/core/native计数均为158，同时owner5完成26,424次请求；44.1 kHz对应owner5为28,756次。观察到的最大 command_wait 分别27/30 UI cycles，read_wait为11；这些仅是该有界fixture的观测值，不是全局保证。后端严格 Verilator lint 零 warning，当前来源检查 `test_current_workstation_sources.py` 10项通过。没有运行本阶段组件综合、P&R、JTAG、SRAM或Flash；不提供物理资源节省、硬件录音或生产接入结论。

## 后续选入与回滚

下一步必须由显式来源策略/profile revision登记新增依赖和唯一编译owner，先做同配置默认旧路径prepare比较，再接实际录音owner/最终PCM CDC、失败/重新启动策略和业务协议，重跑来源、mask/返回/取消/期限及物理时序/硬件验收。旧 timing 来源只能在这些验证完成后退役；当前 accepted/pinned 与 resource 候选选择没有改变。详细接口见[原生契约](../rtl/memory/RECORDING_DDR_NATIVE_CONTRACT.md)及[后端契约](../rtl/audio/PCM_DDR_BACKEND_CONTRACT.md)。

复现需使用不存在的output目录：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/tf_audio/run_workstation_recording_ddr_path.py \
  --output /tmp/workstation_recording_owner8_fresh
python3 projects/138k/push2_workstation/usb_a/sim/tf_audio/run_workstation_pcm_ddr_backend.py \
  --output /tmp/workstation_pcm_owner8_fresh
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
```

回滚本阶段时同时撤回新 native 三模块/契约/fixture/runner、后端可选 transport 接口与对应回归、以及本报告/新JSON；前阶段报告/证据与既有DDR分配继续保留。由于生产入口未选择本组件，回滚不需要改变已部署板卡或既有profile。
