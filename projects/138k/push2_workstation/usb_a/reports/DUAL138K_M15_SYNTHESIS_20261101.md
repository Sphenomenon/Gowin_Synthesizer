# M15 全量综合与严格门

2026-11-01。M15 `custom138k-workstation-m-demo-v1-cf9d6319a310d6fe` 全量综合 exit 0、210.212 s，声明输入前后稳定。综合 FF 46,932、LUT 52,130、ALU 12,875、BSRAM equivalent 195、SSRAM 141；不预记物理资源或时序收益。

实际 VG SHA256 `4707d235626cd446faf4ab00174f51c363c32db7926199cb2aa2449f51eb6a06`。完整 strict 门通过，SHA256 `9bede6b5ec7ae42a4c3aeeeff97ee0ad7d21a92757fa85d0eb70a7ec10a6f10b`，覆盖显式来源、角色保全／退出、资源、时钟、CDC 结构、SDC selector 与 retirement。Native 实际 VG CLI 通过；54 项回归执行 50／跳过 4，45 负控全拒。DEMO boundary 7 项及 61 负控通过。新 TF 五节点实际 live fanin 的专项证明另记，不用通用审计替代。

875 原始来源、588 staged 及 1365 审计工具／RTL／测试快照复验。默认 physical prepare 再次完整审计，`parent_synthesis_audit.json` 与 CLI 结果深等价。`D211010C` 已启动完整 P&R，physical manifest SHA256 `e79a0e1ced980cf4b0211d5c5889b88d9b5879b885d06a423c2a4947f181ace7`；保持完整原 SDC、DDR 3.500 ns 和既有 ULPI IO type 适配，不继承 M14 far 区域或接受状态。

[机器记录](dual138k_m15_synthesis_20261101.json)绑定实际输入、资源、执行和回归证据。P&R、routed 时序／CDC／PLL、CNN 与完整实板 HDMI／DAC／Push／25K 声画仍未验收。没有 SRAM／Flash、板操作或受保护主区写入。
