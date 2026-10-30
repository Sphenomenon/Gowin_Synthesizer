# 无本地面板的 front_valid 精确别名审计（2026-10-30）

已安装并复核无本地面板配置的 shared CDC 审计适配。实际 e855 网表将视频状态位 3 的源网命名为 `u_video/front_valid_Z`；LCD-on R00 仍要求 `u_video/front_valid`。两项声明分别固定于显式配置，均要求唯一源为 memory_clk 域的 `u_video/u_scanout/front_valid_s0/Q`，不提供可选别名或从目标 D 端反推源的回退。BIST done／failed 的精确源及全部原有扇出检查保持。

父级在已封存的 e855 网表上通过 10 项测试、无跳过，9 项实际对象负控全部拒绝，包括替换为 LCD-on 别名、错误源／时钟、断开源和新增首级 CE 消费者。公开审计重新核对工具及来源哈希；88 行 shared 约束对应 43 个普通首级位、8 组／182 个 Gray 位及 14 组／1,308 个保持数据位。110 个复位 pin 的语义与 13 个不透明 DDR query 仍未接受；本次不证明保持协议、完整 CDC、录音 CDC、物理时序或复位完整性。

四份真实 prepare 的来源回归各 12 项通过，profile 回归 20 项通过；连同实际 shared 回归共 78 项，无跳过。新身份如下：

| 显式配置 | 新 prepare 身份 | staged／enabled |
|---|---|---:|
| enabled | `d8d150c4bac15f2e` | 571／260 |
| no-CNN | `d64b7bb9d22c5a5f` | 572／260 |
| R00 | `2fccc5ff6a5e493d` | 584／267 |
| R00 no-local-panel | `d22edab015e08525` | 584／266 |

四份 prepare 的全部 staged 字节分别与此前已封存的对应 tag-RAM prepare 相同；本阶段只更新审计工具、测试、说明及四配置的对应来源锁，没有改变 RTL、SDC 或已启动的 FE 实验。新身份不继承旧综合或物理接受。安装前 shared 审计的失败保留于[综合与 FE 准备记录](WORKSTATION_R00_NO_PANEL_SYNTHESIS_FE_PREPARE_20261030.md)，不回写历史结果。

完整证据、路径、逐项哈希及负控见[机器记录](workstation_task_20261030/no_panel_front_valid_alias.json)。公开父级审计为 cache 的 `r00-no-panel-e855-shared-cdc-parent-v4.json`，SHA256 `01478010e99b0a118b8a1eaf5e2157de63450df88f6ba4fcba5134009c07381c`。PCM reply 仍有 29 个实际 pin 未由旧约束覆盖；owner8 录音及完整 reset／routed STA 继续单独验证。本阶段未操作板卡，没有 SRAM／Flash 部署，也未提升 release_ready。回退仅撤销此审计适配及其来源锁，不能把旧检查器拒绝解释为硬件失效或接受。
