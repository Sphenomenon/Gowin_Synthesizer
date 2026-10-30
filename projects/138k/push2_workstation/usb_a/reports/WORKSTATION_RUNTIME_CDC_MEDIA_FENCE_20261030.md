# 运行时 CDC 第二阶段：媒体停止与 USB 停钟围栏

日期：2026-10-30。本阶段维护 `native-runtime-cdc-gray-media-fence-v2` 的端点、有限逻辑语义、精确 SDC 文字与负例门禁；完整清单、物理 CDC、STA、PLL、实板和部署仍分别验收。阶段身份：`native-runtime-cdc-gray-media-fence-v2-stage-b625d0ac61e872c1`。机器证据：[runtime_cdc_media_fence_v2.json](workstation_task_20261030/runtime_cdc_media_fence_v2.json)。

## 修复的问题与来源边界

原 Gray 检查仍引用 TF 旧实例与异步 clear LUT。运行时 TF 现在由 capture／playback generate 选择新 FIFO，实际网表已成为 source Q→first D→second D 的直接链，不能继续接受旧 scope 或旧 LUT90 许可。媒体停止还增加了 request／ACK／held failure、异步保持、USB 停钟后的真实排空与写端重新开放，需要在实际网表逐项核对。

v2 保留原 21 组／400 bit Gray 范围及原 BLE 复位释放别名，更新其中四组 TF byte FIFO scope，新增媒体和 USB 围栏子集。它没有把历史 150 项或新增 55 组媒体源清单标成已关闭。显示／反馈／AE350、其它 held payload、FIFO 内存所有权和全复位清单等仍在未闭合范围。

## 实际端点与语义

- 21 组 Gray 均要求实际 producer 唯一、bit 身份和源／目的时钟正确，两级数据直接相接、接收 CE 常高、首级 Q 仅扇出到第二级 D。十处明确的 binary-MSB=Gray-MSB 合并仅按明确 owner／bit 接受；四组 TF 均为 13 bit，其中两组 read-pointer MSB 按实际映射纳入这一受限别名表。
- 媒体 request 为两级、ACK 为三级、failure 为两级。对实际 ACK FF 验证 `(CE && (D ^ Q)) == failure_CE`，而不是假定映射必须把事件放在 D 或把 CE 固定为高；真实 LUT／INV 小锥逐项穷举，ACK／failure 源 FF 类型、公共 reset 和 compute 时钟继续核对。failure 更新与 ACK 翻转同一事件，ACK 多一拍稳定时间。
- hold 必须恰好两个 DFFPE，PRESET 真值为 common reset OR 已注册 hold_50；第一级移入零，第二级取第一级 Q，compute 时钟和常高 CE 一致，中间 Q 不得用于其它功能。公共复位或停钟时异步建立保持，解除经过两个真实 compute 沿。独立微型映射与官方功能模型的详细验证见[媒体保持链修复报告](WORKSTATION_RUNTIME_MEDIA_HOLD_FENCE_20261030.md)。
- USB queue release／drain release 各六级，write release 两级，均核对实际时钟、复位、移位方向和中间扇出。对 input_reset、fifo_reset 和 writer0 D 的实际逻辑锥穷举，分别对应已注册 event release／connected／panic、六沿 queue release、真实 drain 完成和 FIFO reset 释放。不会用缺失或裁剪掉的 consume_buffered 四级管线冒充实际排空证据。

## 53 行约束与保护

Gray 和媒体 request／ACK／failure 数据路径以源周期上界设置 max delay，并只切 hold 检查，保留 setup 路径；选中音频参考按更快的 16.9344 MHz 取 59.051 ns。hold_50 Q→两 PRESET 的断言上界为 20 ns；queue_release[5] Q→六个 drain CLEAR 的上界为 13.020 ns。两个异步目标组均没有 false path，recovery／removal 检查继续保留。

端点 selector 展开必须与审核集合完全相同，多、少、歧义均拒绝。新增八个异步端点的保护独立于 `-from`：任何命中其 PRESET／CLEAR 或对应 register 的 false path 都拒绝；max delay 只允许上述两条已审核的精确断言约束。get_ports reset、任意未审核 Q、get_regs、无 `-from` 或无 `-to` 都不能绕过。SDC 校验仍不等于 Gowin 查询对象已解析或 routed flight 已通过。

旧 `custom138k-workstation-v1-9106b1aaffd290c6` 的实际 SDC 还包含混合 USB first-stage setup cut，覆盖了新 writer0 D。因此该候选保留约束失败身份。新 source policy 只从唯一精确旧行中移除 `queue_write_release_0*/D`，保留实际存在的 settled／panic／defaults 三个旧 selector；不接受未经审核的变体，不修改旧候选、manifest 或历史 VG。

## 验证记录与剩余门禁

维护入口为 [CDC 工具](../tools/workstation_runtime_cdc.py)和[实际 VG 回归](../sim/test_workstation_runtime_cdc.py)。工具通过 `--project`／`--synthesis-evidence` 选择已封存候选；回归通过 `GW138K_RUNTIME_CDC_STAGE`／`GW138K_RUNTIME_CDC_PROCESS` 选择同一工程，并显式提供 `GW138K_RUNTIME_CDC_LEGACY_VG`／`GW138K_RUNTIME_CDC_BLOCKED_VG` 才覆盖两份历史负控，不作本机历史目录兜底。实际命令、路径和 hash 见机器证据。

新候选 `custom138k-workstation-v1-f1be50e853d3700a` 的实际 VG 与已封存 SDC 通过非 endpoint-development 审计；570 项实际暂存输入在审计前后逐项重 hash 不变。完整 25 项通过，77 个实际 VG／约束负例全部精确拒绝；测试与审计源在运行前后保持不变。VG SHA：`8fc53d099ebead55ca3926c8d4b2b45b3504fcb1ac1ed5dbcaa1b6e1a1834535`；SDC SHA：`8cc24c8963d1cf8c5887a19c53c8cbc423576d78b2cf94fe51a99802ca310a1d`；process SHA：`05e585abc5ae1d00b22b1cb00eb162b02cc10ca75a12ecb7b6cadbe51ea3f838`。旧 9106 的修复校验器矩阵为 24 pass／1 expected-message mismatch：DFFPE bit1 D 被断开时，先被 bit0 中间扇出不变量正确拒绝，测试原预期是后面的移位错误文字。只修一条预期后，实际 hold 测试与两项 policy 定向复跑均通过；该旧完整矩阵仍保持失败记录，不改写为通过。

最终工具 SHA：`c117a35a2a130feda40589af2435bdf704f8c9a75057abcfb19b3e8895ea0fc8`；最终测试 SHA：`21e4e8ad808d336269cb996ffa8c07ad3ac5e21a47bae0c76798133880d9844d`。53 行审核约束在 ACK／保护修补前后逐字一致，SHA 为 `c97de4d63d463d52585420e2eb6bf0a0e636af7c06e4b6bca14898bcd5871942`。新／旧候选的 570 项暂存输入仅 `constraints/custom_138k.sdc` 不同；所有 HDL、固件与 GPRJ 字节保持一致。两个明确选择的旧 VG 分别因旧 TF scope 和混合异步 hold 分裂寄存器被拒绝，不能替代本候选。

仍未以本次网表映射证明 Gray 编码行为、全 runtime CDC 完整性、held payload 原子性、RAM 所有权／碰撞、异步源 flight／最小脉宽、recovery／removal、实际工具查询解析、双模式 routed timing／PLL、全部功能保持或硬件验收。physical／release／deployment 均保持 false。本阶段没有 SRAM／Flash 操作。

回退必须按完整候选身份恢复成套源码、profile 和 SDC，不能把旧 scope 校验器混用到新 TF 网表，也不能把有组合反馈的旧 hold 映射当作可部署回退。新阶段只扩充审核范围，不提升旧接受配置或新板的部署状态。
