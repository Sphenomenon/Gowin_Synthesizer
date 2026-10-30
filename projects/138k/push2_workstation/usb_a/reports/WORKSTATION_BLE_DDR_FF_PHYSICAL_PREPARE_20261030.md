# BLE DDR FF 物理准备与启动（2026-10-30）

已为固定 revision2 `27732817b67e21ac` 准备独立资源实验 `0xC11030FF`。51 项物理输入绑定真实 VG `3ef23f27…`、591 staged／269 enabled、五份来源元数据、四项综合输出、三份父级实际审计及独立组件审查的 18 文件闭包。physical manifest SHA 为 `55f91fd222c5a2f04105c18868b918243e5c7d664a84dad56a25c3fcc53d8d7d`。

准备器由已锁定 FE 脚本作 dated cache 适配，不修改历史目录或生成新的生产入口。名义 ULPI CST 与 FE 逐字相同；Tcl 仅换 UserCode，保持 place1／route0、不复制资源、timing-driven 与 hold correction 开启。新 SDC 使用本候选的 `06e9739c…`，与 FE 的不同仅为维护 PCM v2 两行增加 32 个 reply D／CE 目标；原 263 目标、13.020 ns、hold 声明及 15 条时钟声明保持。没有放宽时钟或例外。

准备前实际 UserCode 库存未发现 FF 已赋值；准备后仅本物理目录拥有该身份。父级在 P&R 前重新运行真实 verifier，51 输入及 35 负控通过。独立审重新执行同一 verifier，并增加 27 项来源／输出／完成状态／工具／物理选项／路径覆盖，共 62 负控全部拒绝；663 个外部输入前后封存，source 和 prepare 范围无阻断发现。两个独立／准备 seal 的 25 文件已由父级逐项复核。严格的 pre-P&R verifier 会在开始实现后拒绝再次运行；后续使用已封存输入和输出的专门核验。

父级于 `2026-10-30 14:20:35 UTC` 启动 Gowin P&R，使用同一全局 EDA lock；工具已完成网表／约束读取并进入 placement。此检查点只记录准备成功与运行已开始，最终物理结果另记。启动状态保存成独立不可变 snapshot，不把后续变化中的 process 文件当固定 seal。路径、SHA、负控及启动记录见 [机器证据](workstation_task_20261030/ble_ddr_r2_ff_physical_prepare.json)。

本实验保留所有本轮已选功能，不追加裁剪。综合 BSRAM 229 的实际 packing、路由、五类 STA、完整 CDC／reset／PLL／功能门禁均待结果；尚无该候选的位流验收、SRAM 或 Flash 操作。完整与部署标志保持 false。即使工具生成位流，也不能将本资源实验直接升级为可部署镜像。
