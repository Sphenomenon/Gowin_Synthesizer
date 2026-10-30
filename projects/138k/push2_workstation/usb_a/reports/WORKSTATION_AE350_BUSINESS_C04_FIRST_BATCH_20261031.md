# C04 首批业务迁移实际综合对照

同一完整功能配置的首次对照没有取得净资源收益：迁移前 `904b2c6` 的 `011fdc9c6697df42` 与首批真实 C 业务 `72f5d71` 的 `8f615119768bfbf2` 分别完成实际 Gowin 综合，耗时 371.465／402.533 秒。两份独立副本的 653／676 个原始文件和实际输出重新逐项验哈希；未改正在运行或已固定的准备目录。

| 综合统计 | 迁移前 | 首批迁移后 | 差值 |
|---|---:|---:|---:|
| Logic（厂商报告口径） | 94,623 | 102,224 | +7,601 |
| LUT | 75,967 | 83,325 | +7,358 |
| ALU | 16,802 | 17,045 | +243 |
| Register | 60,578 | 63,180 | +2,602 |
| RAM16 | 309 | 309 | 0 |
| 综合 BSRAM | 245 | 245 | 0 |

完整 HTML 汇总经独立解析复核；原始 DSP primitive 数量保持 MULTALU27X18=37、MULT12X12=4、MULT27X36=42，不把它们折算成物理 DSP。综合没有 AG 诊断。XML 层级的 exclusive 差值将主要新增成本定位到 `command_endpoint/cpu_mailbox`：+7,114 LUT／+570 ALU／+2,238 FF；旧录音 owner 移除为 −1,504 LUT／−392 ALU／−1,244 FF。CPU 数据桥及命令端点也有新增成本，不能只报告被删除模块或重复记账 DDR 录音收益。

迁移后的实际 VG 时钟检查五项／28 负控、PCM 检查十八项／109 负控通过。两类负控绑定 VG `5ef7455f2189f73fb34ad22216563708081103cd81ace1c937fb2be7139c595b`。这些检查只覆盖各自明确子集；完整 CDC、复位、PMA／Cache、CPU 服务期限仍未验收。首批 C/APB 的 35 条报文逐字对照仅是功能证据；二批扩展中发现 fixture 的 `timeInc` 单位需从 ps 修正到 ns，正在重新验证真实异步时钟比例，不能用原测试推断运行时限。

下一步针对邮箱动态地址减法／移位／宽选位实现做等行为优化，再以新来源身份重新 prepare 和综合。允许 BSRAM 换 CLS 的原则保持，但本轮不能据此声称收益；现有单周期并行输出契约也不能直接替换成同步 RAM 而不处理接口变化。

机器记录见 [ae350_business_c04_first_batch.json](workstation_task_20261030/ae350_business_c04_first_batch.json)。父级包 `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-business-c04-parent-v1` 绑定 1,355 项外部文件，`verify.py` 可只读复核，seal SHA256 `db76783e90ad679e8e98ad272ae51335be95fc1d7ae246f8b129db0dc20260bd`。没有该候选物理 CLS／BSRAM、P&R／routed STA、位流或实板验收；未操作 SRAM 或 Flash。C04 整项保持未完成，回退可选原 profile 并以独立身份重建。
