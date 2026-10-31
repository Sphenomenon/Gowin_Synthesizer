# AE350 邮箱固定字译码的实际整机综合对照

2026-10-31，固定源码 `fd7625dc70fb85bd60ee7842a6e1f3aae1f5606c`，候选 `custom138k-workstation-ae350-business-v1-09ae2f713f688bb7`。固定字译码将首批业务版本的综合 Logic 减少 **2,608**，但相对业务迁移前仍增加 **4,993**，尚未实现 C04 整体净收益。此处为实际整机综合，非 P&R 或物理 CLS／BSRAM 接受。

## 同功能与来源

首批业务和邮箱优化版本的配置完全相同，612 项 staged 输入仅 `rtl/services/workstation_business_mailbox.sv` 不同，另外 611 项逐字节相同，包含 PLL、CST／SDC 和固件。改动用固定地址 case 替换减法、乘八及可变 part-select，保留存储、160-bit key、ABI 和单周期 ready；原父级功能证据见[邮箱固定字阶段](WORKSTATION_AE350_MAILBOX_WORD_DECODE_20261031.md)。

该固定候选仍是第一批业务 revision1，不能继承随后第二批下载业务或当前 registry revision2 的来源。实际综合 391.885 秒、退出 0，全部输入及原 prepare copy 前后哈希一致。综合复核覆盖三份固定版本的全部 2,029 项文件与264个当前层次实例；完整差异和实际 Gowin HTML 留在外部证据包。

## 实测资源

| 实际综合版本 | Logic | 利用率 LUT | ALU | Register | 综合 BSRAM | RAM16 |
|---|---:|---:|---:|---:|---:|---:|
| 迁移前 `011fdc9c` | 94,623 | 75,967 | 16,802 | 60,578 | 245 | 309 |
| 首批业务 `8f615119` | 102,224 | 83,325 | 17,045 | 63,180 | 245 | 309 |
| 邮箱优化 `09ae2f71` | 99,616 | 80,719 | 17,043 | 63,178 | 245 | 309 |
| 邮箱优化减首批业务 | −2,608 | −2,606 | −2 | −2 | 0 | 0 |
| 邮箱优化减迁移前 | +4,993 | +4,752 | +241 | +2,600 | 0 | 0 |

Logic 使用厂商 HTML aggregate，报告自身满足 `LUT + ALU + 6×RAM16`；该换算只复核此报告口径，不把它当物理 CLS。当前 raw LUT primitive 为 80,412，另有307个 INV，合计利用率 LUT80,719。DSP 三类为37／4／42，各版本保持。邮箱实例 exclusive LUT7114→4464（−2650），其他层次净+44 LUT、−2 ALU、−2 FF；整机净值不能由单实例节省直接代替。

## 针对性门禁与证据

固定 `fd7625d` 工具／配置下，对实际 VG 的 clock5tests／28负控通过；installed PCM 门禁18tests／109负控通过，`paired-nextq-v2`、896selectors、闭包65／263／141／207。当前主线 revision2 工具首次按来源策略拒绝旧 revision1，此失败保留；复验使用固定旧工具，未修改旧候选或放宽身份检查。

父级在新目录实际重跑资源审计，所有候选、差异及数值与独立审阅结果一致。父包 `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-mailbox-synthesis-main-parent-v1` 的 `verify.py` 已实际通过，2,051 项直接外部文件并链接两个只读审阅包；seal `27d7d735aa8eedebbdad896d4f210f6f6fd80ba36652a7d6f7829767c8db0dee`。机器记录见[父级收据](workstation_task_20261030/ae350_mailbox_synthesis_main.json)。资源审阅／PCM 补充包 seal 分别为 `b406d8beeb8df1cd01805fe041964824f8496aeec5ec87700d42a5cb93680164`／`e5561af43e7e1914c2ac45b10fda4d8cf002ea2edc22d292f32cf4b2541c32c2`，均另行复验。

这些门禁没有建立完整 CDC／reset、动态时钟切换或完整功能等价；综合估算时序不替代 routed STA。本候选尚无强制 PLL_R[0] 的 native CST，后续须生成修正后的新身份，不借 C9 探针转移物理接受。此阶段没有 P&R、位流、SRAM／Flash 或硬件操作；继续核算第二批实际下载替换和新增接口／存储的整机净成本。
