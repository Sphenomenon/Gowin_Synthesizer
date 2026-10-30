# 媒体停止保持链的 Gowin 映射修复

日期：2026-10-30。离线阶段身份：`runtime-media-hold-fence-offline-v1-66606b57d7d90cc3`。机器证据：[runtime_media_hold_fence.json](workstation_task_20261030/runtime_media_hold_fence.json)。本报告封存 `workstation_runtime_media_stop_bridge.hold_compute` 的小范围产品修复、专门回归和独立综合映射；完整候选、P&R、实板和部署证据由后续候选另行记录。

## 问题与修改

revision 5 完整候选的 Gowin 综合虽然返回 0，却对 `media_stop/hold_compute` 报出 AG0100／AG0101，并在保持链上生成组合自反馈。其异步公共复位清零与异步 `hold_50` 置一要求相反，无法直接映射到同一触发器的单一异步控制。此前的 RTL 功能回归并不验证该技术映射，不能豁免这一结构缺陷。

修改只把这两位保持链统一为一个异步置位条件：`hold_assert = !reset_ni || hold_50`。公共复位或真实媒体停止均立即置为 `2'b11`，解除后必须经过两个实际 compute 上升沿，依次移入零。CPU-only `owner_reset_ni` 不参与保持条件；它仍只影响本地请求投递／重发，不撤销待处理的停止事务或后端保持。

公共复位期间及刚释放后的行为有意收紧：保持输出维持高电平，即使 compute 时钟未运行也不会提前放行。实际 `gw138k_controlled_services` 在第二个释放沿仍采样旧的高保持，因此该沿上的 REC START 被拒绝；后续沿才允许新开始。默认 `ENABLE=0` 的所有对外桥事件保持关闭。

| 来源 | SHA256 |
|---|---|
| 修改前完整 runtime owner | `73cae668f9b547dd3ab2ae236fb003f58114911e608663cafd962da69b74d051` |
| 修改后完整 runtime owner | `a78a29f86e2af6b8a74cef5dd9662d73a6afa5506861e63cb5ab29c9c323ae5b` |
| 提取的旧 bridge | `1a4a185af2fb420b23d538098c24fc0805c3080b8c87de75d6dfa6149761b976` |
| 提取的新 bridge | `7c16ef56ae24812b81f6119d6dfb9823d85343c504be6d454f21390dd670bdf0` |

专门测试从当前 owner 精确提取 bridge，按唯一锚点反向重建旧 bridge 并检查其固定 hash；没有修改 vendor／冻结基线或把复制项目变为新生产输入。先前 TF／BLE 阶段的身份和报告保持原样，不能把本修复重标为旧阶段输入。

## RTL 和实际门级检查

新增 runner `sim/services/run_media_hold_fence.py` 与 TB `tb_workstation_media_hold_fence.sv`，手动驱动 compute 边沿，让时钟真正停止；50 MHz 控制时钟持续运行。主桥为实际产品实现，REC_ENABLE 为实际唯一 owner。只有本地 completion、TF pending／terminal 和 physical quiet 是本单元的协议夹具；真实后端联动由下述独立联合回归覆盖。

RTL 与实际 Gowin VG＋官方 `gw5a/prim_sim.v` 均通过同一 8 项矩阵：

1. 公共复位异步保持、无 compute 边沿不得释放，以及两边沿释放。
2. 空闲 CPU-only 复位不改变保持输出。
3. 第二个公共复位释放沿上的真实 REC START 被挡住，释放后新开始成功。
4. compute 停止时媒体请求立即建立保持，且不制造本地／TF／terminal 事件。
5. CPU reset 阻止本地投递，恢复后重发同一未结束事务。
6. 本地完成、TF pending、TF terminal 夹具信号和 physical quiet 按顺序结束后才允许释放。
7. TF failure 仍有 pending 时保持和 readiness 围栏不解除，CPU reset 也不能撤销；真正清理后才释放。
8. 活动 hold 与公共复位重叠，复位释放后立即新请求也不会打开保持门。

两种实现的计数完全一致：8 cases、39 compute edges、3 local requests、2 TF requests、done1／failed1。默认关闭桥持续检查为零事件。Verilator 对主桥、实际服务与 TB 的 lint 为零 warnings，没有屏蔽 UNOPTFLAT 等结构诊断。

四个临时 RTL 副本负例均按指定断言拒绝：同步采样 hold、仅一边沿释放、把 CPU-only 复位接入 hold，以及旧的混合异步清零／置位实现。另把实际映射 VG 第二级 DFFPE 的 D 改接 GND，门级单边释放负例也被检测。所有负例只写新输出目录中的临时副本。

## 独立 Gowin 映射

微型综合的顶层仅包装原 bridge，并固定 `ENABLE=1`。原／新桥在 GW5AST-LV138PG484AC2/I1、device version C、GowinSynthesis V1.9.12 下均完成技术映射。运行时遵守 `/private/tmp/gw138k-build.lock`；本次最终回归复用已完成的 micro4 证据，逐字核对输入 bridge／wrapper、配置及来源 hash，没有并行启动第二个 EDA 进程。

| 检查 | 旧 bridge | 修复后 bridge |
|---|---:|---:|
| AG0100 | 6 | 0 |
| AG0101 | 2 | 0 |
| 实际 LUT 组合环 | 2 | 0 |
| hold_compute 实际端点 | 混合 DFFCE／DFFPE 与反馈 LUT | 恰好两个 DFFPE |

旧微型网表的两个 LUT3 `INIT=8'hE0` 均把自己的 F 接回 I0；reset=1、hold_50=0 时真值为 `F=I0`。这是实际条件自反馈。旧完整候选在额外板级 reset 表达式下形成 LUT4 `E000`，两种证据的 LUT 规模不混称。

新网表第一级 D 接 GND、第二级 D 接第一级 Q，第二级 Q 接实际 local_hold 输出，两个 CLK 均追溯到 compute_clk，CE 均为常高，PRESET 共用同一 LUT2 `INIT=4'hB`。其四行真值严格等于 `!reset_ni || hold_50`。官方 DFFPE 模型的默认 INIT=1、PRESET 异步置一；最终门级测试使用该官方模型，实际主 DUT 不是行为替身。为允许默认关闭桥同时保留 RTL，只对映射 bridge 的模块名和顶层实例类型做两处精确重命名，输入／输出及网表逻辑没有改变。

旧 VG SHA：`969944112285db6e32714041dc86dd7aa9990cd6cd621f519f1c0c6bdf2daaea`。新 VG SHA：`bbe65b421f296334878e8c7c1e65d57452e2dceda27564b435e5e094329ab166`。完整日志、VG、原语库及运行参数的 hash 在机器证据中。生成数据库和网表保留在 cache，没有加入版本源。

## 修复后的真实链路复跑

父级另行完整复跑两条实际 runtime 回归。本 runner 再逐项读取它们的 136／83 项实际输入，所有 hash 与各自证据一致，且 runtime owner 均为上述 `a78a29...`：

- `real-runtime-TF-BLE-media-offline-v1-8b930fa01216e91d`：10 场景／6 负例，140 physical＝140 observed，35 eligible＝35 BLE capture，TF done6／failed2，BLE done7／failed1。真实 FIFO、封存／CRC、TF ACK 返回与 I2S 最终帧仍由其实际 owner 完成；SD／有序 DDR／BLE 连接与已解析命令边界仍是该联合夹具的范围。
- `native-runtime-controlled-offline-v2-nonzero-64c63ae311fb249d`：非零 epoch、默认媒体策略；1078 physical＝1078 observed、977 非零帧、384 FFT bins、1077 APB 检查通过。

独立 reviewer 再次读取 runner／TB、审计 micro4 两份映射并完整复跑 RTL／mapped／五负例，阶段身份与最终 runner 完全一致。审阅输出和 hash 附于机器证据。

父级在另一全新输出目录独立执行同一完整命令，复用并重新核验微综合原始输入／产物，RTL／mapped 八项及五个负例全部通过，身份仍为 `66606b57d7d90cc3`；两份联合证据的 219 项实际输入同时重新读取。独立结果见 [runtime_media_hold_fence_parent.json](workstation_task_20261030/runtime_media_hold_fence_parent.json)。

## 复跑与边界

无需启动 EDA 的复跑：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/services/run_media_hold_fence.py \
  --output /Users/sphenicidition/.cache/gw138k-task-20261030/hold-fence-review-fresh \
  --gowin-original /Users/sphenicidition/.cache/gw138k-task-20261030/runtime-media-hold-fence-proposal-v1/micro4_original \
  --gowin-proposal /Users/sphenicidition/.cache/gw138k-task-20261030/runtime-media-hold-fence-proposal-v1/micro4_proposal
```

也可使用 `--gowin` 在非阻塞公共锁下重新做两份隔离综合；若已有 EDA 占锁即失败，不绕过锁。`--attach-verification` 可重复传入两份联合证据。输出目录必须全新，失败同样写 `verification.json`。最终完整命令及独立复跑参数在机器证据中。

本阶段证明了保持链的 RTL 语义、回归灵敏度和独立技术映射；官方门级功能模型不含 routed recovery／removal、亚稳态或物理时钟性质。整机综合、P&R、CDC／PLL／时序、功能保持和实板 acceptance 仍是分别的门禁；本阶段未烧写 SRAM／Flash，未产生已部署或硬件接受身份。回退应恢复上述旧 owner 的精确 source hash 并单独标记为结构阻塞输入，不能直接部署仍有组合反馈的旧结果。
