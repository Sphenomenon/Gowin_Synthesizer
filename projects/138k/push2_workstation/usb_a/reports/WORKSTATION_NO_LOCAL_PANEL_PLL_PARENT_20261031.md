# No-local-panel PLL 审查支持父级复验（2026-10-31）

维护 PLL 审查器现可从封存的完整 source／profile／process 身份显式选择 no-local-panel 的六 PLL 和 audio／USB／CPU 三组控制 tuple；旧默认仍要求七 PLL 和四组 tuple。每组完整十位 `RESET/ICPSEL/LPFRES`、原 10 ns 预算、DDR／video／serializer 子门均保留。没有修改 RTL、SDC、CST 或运行 EDA。

新 manifest 的嵌套路径逐项检查 hash，跨目录与 symlink 逃逸会被拒绝；no-panel 必须使用全新外部 workspace 和独占新建 JSON，禁止回写 physical／source 或覆盖已有证据。调用方仍须先验证 P&R 真正完成、成功及 VO／SDF 输出 hash；该子门不替代完整物理、CDC、reset 或板级门禁。

父级合入 `61e325d` 后独立完成 23 项定向测试：真实 c7／FF／旧 F02 清单分别为 6／6／7 PLL，身份替换被拒绝。另重跑旧 F03 完整 routed PLL／startup：七 PLL、四组十位 tuple 及三项真实负控均通过。独立复核交付 seal 的 17 文件、review 的 2,805 原始依赖，以及父级 F03 的 33 项输入 hash；交付中的 280 逐位变异、24 实际候选负控保留各自证据。详见[机器记录](workstation_task_20261030/no_local_panel_pll_parent.json)。

四份全新 prepare 各通过 12 项来源测试，与对应 Chorus prepare 的 staged 字节／编译清单完全相同：enabled `60568933ad6331d4`、no-CNN `b6131efe83fcb5ac`、R00 `d5fd64444d600f7a`、no-panel `2c7d2f419b26e289`。身份变化来自审查工具的完整 source snapshot；新身份不继承旧综合接受。fresh enabled profile 20 项（旧 legacy prepare 一项跳过）及 accepted sources 17 项通过。

父级初次 F03 运行缺少必需 `GOWIN_SIMLIB`、旧 prepare 与当前 source snapshot 不符的拒绝均保留；随后使用全新输出和正确环境重跑通过。c7／FF 没有 SDF，故本阶段只接受其来源与 PLL 清单，**不接受其 routed PLL**。没有板卡操作、SRAM 或 Flash 部署，整机任务方框保持未完成。
