# 双 138K：DEMO 边界审计的映射与角色分离

2026-11-01。W11 `custom138k-workstation-w-demo-v1-bafd43c180d52b1c` 全量综合退出0，645 个封存输入、284 个启用源逐项复验一致。外部综合日志与候选 `synthesis.log` 逐字节相等，SHA256 `d991bac7f6aee48167f35fa795f127428d9bce3e157880e57b9b7b1e6f4e2c03`。

综合报告为 FF45,091、LUT54,836、ALU14,096、BSRAM equivalent257、SSRAM298；DSP原始项为 MULTALU27X18 9、MULT12X12 1、MULT27X36 29。综合有128项警告；这些数字不代替物理CLS／BSRAM／DSP或routed时序。默认 `D2110101` 全量P&R已启动，本检查点没有物理结果。

首次 strict gate 拒绝 `u_native_usb/input_owner/settled_sync_0` 缺失。原审计器将 DMA 三个 source fault 的完整 consumer 清单同时用于判断业务角色：663 个 FF 端点判为 M，664 个判为 W。W11 的三个 fault closure 均合法映射为既有 663 端点形式，因而误走 M 的 queue 检查；但其真实 queue Q 完整 139 个 FF／2 个 RAM 端点与 W10 W 逐项相等，manifest 和封存 profile 明确指定 W。W11 没有该 `settled_sync` FF 或 alias；另一个 `feedback/req_settled_s0` 属于反馈 mailbox，不能替代它。

最小修复将两类判断分开：DMA 原有 663／664 两份完整清单各自严格匹配；独立使用 queue 原有 139／140 两份完整清单确定 W／M，再与严格门禁传入的封存角色比对。所有 source、FF pin／clock／reset、RAM 端口和后续 consumer 仍完整核验。严格 netlist parser、四条 SDC 常量和整个 `validate_sdc` 函数与改动前逐字节相等；候选 RTL、SDC、VG 和清单未改。

W11 专项 7 tests 通过，61 个实际对象／原始字节／SDC／相反角色负控全部拒绝；W10 原 664 fault／139 queue 和 M12b 原 663 fault／140 queue 各通过完整清单与相反角色校验。W11 strict v2 全通过，SHA256 `c86669a82e21f9b47454122ede736b5f464c86335b1584fcb775e60a7bba235c`，实际 VG SHA256 `4288ba15b267eee1a8d29c358c0a625b10061c3cfe2896e24be2048de8f016b2`。其原始 strict v1 拒绝、只读 RCA 和全部 before／after 源码及日志身份保存在外部证据，不改写失败记录。

机器证据：[dual138k_demo_boundary_role_20261101.json](dual138k_demo_boundary_role_20261101.json)。本阶段通过的是综合准备门禁与结构检查；物理资源、真实时序、CDC 物理接受及实板功能另行验证，不由该结果推定。后续默认物理候选使用新身份 D2110101。
