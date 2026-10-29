# C01／A06 原生音频时钟命令服务离线检查点

日期：2026-10-30。新增 native `workstation_audio_clock_service`，仅为
内部可选 page-local 命令服务。**未分配绝对 APB 地址，未改旧 services、
顶层、profile 或固件，没有进行综合／P&R／板测／SRAM／Flash。**
C01 与 A06 的整机任务仍未完成。

源码与契约：

- `rtl/services/workstation_audio_clock_service.sv`
- `rtl/services/AUDIO_CLOCK_SERVICE_CONTRACT.md`
- `sim/services/tb_workstation_audio_clock_service.sv`
- `sim/services/run_audio_clock_service.py`
- 机器证据：`reports/workstation_task_20261030/audio_clock_service.json`

## 实现与边界

服务运行在常开 50 MHz 域，复用真实 `gw138k_apb_cdc` 一拍本地预解码
接口。唯一可写寄存器只允许 48 kHz／44.1 kHz／恢复三个操作，合法提交
分配 command ID 并发出一次寄存请求；最多一个在途，不排队。APB 只等待
本地接收或拒绝，不等待音频切换。busy、无许可、非法地址／值／strobe、
只读写、未重新就绪或 DSP fault 等均返回错误。

本地准入、硬件接受、应用成功与失败分别保存。注册请求后的真实 core
rejected／runtime policy rejected／failed 都产生失败结果。同率请求
支持 core accepted+applied 同拍；其他 applied 必须在接受以后，且与实际
rate、epoch、valid 和 fault 一致。启动旧 applied 与无 owner 迟到结果只
计数，不产生成功。

现有切换核心的 recover 分支没有 accepted 脉冲，本服务用恢复请求后
真实 `busy && !fault` 起跳作为硬件接受证据。回归直接实例化未修改的
`workstation_sample_rate_switch`，并断言整个恢复中没有普通 accepted
脉冲；并非用构造的可行波形代替此证明。

接受／应用分别有界超时。超时或应用上下文错配会结束 pending，置关联
锁定，后续命令立即拒绝，直到 CPU 命令观察端复位，防止迟到响应误归属
新 ID。已被硬件接受的事务仍继续。实际 rate、valid、epoch 与 sticky
DSP fault 直接来自 runtime；本地只保存命令上下文及只读观察快照，不
持有第二套参数真值。

CPU／preset 复位只清 APB 命令、结果、计数与观察 owner，不驱动 DSP／
stream／PLL 或时钟核心复位。复位后硬件仍忙时拒绝新请求，待其完成且
连续四拍无 busy／结果脉冲才重新准入；通过 `ACTUAL_STATUS`+
`SNAPSHOT_EPOCH` 重新发现实际状态。DSP sticky fault 不会被 CPU reset
或 recover 伪清除。

## 验证

运行：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/services/run_audio_clock_service.py \
  --prepared-project /Users/sphenicidition/.cache/gw138k-task-20261030/f03-scan-window-profile-revision3/workstation/Prj1 \
  --output /Users/sphenicidition/.cache/gw138k-task-20261030/audio-clock-service-final-v2
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
```

runner 可省略 prepared reference，自行从已版本化锁定 baseline 经现有
`timing.apb` 重建相同真实 CDC；不是依赖该临时目录才能运行。该次也验证
重建字节与 revision 3 实际 prepared source 完全相同。

| 检查 | 结果 |
|---|---|
| native service Verilator lint | 零 warning |
| accepted 来源回归 | 10／10 通过 |
| 50 MHz 服务与 27.4 ns bus 异步相位 | 3.7／0.1／21.9 ns，三组全过 |
| 每组 APB 事务／最长 access 等待 | 145 次／9 个 bus cycles |
| 每组真实请求／恢复脉冲 | 11／1，均单拍 |
| 每组真实 core accepted／applied／failed | 9／9／1 |
| held-valid／并发 busy／迟到拒绝 | 一次提交／立即拒绝／core 与 policy 两类均记录 |
| 真实 QUIESCE 故障与恢复 | 真实 core 超时进入 FAULT；recover 无普通 accepted 仍按 busy 接受并应用 |
| 丢 ACK／丢 applied | 两类均有界终结，后续立即拒绝，迟到结果不记成功 |
| applied epoch 错配 | 失败并锁定关联 |
| 启动旧 applied | 仅 unowned 计数，不记 applied |
| CPU reset 中硬件继续 | 实际事务完成且 epoch 推进，观察 owner 清零，不重放 |
| sticky DSP fault | 三次命令拒绝，包括 CPU reset 后 recover；故障仍可读 |
| 实际状态快照 | status 捕获旧 epoch，硬件切换后对应 snapshot 仍不撕裂 |
| source bus 停钟 | 常开域仍完成硬件结果与服务终态 |
| 输入漂移 | 全部 source／baseline／profile 哈希前后相同 |

三相位每组分别核对提交 6 次、硬件接受 4 次、成功 3 次、失败 3 次、
总线拒绝 14 次的中间检查点，证明 APB、accepted 和 applied 计数没有
混为同一事件。core 资格、完整帧 quiescence、预填充与运行返回在测试中
由独立输入提供；许可／响应丢失／epoch 错配是明确的负向注入。

离线身份：`audio-clock-command-offline-v1-a952e76df86b6553`。

- source-set SHA256：`a952e76df86b65531cc09a3c805c8659ec3ee616314a15ff250a119eb11ffcbf`
- native service SHA256：`15222de53157764a0c6dfc9107b856bc13cb48998fa39e20d1513af71b84376e`
- 真实预解码 APB SHA256：`99eddbe61b57756f50e97cf108099cdfaf7324b55178808ab4d403bebf9818b7`
- 本次 verification SHA256：`b8ae25f2e470ba29fb7c419bed300c22e2e99bd71e9c62e5477835388cafede2`

父级以 `audio-clock-service-parent-final` 独立复跑三相位，全部通过；
逻辑输入 source-set 与开发验证完全一致，验证期间输入哈希不变。
对应验证身份见机器文件的 `parent_independent_verification`。

## 剩余门禁与回退

需要未来显式装配绑定唯一请求 owner、独立 APB 页和绝对地址、runtime
状态／策略与整机超时预算，再接维护固件及 CPU 启动重新发现流程。仍需
真实双参考资格、DCS、DSP／I2S、完整 CDC／reset／时序约束、整机综合／
P&R 与授权硬件验收。此离线检查点不能说明 CPU 已能切换板上音频。

回退为保持该 opt-in 服务未实例化；原有 services、顶层、profile、固件
与绝对 APB 地址分配没有改变，无位流或部署可回退。
