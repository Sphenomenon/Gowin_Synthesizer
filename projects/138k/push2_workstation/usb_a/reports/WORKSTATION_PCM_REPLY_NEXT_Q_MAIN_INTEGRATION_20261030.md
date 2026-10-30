# PCM v2 约束组合与父级复验（2026-10-30）

本阶段将 [D／CE next-Q 审计](WORKSTATION_PCM_REPLY_NEXT_Q_AUDIT_20261030.md)接回四种显式完整工作站 profile。生产准备入口默认生成 `native-runtime-pcm-context-cdc-v2 / paired-nextq-v2`；只刷新工具、测试和契约三项来源锁，配置、RTL、固件、冻结输入与 accepted 来源不变。

回复约束仍为 50 行和 13.020 ns，只改两条 reply 行，为已登记的 32 个 FF 同时列出 D／CE，静态 selector 共 896。实际依赖闭包仍为 197 FF／263 pins；33 个 next-Q 函数按独立发布者及状态方程作 ROBDD 等价检查。旧候选保持 `legacy-v1` 身份，e855 的 29 个漏约束实际 pin 不追改为通过。

## 父级验证及来源

- e855 封存实际网表：18 项回归、109 个负控全部通过；原 profile、process、584 项 staged 输入及 VG 保持。
- 独立复核：全部 65,536 个四输入函数、1,048,576 次真值求值及七个额外负控通过；三个审计文件与交付哈希一致。
- accepted 来源回归 17 项通过。Profile 20 项回归通过，其中一个旧默认配置检查因未提供 `GW138K_PROFILE_LEGACY_PREPARED` 而跳过；四份实际 prepare 的来源回归各 12 项通过。

| 配置 | 新 prepare 身份后缀 | staged／enabled |
|---|---|---:|
| enabled | `eb158105fdf2c4e9` | 571／260 |
| no-CNN | `42f4d601a5ad18da` | 572／260 |
| R00 | `d0d19715318eb2d9` | 584／267 |
| R00 no-local-panel | `7d1c3b9b464ff722` | 584／266 |

四种配置与前一 alias prepare 相比，只有 `constraints/custom_138k.sdc` 字节变化。第一轮 prepare 后，未选择的 owner8 mux 增加 channel-ready 隔离，导致完整源码快照变化，Profile 回归正确拒绝。保留原失败日志后重新准备上述四份候选，staged 字节与第一次 PCM v2 prepare 完全一致，并重新通过 Profile／来源检查；未删除快照检查。

no-local-panel 候选已复制到独立综合目录 `pcm-v2-no-panel-synthesis-7d1c3b9b`，复制时核对全部 584 项 staged 输入及四份来源元数据，并写入 `synthesis_copy.json`。综合于 364.268 秒后返回 0，输入保持，无 Gowin AG 组合环诊断。新实际 VG 的约束安装／负控检查另行运行，尚不提升其接受；过程及输出已单独封存，不继承 e855 综合或 FE 失败物理身份。

机器证据：[runtime_pcm_reply_next_q_parent.json](workstation_task_20261030/runtime_pcm_reply_next_q_parent.json)。其中列出全部日志、prepare、独立 review 及复制封存的绝对路径与 SHA256。第一轮快照失败及重新准备证据同样保留。

## 未完成及回退

这证明工具选择、静态约束和来源闭包已接入，不证明 Gowin 查询及 routed flight／setup／hold 已通过。新综合网表接受、完整 CDC／reset／RAM 数据时序、PLL、物理资源、整机功能及实板均需另验；所有 release／deployment 标志为 false。没有 SRAM／Flash 操作。

回退为恢复本次三个审计文件和四份来源锁，并从对应旧 prepare 重新复制候选；不编辑任何历史 stage。新消费者或综合形状变化必须重新审计，不能自动退回 legacy 约束。
