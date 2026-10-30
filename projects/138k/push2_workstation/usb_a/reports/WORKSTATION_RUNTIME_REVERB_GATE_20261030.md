# Runtime Reverb 实际综合网表功能核对

日期：2026-10-30。独立顶层 `workstation_runtime_spatial_reverb` 在真实
Gowin 综合后，以**原始未修改 VG＋完整官方 GW5A `prim_sim.v`**运行
Icarus 四态仿真；同一 TB 与输入序列另行运行精确 RTL＋官方 SDPB。
两次输出的 43,519 行控制／PCM 轨迹、2,265,338 bytes 完全相同。

**本阶段没有修改 RTL、旧 snapshot、VG、profile 或固件；未做 P&R、
SDF、物理时钟／I2S／整机 CDC 或板测，也未操作 JTAG／SRAM／Flash。**

## 来源与综合

实验缓存：`/Users/sphenicidition/.cache/gw138k-task-20261030/runtime-reverb-gate-81b3325c`。

`synthesis_inputs.json` 冻结 4 个 RTL 和 1 个 runtime preset：
audio_math package、`workstation_sdp`、`workstation_sdp_banked`、
`workstation_runtime_spatial_reverb` 与 `runtime_spatial_room_preset.svh`。
它们逐字节取自修复后的 `runtime-audio-component-synth-108192b1`；四个
维护输入也核对当时工作树相同。package 沿用该完整闭包的锁定来源。
没有复制完整工程、测试 RTL 或 vendor bytes，没有文本改写实现。

保留原始全部顶层端口。设备 `GW5AST-LV138PG484AC2/I1`，version C，
`sysv2017`，真实 76.8 MHz／13.020833333 ns 约束，timing-driven，仅
`run syn`。runner 独占非阻塞 `/private/tmp/gw138k-build.lock`；实际综合
约四秒、rc=0 后释放锁，输入哈希不变。未添加 false path 或放宽时钟。

综合日志无 `EX1998`／`EX3638`。报告为 LUT `1977(1336)`、Register
`2020(1566)`、MULT27X36 `19(19)`、SynBSRAM `20(0)`；原始 VG 可数到
20 个 SDPB 实例。这些仅是**综合报告与综合网表结构**，不是布线后资源
或物理 BSRAM 验收。

## 实际功能验证

官方模型直接引用已安装文件，SHA256 为
`2ec53fec48601d2d491299bc3a28b4b199d3a79708f1dd38f72555a5c688ebd5`。
RTL 通过现有 `WORKSTATION_SDP_VENDOR_SIM` 选用同一官方 SDPB 模型。
参考与 VG 分开编译／运行，所以无需重命名、补丁或修改 VG。TB 的条件
分支只读取两种层次命名下的实际 RAM write enable／pending／read state，
从不 force 或改写设计内部状态。仿真未注入 SDF，不作真实传播时延证明。

| 覆盖 | 两次仿真相同结果 |
|---|---|
| 总帧／计算时钟 | 14,502／1,174,682 |
| 48k／44.1k 非干声 wet 帧 | 1,816／1,191 |
| 饱和 clip 帧 | 1,563 |
| 左／右非零帧 | 各 4,222 |
| 配置 ACK／history done | 3／4（配置也清历史） |
| 清除状态检查 | 6 次 |
| 真正写尾取消／在途读取消 | 各 1 次 |
| trace | 43,519 行，逐 byte 一致 |

序列先在两率分别填满实际 early／FDN 延迟返回，输入包含双声道正负
满幅与不对称样本。覆盖 48→44.1、同率 44.1 配置、44.1→48，配置与
history 请求在前帧高半字写尾期间保持，必须等真实 quiescence 才 ACK；
配置优先级与 wet gain 保留也被检查。

direct clear 精确插在 SDPB 低／高半字之间，断言二十个实际 primitive
`CEA` 全为零，清除后 pending 高半字为零。另一项在真正 RAM 读事务
发出后 clear，检查五路 `read_state` 归零且没有旧 valid。每轮清除后
继续输入超过有效延迟长度的零帧，所有输出 PCM／clip 必须为零，排除
旧历史在绕回后泄漏。RAM contents 本身按设计不物理清零；验证对象是
在途写／读取消、历史逻辑失效及后续覆盖。

RTL 完整运行约 60.8 秒，actual VG 约 341.8 秒，均 rc=0。曾尝试
Verilator 检查完整官方模型，因其 FF `assign/deassign` 与 nonblocking
状态混用报 `BLKANDNBLK`；失败日志保留，未修改 vendor 模型或关闭该
错误冒充验证。最终证据来自通过的 Icarus 四态运行。

## 身份、复核与限制

机器证据：`reports/workstation_task_20261030/runtime_reverb_gate.json`。

- identity：`runtime-reverb-functional-gate-v1-e98758acd8f36079`
- synthesis source set：`81b3325cb84eda7807de3da0300149ee3994f63a0b9160183b6b1227d7166483`
- simulation input set：`e98758acd8f36079ad8960f056e0d204f26ffce15e235a4ec69d615e056d0b2f`
- 原始 VG：`cf9e25328706d73c23b82257f7178e753c763b0b18f2673dd258aae6aa0777f2`
- 相同 trace：`d19579073c69c5a814403e02892112c3eee68e2606f7909cc661d0b74048c1e8`

缓存包含 exact source、工具／preset／TB／仿真程序哈希、`run.tcl`、
`run_synthesis.py`、`gate_simulation_inputs.json`、原始 VG、两次 log／
trace 与只读结果检查入口。复核已完成结果：

```sh
python3 /Users/sphenicidition/.cache/gw138k-task-20261030/runtime-reverb-gate-81b3325c/check_gate_results.py
```

父级独立复核了完成后的全部输入／工具／VG 哈希与两份完整 trace 的
逐 byte 一致性，未重复长时间仿真；对应审计身份见机器证据。

再次综合必须准备新的独立目录／身份，不能覆盖该实验。该缓存是历史
诊断证据，**从不成为生产 source**；后续集成需由新哈希 runtime/profile
候选及独立物理验收替代相应验证范围。当前证明是指定序列的实际综合网表
功能对照，并非全输入形式等价，也不提升整机双率、时序或部署接受状态。
