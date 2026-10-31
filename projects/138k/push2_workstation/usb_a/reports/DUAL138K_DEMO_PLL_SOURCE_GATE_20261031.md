# 双 138K DEMO：完整 PLL／串行器来源门禁，2026-10-31

M7（`0067ea90a6354485`，`D2103103`）、M8（`f11f1756db68044a`，`D2103105`）和 W7（`aec83bda901d0042`，`D2103102`）的完整维护 PLL／startup 子门禁均通过。M8、W7 各七项实际 VO／CST／SDC 变异全部被拒绝。完整结果、输入与工具散列及运行环境见 [配套 JSON](DUAL138K_DEMO_PLL_SOURCE_GATE_20261031.json)。**这不表示整机时序、CDC、全部复位、电气或实板验收通过。**

维护工具为现有 custom-board DEMO 物理清单增加精确来源分支，重查注册 M／W spec、候选身份、完整 staged closure、GPRJ 选择、固件／ROM、复制 profile／integration 元数据、Gowin 完成日志、VG、资源报告和实际 SDC。Gowin emitted log 明确记录为自己的证据类型，不伪装成 runtime driver stdout/process seal。只有显式无本地面板契约的五项元数据全部匹配，才选择六 PLL 和三套完整十位共享控制。旧七 PLL 和已有 runtime-driver process 路径保持原门禁。

DFFRE 的 `RESET` 是同步数据输入。本阶段对维护清单内九个 M 接收器、六个 W 接收器证明：第一级与第二级使用正确同域时钟，CE 恒开、INIT 为零，第一级 Q 仅驱动第二级 D，且无竞争驱动、顶层导出或歧义端口。实际 SDC 的首级 D／RESET 例外和后级 2 ns 最大延迟必须精确存在一次；后级 setup／hold 例外被拒绝。实际 CLK→Q、route、第二级 setup 总和继续受 2 ns 限制。这些入口作为 CDC 同步数据单独分类，不冒充 40／80 ns stopped-clock 复位端点。

| 实际 routed 候选 | 共享 tuple 最大／10 ns | video PLL 最大／10 ns | TMDS reset settle＋recovery／40 ns | DDR reset settle＋recovery／40 ns | grant 后级／2 ns |
|---|---:|---:|---:|---:|---:|
| M7 | 5.712 | 9.491 | 5.044 | 7.263 | 0.904 |
| M8 | 5.456 | 9.296 | 5.094 | 6.857 | 1.091 |
| W7 | 8.496 | 9.405 | 6.466 | 6.886 | 1.257 |

三者均重新执行锁定 DDR 源证明、DDR 配置证明、完整 OSER10／差分直连／像素分频检查、六 PLL 清单、三套共享 tuple、视频两级 PLL、AE350 专用 PLL site 和独立 RTC 检查。RTC 正向与负控均绑定候选内冻结源码，输入及审计依赖 before／after 散列保持一致。原 10 ns、40 ns、80 ns 和 2 ns 预算均保留，原物理输入和历史失败证据未修改。

来源测试 26 项中 25 项通过；一项仅适用于两个 runtime-driver process seal 的测试按证据类型跳过，DEMO 候选相互替换另有通过的负控。精确 M／W spec 测试包含八个重新封存错误 revision／source／configuration／role 的子例。同步 RESET helper 九项测试及原 DEMO 审计 15 项回归通过。M8 实际 native routed VO＋SDC 的 28 项全部通过、24 个网表破坏均拒绝，见 [局部 CDC 报告](DUAL138K_NATIVE_CONTROL_CDC_20261031.md)。

M7 原审计的七 PLL 误选和未分类同步 RESET 错误保留在外部 v2 JSON。新门禁的 M7 最终记录为 `m7-full-pll-audit-v6.json`，M8 为 `m8-full-pll-audit-v3.json`。W7 的真实 routed 门禁为 `w7-full-pll-audit-v3.json`，exit 0，六个同步 grant 接收器通过；v1 参数错误及 v2 在运行中发现 `workstation_profile.py` 改变而拒绝的日志均保留。PLL 工具、原候选配置与物理输入未修改，未运行 SRAM／Flash 操作。M8 已知完整 STA 的 3042 setup／36 hold 失败、W7 的整机 setup／hold／reset 缺口仍由候选报告单独处理，不能因本子门禁通过而省略。
