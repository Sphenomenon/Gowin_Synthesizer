# 双 138K：路由反相器与分拆 APB 启动叶精确审计

2026-10-31。W9b 完整 P&R 将已证明的请求反相反馈映成 `LUT1 INIT=2’h1`；M10b 则将 `psel && penable` 的合并启动叶用于请求 XOR、两个独立叶用于载荷 CE。v3 固定结构要求拒绝了这两种实际映射。本批仅扩展维护审计器的精确证明与破坏负控，原候选、原审计器封存输入和已提交的 v3 证据保持原样。

## 新增结构与保留证明

W9 路由分支仅接受唯一 `LUT1/F` 驱动、`INIT=2’h1`、`I0=request Q`，继续要求请求寄存器和全部载荷共享已证明的 `IDLE && launch0 && launch1` CE。M10 分支仅接受唯一 `LUT2/F`、`INIT=4’h8`、两个输入恰为捕获 CE 的两个独立启动叶；将它们统一为自由布尔变量后，证明 XOR 请求更新和载荷捕获使用同一精确启动函数。两者均不按网名或已知值假定启动条件。

保留完整有效 `nextQ=CE?D:Q`、请求／等待／完成状态与 ACK 方程，49 位源／目的载荷的共同 CE／时钟／复位、逐位映射和消费者闭包，以及第三请求同步沿捕获。两个新负控分别把反相 LUT1 改为 `2’h2`、把 AND LUT2 改为 `4’hE`，必须被拒绝。

## 实际验证

| 实际输入 | 请求映射 | 自由赋值 | 54 项回归 | 被拒绝负控 |
|---|---|---:|---:|---:|
| W9b VG | INV＋精确 IDLE／启动 CE | 64 | 41 通过／13 跳过 | 36 |
| W9b VO | 精确反相 LUT1＋同一 CE | 64 | 43 通过／11 跳过 | 38 |
| W8 VG | 原 LUT4 XOR、CE 恒有效 | 32 | 39 通过／15 跳过 | 34 |
| M10b VG | LUT4 XOR＋精确分拆 AND 启动 | 64 | 50 通过／4 跳过 | 45 |
| M10b VO | LUT4 XOR＋精确分拆 AND 启动 | 64 | 51 通过／3 跳过 | 46 |

五份实际网表及各自实际安装的 SDC 均通过 v4 CLI 审计。所有负控确实执行并拒绝；跳过项只针对该网表中不存在的其他映射／角色结构。厂商 RAM18／RAM36 注册输出保持仿真也通过。W9b、W8、M10b 的全部封存准备输入在最终封口时重新逐项核对。W9b 远置 DDR 子版本 `D2103114` 的实际 VO／SDC 基线另通过同一 v4，未重复全套负控。

维护文件冻结 SHA256：

- `tools/workstation_native_protocol_audit.py`：`49af05fd28776d3cae3ce64cb610df18462780325d4d91c5365e702e8d559658`
- `sim/test_workstation_native_protocol.py`：`cdf50bde15de1f691415b6632ffe4eafc658afe5c3c97d7d25cb6bc3b0ba061f`

机器证据：[dual138k_apb_routed_inverse_audit_20261031.json](dual138k_apb_routed_inverse_audit_20261031.json)，SHA256 `555b55b9118ff36681c2af4406dfc1d1d3d266925d6fb56c22833a672dc15f0d`。它包含所有实际输入、测试日志、负控和失败记录的完整路径及 SHA256。已提交 v3 JSON 的 SHA256 仍为 `18eeb3d98ef1dfee593b01e17e1ed00e327dff3700ae253db7de283bec18b05c`。

## 验证边界

保留 `native-vo-v3.log`、M10b VG／VO `tests-v1.log` 的失败。此结论只接受所列局部原生／APB 协议结构和实际安装的局部 SDC 查询，不代表完整 CDC、整机路由时序、PLL、声画功能或硬件验收。未修改候选输入，未重新综合、下载 SRAM 或写 Flash；完整 P&R 测量另记。
