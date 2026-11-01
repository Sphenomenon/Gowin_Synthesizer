# PCM bitmap 最终 context 判定：维护源码

2026-11-01。针对 W17 实际 DSP fault→PCM owner written bitmap CE 长链，维护 `workstation_ae350_pcm_owner.sv` 现在先计算不含晚到 context 的资格，再在私有 bitmap 写入末端选择：context=1 使用并行资格，context=0 按实际派生关系执行最终清除，X／Z 使用原有顺序 NBA。其他源码字节保持，未加入 live_matches 分组，没有新状态或采样延迟。

精确候选 `290d3fba…` 与独立缓存审阅一致，严格逆变换逐字恢复 Git 前版 `1c575c3f…`。维护入口重新通过：

- 实际完整模块 52,224 个四态检查，50 状态组／11 输出／512 RAM 字／4 bitmap；实际 raw 命令 owner 7,217 周期，4 个实际变异及 4 个来源负控全部拒绝。
- 从实际标量依赖 DAG 与原顺序 NBA 建模，context 0／1／X／Z 及四个派生关系共 8 项 UNSAT；两个错误方案为 SAT。accepted／usable 等派生资格没有当作独立自由量。该证明不是完整 SystemVerilog 时序归纳证明。
- 原 PCM owner 八项，包括 48k／44.1k、±2000 ppm、每项 576,000 帧；window／descriptor／control／output-context 与历史 bitmap 两入口保持通过。历史入口明确先逆回各自阶段，原 fixture 与破坏性控制不变，不能代替当前 context 证明。
- 正式通用 PCM→效果→I2S 回归通过 1,454 个物理帧；D-only 通过 1,918 个物理帧、1,917 个 display snapshot、12 个 PANIC 场景。两者绑定同批最新配置接受回执 RTL；这里的 physical 是离线串行器重建帧，不是板测。

主线程复验封存的 462 份文件、132 个当前输入和 Git 完整逆变换。初始 helper 编写阶段 AST 失败保留在独立目录，修正后用新输出执行以上验证。完整身份、入口及局限见同名 JSON。

本阶段未更新 profile、综合或 P&R，没有实测资源／时序收益，未 SRAM／Flash。离线模型没有验收真实 HCI／SBC、HDMI 像素或 DAC；下一完整 M/W 候选重新锁定与测量。回滚可还原本阶段六份 RTL／sim 文件并使用原锁定候选，固定 W17 位流未消费本修复。
