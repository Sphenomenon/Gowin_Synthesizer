# F5 布线失败分析与 F6 LUT-only 准备，2026-10-30

F5（`C11030F5`）已完成 placement，在 routing 报 `DesRoute failed`，进程退出 1，`PR0004` 给出 **297 条未布通网络**。没有生成 FS、SDF 或 STA 结果，不能接受或部署。F5 原输入哈希重新核对一致，失败产物与原候选不修改。完整进程、短日志、证据哈希、连接分析与 F6 prepare manifest 见 [f06_dqs_lut_only_preparation.json](workstation_task_20261030/f06_dqs_lut_only_preparation.json)。

## 已知事实与未知位置

F5 的文本/HTML报告只包含未布通总数，没有列出网络名；失败 VO 仅有连接，不含 LOC。`.p` 为加密 placement，`.db` 是未提供实例名映射的二进制数据库。本次只读分析不启动 EDA，也不猜解位置映射。因此 **F5 的八个目标实际坐标均为 unknown，297 个具体未布通网络也为 unknown**；CST 目标区域不能替代真实落点，不能宣称 297 条都位于 C2:30 或都属于 DQS。

以下是 F3 已完成 routed timing 导出的实际位置，用于说明原始布局，不是 F5 的位置：

| lane | F3 config FF | F3 HOLD LUT | F5 追加目标区域 |
|---|---|---|---|
| 0 | R93C178[2][A] | R90C171[1][A] | R[104:110]C[2:30] |
| 1 | R101C176[1][A] | R98C174[3][B] | R[94:108]C[2:30] |
| 2 | R92C180[2][A] | R90C171[2][A] | R[84:98]C[2:30] |
| 3 | R92C177[1][A] | R90C171[0][B] | R[74:88]C[2:30] |

从 F5 VO 核对四条实际连接：每个 `read_rclksel_conf_*_s0/Q` 都有 **10 个消费者**，其中一个是相应 `hold_Z_*_s/I0`，另外九个属于 calibration/precharge/count 等逻辑；每个 HOLD LUT 的另一路 I1 来自相应 `hold_gen[*].hold_i_s0/Q`，LUT 输出只驱动相应 DQS HOLD。完整消费者清单保留在 JSON。

F5 同时将 config FF 和 HOLD LUT 拉向左侧，可能把 config 的另外九处扇出变成长线路。器件报告还显示 CLS 60517/69120、BSRAM 309/340，PRIMARY/LW 均 8/8。较高利用率与窄左侧区域可能增加路由压力，但没有网络级失败导出，**这只是待检验假设**，不是已证明根因。

## F6 的单变量修正

父级授权的 F6（`C11030F6`）直接从原 hash-bound F3 派生，只对四个 HOLD LUT 使用与 F5 相同的区域，四个 config FF 自由布局。相对 F5 仅撤去四个 config-FF 区域约束；不同时加宽 LUT 区域，以便区分这项变量的影响。

现有 `workstation_custom_board_implementation.py` 增加显式互斥选项 `--ddr-dqs-hold-lut-only`，沿用既有 derive 入口；原 FF+LUT 模式保持可用。LUT-only 仍验证全部四组 FF→LUT→DQS 的类型、INIT、真值表、数据、UI clock、reset 与 DQS X4 配置，不绕过 register 检查。若父 CST 已约束 config FF 或 HOLD LUT，仍拒绝；不允许从已有 F5 约束中暗中删改。

保留 F3 原 capture `R[40:50]C[70:90]`、0.800 ns min-delay、硬资源/IO、VG、SDC、place 2/route 0、自动 hold repair 和全部时序检查。F3/F4/F5 的原始字节和候选身份没有变更，没有使用当前 RTL 重新综合。

实际 prepare 输出：

- 目录：`~/.cache/gw138k-task-20261030/f06-dqs-lut-only-C11030F6`
- manifest SHA256：`37ce33f6db55f44d850aadcb8c2db9f4bb3644cfe10629b5c4d225e370a1e929`
- CST SHA256：`b04283774f0090df902f248edf66057a499c63221b18e36e2fbac11b7b51ff03`
- helper SHA256：`4b32ee8296d1d2cc7bf4978799ad46005b4abf1b76a928ec6e91ac74f1082b56`
- 父 F3 evidence SHA256：`abf87e360e4a06688a3769edc7270e8322671600b888ad55700eefd83ba877b3`

DQS 准备测试 10 项、原 capture 7 项、原 implementation 22 项全部通过。新增测试覆盖恰好四个允许 LUT/相同区域、config FF 自由、互斥模式、四组拓扑验证仍有效、父 evidence/VO/CST/祖先输入漂移拒绝，以及已约束 config 的父 CST 拒绝。真实 prepare 复核所有输入哈希与仅四行追加；输出还没有 `impl/`。

原始准备通过现有入口执行 `--ddr-floorplan-parent-evidence <原F3 evidence> --expected-parent-evidence-sha256 <上述父哈希> --ddr-dqs-hold-lut-only`，使用新的输出目录与 UserCode。没有新增长期 numbered production builder。

## 交给父级的后续运行

已在缓存准备任务专用 `run_f06_physical.py`，仅从 F5 runner 换成 F6 路径/UserCode/manifest SHA，并新增恰好四个 LUT-only 目标和父 proof 守卫。它仍使用 `/private/tmp/gw138k-build.lock` 的非阻塞独占锁、固定 Gowin tool identity、前后输入哈希记录与原环境；**本次没有启动该 runner、EDA 或 JTAG**。父级复核、提交后可运行：

```sh
python3 /Users/sphenicidition/.cache/gw138k-task-20261030/run_f06_physical.py
```

若完成路由，需核对八个观察目标的实际 LOC、四个 LUT 是否在区内、config 的其他扇出，以及每条 FF→LUT→DQS HOLD 的完整 setup。重新检查原 init→wloadn capture 精确 hold、全部 STA/CDC/PLL/资源和特性门禁；若仍失败，保留实际未布通网络导出（若工具可提供），再考虑单独放宽 LUT 区域。没有时序或板级接受之前，不把 F6 作为已接受候选。回退是弃用独立 F6，原 F3/F4/F5 与部署状态保持其原证据。
