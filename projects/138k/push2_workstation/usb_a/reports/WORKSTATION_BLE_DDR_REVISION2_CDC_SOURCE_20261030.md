# BLE DDR revision2 实际 CDC 来源检查（2026-10-30）

已将独立 scope `runtime-r00-no-local-panel-ble-ddr-v2` 接入维护审计，父级在固定 `27732817b67e21ac`／VG `3ef23f27…` 上完成 shared、USB2 owner reset、录音 phase1 和 raw-store inventory 四项公开审计。旧 scope 的默认配置、拒绝行为与端点要求保留；新 scope 显式锁定 revision2 的完整配置、269 项 enabled 输入身份及实际 GPRJ 顺序。保留旧串行 counter 文件但改为编译 balanced 来源也会被拒绝，后续源码不可继承本次审查。

父级五项测试通过，包含 12 项实际网表变异和四项选择负控；独立固定 commit 复验五项／同组负控通过，另增 13 项来源／闭包负控。交付方另在真实 269-input 元数据及 GPRJ 上执行七项选择负控，全部拒绝。父级逐项核验独立 seal 与最终四报告的 helper SHA；详细来源与证据见[机器记录](workstation_task_20261030/ble_ddr_revision2_cdc_source_inventory.json)。

新增 inventory 检查八组 raw-store、四组 seal、一个 authority 普通接收对，以及 50 位 Gray（两个九位 FIFO 指针和 32 位 heartbeat）。每个第一 D 的生产 FF 和第一 Q 的完整消费者均显式绑定，42 组来源／reset／safety 闭包保持。四组 raw payload 共 528 个逻辑位、524 个实际 FF；缺少的 length 高位和 BL8 word 低三位单独列明。seal 的四位 code 未保留为 FF，其常量／别名消除与完整握手仍未接受，不能默认为通过。

原 phase1 保持 425 FF／42 Gray／82 payload；Gowin 合并 seal 目的复位与 drops 前两级的实际闭包已显式锁定，包含十个 seal CLEAR，不允许任意新增消费者。shared 仍严格核对 88 行约束，USB2 仍核对三个 receiving CLEAR 和完整下游 fanout。本阶段不安装新 SDC；phase1 的 18 个原始 receiving CLEAR 只作提案，新增 raw inventory 不生成约束。

四份维护 profile 仅刷新来源快照并纳入新审计依赖；新 prepare 分别为 `0a32736104874154`、`9b8ec5ce9631c2b1`、`c1f321fffd0697f0`、`28bba443b6c95e29`，各 12 项来源回归通过，staged 字节分别与其前序完全相同。enabled profile 20 项（一个可选历史项跳过）、no-panel 六项、accepted 来源 17 项通过。旧审计单元回归保留可选历史网表跳过，未将跳过称为实际网表通过。新 prepare 没有重新综合，277 与 FF 不改名继承。

这仍是实际来源及端点结构检查：held payload 捕获、RAM 所有权／数据弧、复位脉宽／recovery／removal、Gray 物理飞行及整机 CDC／PLL／STA 都未完成。全部完整、物理、硬件与部署标志为 false，没有 EDA、SRAM 或 Flash 操作，R00／R01／R02 方框保持未完成。
