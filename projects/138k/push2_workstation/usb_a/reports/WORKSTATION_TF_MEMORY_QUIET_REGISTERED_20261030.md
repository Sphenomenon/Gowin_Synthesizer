# TF memory quiet 源域寄存与旧读排空边界（2026-10-30）

本阶段修复 `u_tf_audio` 返回 50 MHz 的 quiet 源：此前直接同步
`memory_gate && !memory_read_pending` 组合结果；现在先在 memory 时钟域寄存，
再进入原两级接收同步器。原命令 buffer、单在途有序读、关闸和 path restart
协议均保留。新增定向回归证明真实 command buffer 中尚未物理接受的旧读，以及
响应紧邻关闸边沿的旧读，均须返回后才能重启；新文件完整 PCM oracle 通过。

这是维护源码及离线验证阶段，不是 routed CDC、整机位流或实板验收。

## 来源与范围

- 唯一产品源码变化：`rtl/tf_audio/workstation_tf_runtime_service.sv`。
- 产品源 SHA-256：`c61e4cbdfa1b204cd95cf6d0d282feccb446c272ec716034fe07038ebc2604e2`。
- 回归身份：`native-tf-runtime-service-v3-e6c3af6a6d507320`。
- 回归输入集 SHA-256：`e6c3af6a6d50732066260418aac8ebf3689244dae41d1b561810e78851687bd2`。
- 机器证据：[tf_memory_quiet_registered.json](workstation_task_20261030/tf_memory_quiet_registered.json)。
- 完整本机日志：`/Users/sphenicidition/.cache/gw138k-task-20261030/tf-memory-quiet-v3`。

未修改 frozen baseline、vendor、旧 manifest 或既有 TF v2 历史报告。产品源改变
之后，revision 4 的旧 source lock／候选身份不再覆盖当前源；须由独立来源准备
阶段显式重新登记、准备并验证，不沿用 `41e653fe462e5ea3` 的接受结论。

## 读排空与 ACK

read pending 继续在服务端 `valid && ready && !write` 时置位；该 ready 可以是
真实一入口 command buffer 的接收 ACK，不能等同于物理 DDR 接收。唯一有序
`response` 消费后才清 pending。关闸后保留 response 返回通路，禁止新的接收。

quiet 寄存器在 common reset 时为 0。它只在 memory 上升沿采样已关闸且没有
在途读的状态；关闸和末次响应清 pending 后保守增加一个 memory 边沿，再经
两级 50 MHz 同步返回。这样 CDC 源是单一寄存器，避免 gate 和 pending 两个
源寄存器在同一边沿传播延迟不同时产生组合 ACK。超时仍只报告失败，不伪造 quiet。

## 定向覆盖与结果

执行：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/tf_audio/run_workstation_tf_runtime_service.py --output /Users/sphenicidition/.cache/gw138k-task-20261030/tf-memory-quiet-v3
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
```

| 检查 | direct | 真实 command buffer |
|---|---:|---:|
| 业务用例 | 22 | 22 |
| 真实输出 PCM 帧 | 677 | 677 |
| analysis PCM／暂停零帧 | 128／6 | 128／6 |
| DDR 写／读 | 270／234 | 270／234 |
| 关闸且读 pending 的 memory 周期 | 121 | 153 |
| 源寄存器逐沿检查 | 116,900 | 120,442 |
| quiet 源有效变化 | 92 | 92 |
| 强制队列驻留后关闸的排空用例 | 不适用 | 2 |
| 响应与关闸相邻边沿用例 | 1 | 1 |
| 独立取消读排空用例 | 1 | 1 |
| 原 scope 输出逐周期等价检查 | 58,321 | 60,092 |

两个强制队列用例分别发 restart 和 cancel：先让实际 command buffer 接收读，
保持下游不 ready；发控制并等待 gate 后，连续 12 个 memory 周期检查 pending
保持、quiet 为假、物理读未接收且没有 path restart。随后才放行 DDR，并继续
扣住已生成的旧响应至少 6 周期；返回后才允许 quiet。取消不能偷偷重启，新显式
文件启动后用不同文件的 64 帧数值和实际率检查，阻止旧数据冒认为新文件首拍。

相邻边沿用例让旧 response 在 gate 置位同沿产生，下一 memory 沿消费；此时
pending 清零但 quiet 仍为 0，再下一沿 quiet 才为 1。所有 path restart 均要求
pending=0、gate=1、源 quiet=1 和 50 MHz quiet=1。持续检查还禁止 quiet 在
memory 上升沿之间改变。

负对照只在临时输出中恢复旧组合 quiet；相同真实 path TB 在 **785.001 ns**
以 `quiet aggregate was not registered in memory domain` 拒绝它。维护源码
未被负对照修改，运行前后全部输入 hash 保持。
该负对照检出源寄存的逐沿关系，不模拟门延迟毛刺、亚稳态或物理 CDC 行为。

默认 path 精确逆适配与 immutable baseline 字节一致，双真实 path 对照的
128 帧／12,531 个周期通过；原 scope 的精确逆适配同样通过。
`test_current_workstation_sources.py` 的 10 项检查通过，`git diff --check` 通过。

## 限制和回退

DDR 模型保持唯一在途、有序响应；此修复不提供事务 tag，不覆盖独立 memory
reset 后旧响应迟到、外部 arbiter owner 丢失或响应重排。quiet 不证明已确认写
命令物理完成，也不提升 EOF 为成功完成或物理 drained。SD/FAT 仍为字节边界
fixture；未证明 TF 长流迁移、实际卡时序或硬件路径。

本阶段未修改配置、DDR 分配、event 布局、采样调度或 PLL 方案，未执行 EDA、
JTAG、SRAM、Flash 或实板操作。后续必须以新锁、新完整输入身份重新准备并完成
整机 CDC／时序与硬件验证。回退使用既有已登记候选及其原始输入；不得把本源
的变化写回冻结基线，或将旧候选验收套用于当前源。

父级以 `tf-memory-quiet-parent-final` 新输出目录独立重跑全部回归，输入集身份、direct／buffer／默认参考 metrics 与子代理完全相同；组合负对照也被拒绝，所有输入 hash 重新核对通过。父级另重跑 current-workstation 10 项来源检查并通过。没有将这次源码修复回填到 revision4 的旧候选或综合网表。
