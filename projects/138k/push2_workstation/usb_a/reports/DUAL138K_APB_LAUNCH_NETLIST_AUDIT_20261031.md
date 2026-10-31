# 双 138K：APB 请求翻转的实际网表审计

2026-10-31。W9b 全量综合及严格 DEMO 综合门禁通过后，追加的原生协议局部审计因固定要求请求 D 输入为 LUT4 而失败。实际 W9b 把条件翻转等价地映入 DFFCE 的 CE；本批只修复维护审计器及其破坏负控，未修改候选 RTL、SDC、网表或原始综合门禁证据，未重新综合。

## 精确证明范围

保留旧分支 `nextQ = Q XOR (IDLE AND launch)`：请求 D 为 LUT4、CE 恒有效。新增分支只接受唯一 INV 驱动的 `D=~Q`、49 位请求载荷和请求翻转寄存器共同的 CE，以及由两个状态位和两个独立启动叶驱动的唯一 LUT4。两个启动叶均为自由布尔输入，不假定其信号值。BDD 精确证明 `CE=IDLE AND leaf0 AND leaf1`，并将 `nextQ=CE?D:Q` 代回原请求、等待、完成状态方程；不是允许任意组合门通过。

同一证明还检查全部 49 位 `request_held` 的共同 CE／时钟／复位、49 位 `request_local` 的共同 CE／时钟／复位、逐位 D 映射和完整消费者闭包。目的端 CE 必须精确等于 `req_sync XOR req_settled`，配合既有三拍请求链证明第三同步沿捕获。请求翻转完整组合扇出仅允许已证明的本地反馈、状态／响应捕获和唯一跨域 `req_meta/D`；两套实际网表均恰有 37 个触发器端点。

## 实际候选与验证

| 实际输入 | 请求实现 | 布尔赋值 | 测试 | 被拒绝破坏负控 |
|---|---|---:|---:|---:|
| W9b `01aa047a4d25aaf1`，VG `990302b2…` | INV 反馈＋精确 IDLE／启动 CE | 64 | 52 项，41 通过／11 跳过 | 36 |
| W8 `d1109d2f36e8e171`，VG `f50efd53…` | 原 LUT4 XOR、CE 恒有效 | 32 | 52 项，39 通过／13 跳过 | 34 |

两套实际 VG 和各自实际安装的 SDC 均通过新审计。负控覆盖反相反馈破坏、CE 绕过 IDLE、翻转 CE 与载荷不一致、任一源载荷位 CE／时钟／复位改变、目的载荷位时钟／复位改变、位映射别名、额外消费者、提前捕获和既有状态／ACK 语义。W8 跳过新增 CE 映射专属两项，其原分支和其余负控实际执行。厂商 RAM18／RAM36 的注册输出保持仿真也通过。

所有 W9b 644 项、W8 643 项封存编译输入在最终验证后重新逐项核对一致。维护文件冻结 SHA256：

- `tools/workstation_native_protocol_audit.py`：`ffbf679e12619b3106392b4b3c359f084e635fce215b56bce081b21f7e675caf`
- `sim/test_workstation_native_protocol.py`：`f9ba4691a1ae67d6dbfa1cf98678a777c54096fc5185fb832d4039ce52bfa039`

机器证据：[dual138k_apb_launch_netlist_audit_20261031.json](dual138k_apb_launch_netlist_audit_20261031.json)，SHA256 `18eeb3d98ef1dfee593b01e17e1ed00e327dff3700ae253db7de283bec18b05c`。外部完整日志位于 `/Users/sphenicidition/.cache/gw138k-dual-20261031/w-demo-d-v9b-physical-audits-v1/`；最终为 `native-vg-v3*` 和 `native-w8-reference-v3*`。

## 保留的失败与边界

最初 `native-vg.log` 的固定 LUT4 结构失败和 `native-vg-tests.log` 的 41 项测试结果（1 failure、4 errors、11 skips）均保留。中间 v2 完整回归已分别通过 45 项测试，但最终证据使用补齐请求载荷捕获证明后的 v3。原综合 gate 的审计器身份、候选中封存的旧审计器和全部原始输入不追改；新工具作为外部审计单独记录身份。

本结论只证明所列 APB／原生 mailbox 局部结构及实际安装的局部 SDC 查询，不接受其余 CDC、整机路由时序、PLL 或硬件功能。W9b 完整 P&R 的真实资源／时序另记，不能由本报告推断已通过。未下载 SRAM、未写 Flash，原板卡镜像保持不变。
