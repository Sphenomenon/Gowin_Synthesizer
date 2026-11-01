# W14 DMA fault consumer 的精确 D／CE 映射修复

W14 全量综合完成后，原 strict 与 DEMO boundary VG 回归均在 `fault watchdog_fault all FF consumers drift` 拒绝。本阶段核对实际 W13／W14 网表并证明故障保护仍完整，然后补充这一种精确映射；未修改候选、来源锁、冻结的失败审计快照或约束。

## 唯一消费者差异

W13 实际 VG SHA256 为 `3c7866321188f7b36dc601c36f6b572b04ee5c5f7786f434a10a1b0d2bb4a787`，W14 为 `36576c86a2c2c6d42830bb2c75af5441143ca288ca93397b17923de03fee2141`。三个 registered fault（watchdog、protocol、peer）的完整 FF closure 在两代都各有 663 个端点。逐项按真实寄存器身份核对后，唯一差异如下；所有其他 FF 端点、端点时钟、RAM／opaque 端点及 top-output 清单均保留严格检查。

| 实际目标 | W13 | W14 |
|---|---|---|
| `delay_dma/wptr_0` instance | `wptr_0_s3` | `wptr_0_s0` |
| fault consumer pin | D | CE |
| D | `n2425_10` | `n2425_7` |
| CE | constant VCC | `wptr_31_11` |
| CLK／CLEAR | `memory_clk`／同一 memory-release reset | 相同 |

原审计器只允许 `wptr0 D + state1/2 D` 的 663 形态，或 `wptr0 CE + state1/2/3 CE` 的 664 形态。W14 实际是 `wptr0 CE + state1/2 D` 的 663 混合形态。因此旧 gate 的拒绝是真实清单漂移，不能通过过滤前缀、放宽域、只看数量或笼统接受 D／CE 互换处理。

两代实际 staged 与冻结来源中的 `workstation_runtime_delay_ddr_dma.sv` 均为 SHA256 `4486bddae55e89c191cace04fdfad6163b71af9a1c43b5369e8fabc0d7e42551`。W14 raw CLEAR source 另与已审源码证明的 SHA39ae 一致；该证明保持独立，本阶段的 DMA 结论来自实际 DMA 源与实际映射功能核验。

## 实际 next-Q 全域证明

分别抽取两个实际 `wptr_0` 的 D、CE、CLEAR、Q 完整 LUT cone，配对全部 10 个真实 FF 输入：4 个 state bits、3 个 sticky faults、wptr0 自身、memory_release2 和 read FIFO full。没有黑盒谓词替代这些 cone，也没有正常状态、正常数据或无故障可达性假设。

两代 reset-inclusive next-Q BDD 完全相同，共 73 个 BDD nodes；独立逐项计算实际 LUT 的 1024 个二态输入组合也全部匹配。其精确源函数为：reset 时置零；`S_PACK=7` 时翻转 Q；`S_RD_MARKER=6 && !full && !(watchdog || protocol || peer)` 时置零；其他情况保持 Q。PACK 的原有行为保持，故障 veto 精确约束 marker commit。该结论涵盖所有 16 个 state 编码及每个故障组合，未用合法 FSM 状态筛选。

维护工具新增此完整 next-Q 门禁，核对 DFFCE shape／clock／INIT、完整 10-input support 和实际 D／CE／CLEAR 方程。只补消费者清单会让任意 D／CE 互换伪装成另一种已审形态，因此功能门与第三种精确清单一起使用。三个 fault 源仍必须各自匹配完整同一清单；所有原时钟、sticky-D、reset、exact three-source OR、接收级、完整 USB queue／RAM、角色绑定、11 个精确 SDC pin selectors 和附加约束拒绝规则保持。

## 维护实现与回归

维护 `tools/workstation_demo_boundary_cdc.py` SHA256 为 `bd45e3dbe5a8ecbff4bac1d8fdd2603e9280b713e98549f968032757982544e8`；`sim/test_workstation_demo_boundary_cdc.py` 为 `37b90d68c32faa6b2424b5af6616cc076a07778d206ab09a52f2aeb745f0c82e`。除 audit 入口外，全部原 helper 函数逐字保持，PROPOSAL 的 AST 完全相同；没有修改或再生成 SDC。

- 原审计器对旧 W13 VG／routed VO 各通过完整 7 tests／61 negatives；两份原始回归保留。
- cache 提案工具对 W13 VG／VO、W14 VG 各通过原完整 7 tests／61 negatives，共三套。
- 新维护测试的等字节 cache 副本对 W13 VG／VO、W14 VG 各通过 7 tests／69 negatives，包含全部 61 个原负控及 8 个新增真实对象功能负控。
- 新负控覆盖实际 wptr0 D／CE 互换、功能 reset、INIT、实际 D LUT 反相、三项 fault 各自有效 veto 删除及未审 state1 D／CE 互换。6 项保留所有三 fault 的原完整结构 closure，其中三项通过实际 LUT cofactor 分别删除 watchdog／protocol／peer 的有效 veto，均由具体 next-Q 功能门拒绝，不能靠清单漂移掩盖功能检查。
- 另有独立缓存 7 个实际 VG 负控及每代 1024 个真值组合通过；维护 Selection 3 tests 与 accepted-source 17 tests 通过。

新增 reset 负控的前两次缓存构造分别因 global／relative net 作用域错误、把 fault-dependent CE 接到 CLEAR 而提前拒绝；两份失败说明与原脚本保留。最终负控改用同 scope 的常量 reset，保留 fault consumer closure 后确实检查功能门。提案／维护工具字节始终没有因这些测试构造错误而调整。

主线程另委派的 M16 独立正控对实际 VG／default VO 均通过新 helper 的 role=M audit 与 SDC validation：10 named inputs／1024 全赋值、fault663／queue140，RAM 端点 VG4／VO8。该独立记录 `m16-nextq-w14v3-boundary-review-v1.json` SHA256 `9d29ed5d3cb8a6d67121300f07822fab0bd220ff1c8ebc554d768d77379851c4` 已纳入快照，实际 VG／VO 与 auditor 字节另行核对；未改 M16 原已封存审计或来源。

## 封存与后续边界

[机器证据](dual138k_w14_boundary_wptr_mapping_20261101.json)记录实际差异、BDD、1024-vector 交叉核对、8 套完整回归、独立强负控、命令和完整来源身份。内容寻址输入快照为 `w14-boundary-fault-consumer-review-v1/final-evidence-v2/input-snapshot.json`，SHA256 `733488bf7ac7e1bac2282e52d41e1b7379170018888640c72debed6a517c8b42`：86 个实际输入对应 53 个独立 blob，包含实际 VG／VO、传递导入依赖、实际 staged DMA 源、原失败日志及测试脚本。最终 source seal SHA256 为 `4fa2958aac7b8ae1b75db07110e0ca40ff17d817b65e4bc469941af328697897`，96 份证据均再次校对，seal／报告自身没有递归 self-hash。

本阶段没有运行综合、P&R 或板卡操作；W14 的综合及之后物理结果由主线程单独记录。原 W14 v1 冻结工具与失败记录保持；主线程另以已审工具建立外部 v2 审计身份，仍核对 stage 中原工具 SHA 与原 SDC 选择 metadata，不改旧来源或重新包装失败记录。此处是完整二态组合映射证明与结构 CDC 审计修复，尚不构成 mapped-cell 四态证明、整机 sequential formal、STA／CDC 物理验收或实板声画验收。
