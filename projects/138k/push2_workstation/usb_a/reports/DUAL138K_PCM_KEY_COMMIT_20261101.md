# W12 实测 PCM 路径修复：分组 key 比较和本地 COMMIT 拒绝

日期：2026-11-01。机器记录：`DUAL138K_PCM_KEY_COMMIT_20261101.json`。

唯一生产修改是 `rtl/audio/workstation_ae350_pcm_owner.sv`，冻结 SHA `3eab83ad77e0ff28aac3bee416751262bb3af01241d1df596e769a871d53f5b3`。M14 的来源及 physical prepare 已由主线程冻结后才落地；未修改 M14 的缓存输入、其它生产文件、profile 锁、task2 或部署状态。

## 真实问题

W12 默认 P&R 的 `staged_controller_2_s0/Q → written[0]_16_s1/D` 为 audio 域最差路径：slack −4.341 ns，20 级逻辑，data 17.167 ns，其中 cell 6.248、route 10.613、C2Q 0.306 ns。最终 `n5329_s2/F` 扇出 256，至目标 D 的单条路由 3.034 ns。

实际 VG／VO 表明，源码的 32 位 XOR／reduction 仍映射为 `n245_s0…n274_s0` 的 controller key carry 比较。随后经过五组 key 汇合、descriptor／sequence 校验和完整 response error mux，再进入 invalid COMMIT 的 `terminate`／bitmap 清除。已有 operation-specific acceptance 没有覆盖这一拒绝分支。

缓存 RCA 对确切 Path2 的 90 个数据引脚完成 VG／VO 核对；`n2327_6` 因实际 owner／runtime formal 导出而使用 `u_managed/n2327_6` 的物理别名，逐级连接单独核对，没有按名称相似跳过。时钟和 reset 侧针不属于这项数据路径核对。

## 两项精确修改

五组 `staged_{controller,generation,stream,rate,physical}`／`active_*` key 各拆为四个 8 位比较，共 20 个具有 `syn_keep=1` 的 scalar；最终 `key_matches` 保留全部组的 AND。没有寄存器、新 owner、周期或协议改变，也没有改变 existing physical-epoch comparator。

新增 `rejected_commit`，仅组合当前写命令、地址 0x040、操作 2 和既有 `control_format_ok`／`control_id_ok`／`commit_error`。invalid COMMIT 的 terminate 分支使用它；response 输出 mux、overflow 分支、后续 failure reason、fault／revocation／cancel／bitmap 优先级原样保留。复用过程式 format／ID 标志，保留未知 strobes／饱和 ID 的原 `if` 语义，没有改为直接 `!full_write`。

两项先分别在缓存副本验证并审阅 diff，再获授权合并到生产源码。最终验证重新编译、运行合并后的完整模块，未将两项独立记录拼接为合并验收。

## 验证

精确参考为实际 W12 consumed owner：`w-demo-d-v12/workstation/Prj1/rtl/audio/workstation_ae350_pcm_owner.sv`，SHA `3342a94cfd4e103efbb11808c5753aa8839069634ebf5d78ed80c0dab9cff837`。

| 合并源检查 | 结果 |
| --- | --- |
| 完整 W12／合并 owner twin | 两个实际编译 fixture 各 7,190 周期，比较 61 项状态／输出、512 RAM words、4 组 written／frames；含 6,000 随机命令、有效流、同拍 revocation 和 publish／consume |
| key 全域证明 | 5 组各 64 输入位二进制 UNSAT；5 组各 128 符号位四态 UNSAT；源码检查全部 20 个精确切片、keep 和最终 AND，反向恢复后边界外与 W12 完全一致 |
| key 实际模块四态 | 5,120 向量；所有 160 key bits 的 0／1／X／Z 对，以及另一组已知 mismatch 支配 unknown |
| COMMIT 全域证明 | 完整命令 binary decoder／拒绝更新条件 UNSAT；原过程式 format／ID 四态逻辑上下文 UNSAT |
| COMMIT 实际模块四态 | 98,304 向量；65,536 个有效 COMMIT 上下文组合及 32,768 个任意四态命令／资格组合；比较实际顺序 if 更新决定，并核对被选 COMMIT 的拒绝谓词四态语义 |
| 实际负控 | 漏 bit31、最终 OR、漏 format、漏 ID、直接 `!full_write` 误改未知值语义五类均在合并模块中触发预期失败 |
| 既有 owner 回归 | 8 项全过；48k／44.1k × ±2000 ppm 各 576,000 帧，真实 stereo SRC reference、零／一／二步消费、session／CPU／rate／TF／history／queue／sequence 边界 |
| 来源／DEMO | 17 项 current source 和 15 项 DEMO audit 全过；diff check 通过 |

初始将 drift 缩为 16,000 帧时，两组负偏差尚未进入 zero-step，触发原覆盖门槛；没有修改门槛或代码来迎合短跑。原默认 576,000 帧完整重跑四组全部通过，保留短跑观测和完整日志。

维护 runner 为 `sim/audio/run_ae350_pcm_key_commit.py`，SHA `4c735e66846b1fa8673fe9c3c6f16e4d136ab9c3414c73dc22d6eadeec9a879a`。最终合并证明 `pcm-key-commit-combined-v1/verification.json` SHA `0871d248c3de4225421cb8050bf6173434f129f0e05a423674c15eef4eab6663`。所有输出在外部 cache，完整证据清单及 SHA 见机器报告。

从 `usb_a/` 重跑，reference 必须匹配 W12 固定 SHA，output 必须是新的外部目录：

```sh
/Users/sphenicidition/miniforge3/bin/python3 -B sim/audio/run_ae350_pcm_key_commit.py --reference <exact-W12-workstation_ae350_pcm_owner.sv> --output <new-external-output>
python3 -B sim/test_ae350_pcm_owner.py
python3 -B sim/test_current_workstation_sources.py
python3 -B sim/test_workstation_demo_audit.py
```

## 验证阶段

这是源码及离线验证阶段。全模块顺序行为由仿真检查，局部全域证明不等于全 owner 形式验证。本阶段未综合或 P&R 新源码，不预记 timing／资源收益，未烧录 SRAM／Flash，也未作硬件验收。下一候选必须独立记录真实映射和 routed 结果；256 扇出清除网仍是需要观测的限制，不能由 comparator 改写推断其已解决。
