# 第二批 AE350 业务与独立 RTC 整机综合

固定源码 `f8882c5`、business revision 4 候选 `0981b403bb531b2b` 完成实际 Gowin 综合，
耗时 388.508 秒，614 项 staged、272 项 enabled 输入前后逐项一致。
使用独立综合副本，原 prepare 保留；ILM／DLM 各 64 KiB、启动 ROM 64 KiB，Cache 未启用。

| 厂商综合统计 | 数量 |
|---|---:|
| Logic | 97,375 |
| LUT／ALU／RAM16 | 78,754／16,767／309 |
| Register | 62,876 |
| 综合 BSRAM | 245 |

HTML 汇总与 XML 各层 exclusive／inclusive 加和独立一致。相对首批业务候选的
102,224 Logic 减少 4,849；本候选同时加入独立 RTC，不能把全部差值归因于某个业务模块。
这些数值不是物理 CLS／BSRAM，也不是布线收益。

实际 VG SHA256 为 `739c6ed7b9f58d0a4be22d01e7ffe863fa2aaad5666237e00d79ae91522850ef`。
runtime 时钟五项／28 个负控通过，最终 RTC 源码与固定 VG／VO 回归 11 项通过、两项 opt-in 跳过，
最终 PCM 来源及已安装约束的两项正向检查通过。完整 CDC、特性和警告审查仍未完成；
149 条警告及原始日志全部保留，没有 AG 组合环诊断。

首次审计保留三类拒绝：旧 native 顶层策略及特性路径不接受新 runtime 身份；
prepare-only 清单拒绝 Gowin 新建的 `Prj1.gprj.user`；原 RTC 检查要求布线后的硬核 primitive，
而综合 VG 只暴露加密 wrapper。原 prepare 和全部声明输入另行校验，未删除生成文件或绕过门禁。
维护修复 `a4e5fb3` 把 VG 的 `u_cpu/u_RiscV_AE350_SOC/rtc_tick` 与 VO 的
`AE350_SOC.RTC_CLK` 分为两道检查，后者仍拒绝 wrapper。额外驱动、消费者、向量伪装与
作用域碰撞不能充当直接 RTC 标量接线；独立审阅发现的空端点漏检已补回归。
综合证明仅到可见 wrapper 输入，未证明加密内部接线、硬核内部时序或实际频率。

父级证据包 `~/.cache/gw138k-task-20261030/native-business-rtc-full-parent-v2` 保存
1,300 份原始源码快照、最终及早期审计源码、705 个固定外部文件。
seal 为 `716bc0ca84842afe32d11f5af447f8640174a791d34012a4fee5951e7900e414`；
机器索引见 [ae350_business_rtc_full_synthesis.json](workstation_task_20261030/ae350_business_rtc_full_synthesis.json)。
没有本候选的 P&R、routed STA、位流、SRAM 或 Flash 操作；回退使用原固定 profile 重建，
不修改 accepted／baseline，也不升级整机验收状态。
