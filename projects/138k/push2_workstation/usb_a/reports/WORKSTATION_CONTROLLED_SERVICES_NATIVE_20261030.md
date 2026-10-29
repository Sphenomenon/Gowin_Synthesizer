# Controlled services 维护源码提取

2026-10-30。新增 `rtl/services/workstation_controlled_services.sv`，保留 module 名
`gw138k_controlled_services` 及所有端口、寄存器、复位和行为。该文件尚未被既有
top、profile 或 composition 输入选择；旧 builder 仍走原来的 baseline 加 overlay。
本阶段没有修改 frozen baseline、vendor、旧变换或源码选择。

## 来源与字节等价

来源是 `resource_rework_route0` 锁定的
`src/ae350/gw138k_controlled_services.sv`，再执行现有
`tools/workstation_resource_timing.py:services`（含 `services_writes`）后的实际输入。
本次仅复制这一个组件，没有复制工程。新文件为 LF、18,852 字节，未增加说明头、
重排代码或修改业务。完整出处见同目录的
`workstation_controlled_services.provenance.json`。

| 输入 | SHA256 |
| --- | --- |
| baseline 原始服务 | `f1e2abeb57c639882089c86e856aa86737468da4c040bb6800e53045a27a361d` |
| transform 结果／维护文件／实际 prepared 输入 | `bea3a6feb9397537a6e37f36d60f463b11e395178298c40c929f18d166f1a988` |

实际 prepared 对照来自 profile revision 2、candidate
`custom138k-workstation-v1-f5b723250388add5`。每次回归都从版本化 baseline 重建对照，
不需要私有历史目录；`--prepared-project` 另验证指定工程中的实际字节。
这证明来源和提取等价，不重新接受该历史 candidate，也不扩大其验证范围。

## 保留的 owner 与接口

- 服务运行于连续 compute/audio clock。命令 payload 在 `command_valid` 前必须
  至少稳定一拍供 predecode；现有 timing-adapted APB CDC 提供这个条件。
- 合法 `0x180` CPU event 写入保留 18-bit payload 和 ready 背压。非法事件、
  非法 strobes、普通寄存器和空录音读取均不阻塞整个 mailbox。
- 录音 enable 仍由该服务独占，外部 capture FIFO 供应 `{sequence,left32,right32}`。
  显式 POP 才锁存 96-bit 快照，RELEASE 才清除快照；不能直接重复 POP。
- score 仍是 256 条顺序上传的 `{absolute_frame32,key_mask32}` cue；保留时间单调、
  loaded/length、运行时禁止改写、start/stop、done sticky 和 panel toggle。
  真正的播放时基、LED 状态和 cue RAM 仍属于外部 score player。
- committed 参数、held notes 和事件计数保持输入观察态。服务不引入第二套参数、
  session 或音频调度。CPU 写入的 `0x1a8..0x1b4` snapshot 展示寄存器原样保留。

审计未发现必须在提取时改义的业务矛盾。现有 96-bit 录音包不含 rate、epoch 或 error，
score 使用 sample frame 时间；这些接口的未来率切换适配必须另有明确策略。
本次没有借提取增加寄存器或改变该约定。

## 验证

```sh
python3 projects/138k/push2_workstation/usb_a/sim/services/run_controlled_services.py
```

回归编译维护服务、由锁定 baseline 重建的真实 predecoded APB CDC、实际
`audio_capture_fifo`、`score_led_player` 和 `workstation_sdp`。APB 50 MHz 与
compute 76.8 MHz 异步运行。结果如下：

| 检查 | 结果 |
| --- | --- |
| baseline + 既有 transform 与维护源码逐字节比较 | 通过 |
| 实际 prepared 输入字节比较 | 通过 |
| APB 完成／服务提交 | 1,106／1,106，严格一次 |
| 合法 CPU event 背压及非法事件拒绝 | 仅 1 次合法提交 |
| snapshot 原子读、telemetry、非法 strobes/地址/值 | 通过 |
| 实际 capture FIFO 溢出／POP/RELEASE／空读错误 | 14 次 drop，sample 仍推进 |
| 实际 cue RAM 完整上传、单调性／满／busy guard | 256 次合法 cue 写入 |
| panel 录音与 score start/stop、实际 score 完成 | 16,384 sample frames 后完成 |

整个回归共观察 16,503 个 sample frames，score/录音操作没有生成额外 note event。
输入哈希在运行期间保持不变。Icarus 对原始 `always_*` 的 constant select 发出
19 条 sensitivity 扩展提示；编译和仿真均成功，源码字节与既有 prepared 输入一致。
精确输入、命令、日志 SHA256 和计数见
`workstation_task_20261030/controlled_services_native.json`。`git diff --check` 通过。

本阶段是源码提取与离线功能回归；未进行新的综合、P&R、SRAM、Flash 或板级验收。
既有 profile 没有选择该组件，也没有在本阶段重新声明整机 profile 验证成功。

## 接入与回退

未来显式 runtime profile 应只选择这份维护服务一次，并停用对应 staged overlay
作为该 profile 的编译输入；保持 APB CDC、18-bit lifecycle 公平 merge、score、
recorder 和性能快照壳。该选择需要单独的输入锁定、回归与新 candidate 身份。
旧 profile 和历史 builder 的来源策略继续保留。

在新策略完成前，该组件保持未选中。回退为继续使用原 overlay，或移除本阶段新增文件，
无需重建或修改冻结输入。

父级在新输出目录 `controlled-services-native-parent` 独立复跑，并额外对照 revision 3 prepared 的实际服务输入：逐字节一致，1,106 次 APB 完成/提交、256 cue、16,384 score frames 及录音满/背压检查均通过；全部运行输入哈希结束后再校验一致。机器记录保存独立验证文件身份。
