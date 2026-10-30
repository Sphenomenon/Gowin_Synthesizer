# no-CNN C11030FA：独立物理资源试验准备（2026-10-30）

实际综合候选 `custom138k-workstation-no-cnn-v1-525ffff10d622031` 已明确选入首轮no-CNN资源P&R，UserCode为 `C11030FA`，place2／route0、replicate=false。父级与独立审查均通过18项登记输入hash和23个破坏版本检查，已启动运行；本检查点不记录尚未完成的物理结果。

父级在这份实际VG上重新完成时钟4项／23负控、原Gray／媒体／USB CDC27项／77负控，均无跳过。两项审计分别为 `runtime-clock-source-audit-v1-8dc4415c7d525f15` 和 `runtime-cdc-gray-media-fence-source-v2-dae09bcc7fd35519`；后者仍只覆盖21组／400位及既有媒体／USB子集，安装范围不扩大为全部CDC。日志和审计hash见[局部验证证据](workstation_task_20261030/conditional_no_cnn_clock_cdc.json)。

物理输入使用原VG和301行SDC原字节，CST只经现有maintained ULPI nominal LVCMOS33附加规则转换，Tcl逐字来自现有implementation helper。没有降频、增加宽cut、改hold策略或再删除功能；显式移除范围仍只有用户条件授权的CNN分析／曲谱跟奏。30项保留owner仅证明实际层级／资源存在，不等于全部功能接受。

| 物理输入／审查 | SHA256 |
|---|---|
| physical_inputs.json | `5a595a358d0d539d75ad6f305c745850968eb914b2a2b4d3d1f0837fef24cc40` |
| actual VG | `37c811ffcc0a0ae2ce55aa66550c95bec8bb04cc7fc92aa69c1cc7c17d6f3f4f` |
| physical SDC | `ead347d58729b7ac917ca6b27a0c0d65c598ac4cd8f8dcd7fa1cd127c19c4036` |
| physical CST | `8c3f8415936623883006f02b6c70ad464f323337d9ed486583fee4349cbead3e` |
| independent review seal | `7ef6cb1bf3170863bc5fbaa694a671fc87bd749a1c9ea1bd07f3ca04f57d1705` |

本次具日期cache preparer独立扫描原综合日志的AG／结构环／error诊断，没有向封存process补造历史字段。原严格prepare verifier因Gowin新增 `Prj1.gprj.user` 而拒绝额外文件；试验适配完整重算profile／编译选择／571项输入，仅允许这份精确hash的UI结果XML，单独登记为post-synthesis证据。原输入、原manifest、旧checker及历史失败不改；未知额外文件仍拒绝。准备时审查用worktree的八项关键工具／配置与主工作区字节相同，差异身份不隐去。

17个加密DDR内部query完整保留，静态parser的空项不是Gowin工具解析接受。新的PCM实际拓扑检查、观察RAM数据弧、全部shared CDC／复位／PLL、两模式routed setup／hold及功能／电气仍有独立缺口；即使生成FS也不能据本manifest部署。父级启动的P&R进程及输出持续变化，不在prepare seal中伪装封存完成。

物理目录为 `/Users/sphenicidition/.cache/gw138k-task-20261030/no-cnn-physical-C11030FA`，完整prepare／父级／独立审查与launcher身份见[机器证据](workstation_task_20261030/conditional_no_cnn_fa_prepare.json)。旧F8／F9失败只作为条件授权依据，不把其feature_preservation或资源结论转移到新配置。本阶段无板卡、SRAM或Flash操作，deployment_allowed=false。该cache preparer在maintained完整runtime物理入口就绪后退出，不成为另一份长期生产builder。
