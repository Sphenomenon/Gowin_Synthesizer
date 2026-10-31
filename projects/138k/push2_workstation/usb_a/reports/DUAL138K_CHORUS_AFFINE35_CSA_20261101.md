# Chorus 35 位 CSA 维护落地与完整 effects 回归

已将独立审查通过的 chorus CSA 候选精确落到维护 `workstation_runtime_chorus_effect.sv`。生产 RTL 仅整个组合 `rate_delay` 函数改变，其余完整模块字节保持原样，没有增加状态、周期、接口或改动其他算术。新独立维护 runner、实际函数穷举及原有完整 chorus／effects 回归全部通过。本阶段没有新的综合、P&R、资源收益或板测结论。

新完整源码 SHA256 为 `1cc7ddd5e00edcb5975ed64cc2eceb4707029f5add724467700fbeae30b61ea5`；精确旧完整 fixture 为 `28ef32d47d55a0d44eef8ec23fa3437cdbef647d4ca0b023f98cb184bd8ce50c`。主线程审查记录 `chorus-affine44-csa-root-review-v1.json` 为 `989420fad0fb7bdceae9571cefe32796831d2ce170d2bf1ca73d7553834e9c5a`，包含任意三个 35 位输入的独立模加 CSA 等价证明及九个移位系数和为 361267 的检查。

## 算术与来源链

44.1 kHz 的原 `361267*t + 134225920` 使用相同九个精确移位项及 bias，经五层 carry-save 压缩和一次最终 35 位加法完成。右移 28 位、16 位 cast 和基值 441 保持原样；48 kHz 分支逐字保留。原 `if(rate44)` 的 X／Z fallback 不变。任意 triangle X／Z 沿未移位项的 XOR sum 路径到达最终算术加法，保持原有未知传播。

`tools/workstation_chorus_provenance.py` 新增受完整 source hash、精确旧／新函数锚点、完整旧父文件 hash 和正逆 roundtrip 约束的 CSA 逆检查。随后仍执行原 affine44、scratch、narrowing 及原 prepared 来源链；没有改旧 provenance、adaptation 或 vendor 字节。这是验证逆链，不生成生产 RTL。

原 `prove_chorus_affine44.py` 继续证明其原 affine grammar，但明确先检查 CSA 逆链并记录 normalized affine 与实际 CSA 函数的不同身份；实际 CSA 函数由新入口独立证明。原完整 chorus 测试保留 M12 fixture、prepared 参考和独立物理时间／PCM 模型，并增加新 CSA 来源逆链的缺失、重复、变异、错误父身份及额外字节负控。原完整 effects oracle 没有修改。

## 验证结果

全部命令退出 0，精确输入、指标及正负控见[机器报告](dual138k_chorus_affine35_csa_20261101.json)。

- 新维护 `sim/audio/run_chorus_affine35_csa.py` 固定新源码、精确旧完整 fixture 及函数身份，要求函数外字节相同，并在结束时复验全部依赖。任意三个 35 位输入（105 位自由度）的模加 CSA 恒等式与任意 16 位 triangle 的独立函数 SMT 均为 UNSAT；三个精确算术破坏模型均为 SAT。它们是源 hash 绑定的手工翻译及 IEEE 运算符论证，没有声称 HDL 前端或全模块 temporal formal。
- 实际完整新旧模块内完成 278,664 个函数 probe，覆盖所有 65,536 triangle × rate 0／1／X／Z，以及二位四态排列、各位单独和全 X／Z，并核对独立整数延迟公式。三个实际源码 mutant 全部编译成功后因 `TAP_MISMATCH` 拒绝。
- 新完整 chorus 双实例运行 50,000 source clocks、100,008 两沿状态／公开输出检查，完成 9,398 PCM outputs、9,399 内存写、320 次配置接受、300 次 history clear 和七次 legacy clear。每次真实内存写核对目标字，结束核对两声道全部 2,048 字；包含 valid 间隙、复位和 X／Z PCM。
- 既有 `run_runtime_chorus_delay.py` 对实际新函数、原 native、M12 和独立物理时间公式完成两速率共 131,072 个穷举，tap 范围分别为 480..575、441..529；八项 provenance 负控及五项实际函数 mutant（丢移位项、错误舍入、35 位截断、丢 final carry、错误 48 kHz shift）均拒绝。
- 原完整 chorus 的 10 个测试通过。48／44.1 kHz 各运行 60,000 帧，前者逐周期对照 prepared 参考，后者包含完整 LFO 周期；完整 M12/new 比较分别为 1,440,033／1,440,035 个半周期、12 个公开输出。另有 6,000 帧切换／历史保存、五个 FSM 状态 legacy clear 和配置 backpressure／优先级覆盖。
- 原完整 effects 的 16 个测试通过，包括 36,288 帧 prepared 48 kHz 参考、24,288 帧双速率独立模型和 44,512 帧排列／维护链路。PANIC 碰撞、两时钟停止、迟到／缺失 fence、九个 chain/stage clear 边界和 sticky failure 均通过。

原完整 chorus 编译警告计数仍为 `TIMESCALEMOD=2, WIDTHEXPAND=12, WIDTHTRUNC=3`；没有放宽既有 warning、clock、CDC 或 timing 门禁。上述 PCM／时钟场景均为 RTL 离线仿真。

## 独立可重跑与证据保留

新 runner 仅依赖维护源码、版本化旧 fixture、公开锁定 baseline math 包、Python z3-solver 和 Icarus，无私有 cache 输入。math 包 SHA256 固定 `f07fab099e112b18d9fc142eeb701139cae62be79e2f25596e134aaecea88f3d`。在 USB-A 根目录运行：

```text
python3 sim/audio/run_chorus_affine35_csa.py --output <new-directory>
python3 sim/audio/prove_chorus_affine44.py --output <another-new-directory>
python3 sim/audio/run_runtime_chorus_delay.py --output <another-new-directory>
python3 sim/test_workstation_runtime_chorus.py -v
python3 sim/test_workstation_runtime_effects.py -v
```

外部证据根目录为 `/Users/sphenicidition/.cache/gw138k-dual-20261031`。最终新 runner `chorus-affine35-csa-maintained-v2/verification.json` SHA256 为 `901a0ca60353759dd11200cd9e1a0c32b5b52db90463c14e8d6397298024d595`。本次所有维护运行均通过；v2 补充依赖 inventory／结束门禁及明确 normalized affine 字段，先前 v1 成功输出保留。

封存前已把各 `input_sha256`、完整测试 `SOURCE_SHA256` 和维护交付依赖存为按内容 hash 命名的对象。`chorus-affine35-csa-maintained-input-snapshot-v1/snapshot.json` SHA256 为 `fc722f5763790e18deee2a97c7951d7ab2c659243e41a86e4749f156f6c40c30`，共有 40 个输入版本、38 个独立对象，全部再读匹配。其中两个早期 runner 版本从最终文本作精确受检逆变换恢复并匹配其原记录 hash；索引明确标注，原 verification JSON 未改写。后续维护源演进不影响读取这些历史输入字节。

最终 seal 为 `chorus-affine35-csa-maintained-sealed-v1.json`，在所有命令退出、快照和报告完成后生成并逐项重读。M15／W13 内原 chorus 均仍为旧 `28ef32…ce50c`，本阶段未改变其冻结身份。旧 M15 default／far 路径尚未闭合；下一整机候选必须检查实际 live 算术锥、真实资源、P&R／STA 和相应实板声画后，才能判断改进。

本子任务没有改锁、task2 或其他生产子系统，没有 commit／push、SRAM／Flash 或板卡操作。主线程负责后续候选冻结和阶段交付。
