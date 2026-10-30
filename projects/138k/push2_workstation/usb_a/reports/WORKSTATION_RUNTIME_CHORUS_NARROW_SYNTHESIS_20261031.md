# Chorus 窄化实际综合与父级复验（2026-10-31）

候选 `custom138k-workstation-r00-no-local-panel-v1-6b9610324164f0c9` 已完成实际综合，退出 0、耗时 335.329 秒。来源固定 `8d59fdd` 的 prepare 副本；596 项 staged、269 项编译输入、五份 metadata、canonical identity、四项输出、两项工具和日志均重新核验。实际 VG SHA256：`2cfe81e54a9257d212f4b54cecac56853a50e969dbf532d6857d45ce8fe316c8`。

与前序 c7 相比，唯一编译 RTL 字节变化是 Chorus，新增三份非编译出处文件；SDC、CST、GPRJ、编译顺序和业务配置保持。父级复核独立审查 seal 的 57 文件、1,228 依赖 SHA，并在实际新 VG 上完成 clock 审查及四项回归：15 声明时钟、六 PLL、21 静态 LCD 输出符合所选 profile。这里仍是部分静态 source topology，不接受动态 DCS、完整 reset／CDC 或 routed 时序。详见[机器证据](workstation_task_20261030/runtime_chorus_narrow_synthesis_parent.json)。

| 综合估算 | c7 | 6b | 差值 |
|---|---:|---:|---:|
| Logic | 106,720 | 106,679 | −41 |
| Register | 60,912 | 60,910 | −2 |
| BSRAM 等效量 | 229 | 229 | 0 |

该 BSRAM 口径与 C2103001 物理报告 268 分列。150 条警告按候选 stage 路径归一后多重集完全相同；没有 ERROR 或 AG 诊断，但不据此接受全部 lint 或功能保全。

综合最差五条路径已从 Chorus 移到 `pitch/n27_s/DOUT[16]` → `glide_ratio[21,20,0,1,2]`；最差 slack −16.879 ns、36 逻辑级。音频默认时钟的综合估算 Fmax 为 33.445 MHz，前序 31.409 MHz；其他 11 行不变。它仍低于所需计算时钟，且这些自动时钟的综合估计不能替代原 15 时钟的 routed STA，也不能证明新候选已布通或全部 Chorus 路径通过。

后续针对 pitch `/147` 与 `%147` 进行完整 16 位 API 域的精确算术修订，同时以新显式 scope 审查新 VG 的 CDC／PCM／TF／counter。旧 c7 scope 与 C2103001 的接受不转移；旧 preparer 锁定 c7 的 canonical identity、VG、审查和 root seal，不能只替换 VG 后复用。本阶段没有 P&R、位流或板卡部署，整机任务方框保持未完成。
