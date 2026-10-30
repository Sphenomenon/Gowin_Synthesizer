# TF quiet 发布与 Gray 长链修正（2026-10-30）

已将 TF 代次的 31 级串行 Gray 解码改为五级并行前缀；取消判断直接比较两级同步后的 Gray identity 与 expected identity 的 Gray 编码。完整 32 列 GF(2) 满秩及逆矩阵证明两种比较在全部二值输入对上等价，未把未同步来源接入控制判断。此修改针对旧 `27732817b67e21ac` 综合报告中 generation_sync→quiet_sync 首级的 37 层／−27.245 ns 路径；旧值是综合估计，不能当作 routed STA 或新实现收益。

compute 域新增 `quiet_published` FF，专用于 source 域的两级 quiet 回程。公开 `media_quiescent_o` 保留当前 generation、quiesce、FIFO／held 状态的即时撤销条件；source 仍必须同时满足 invalidate 抑制、generation ACK 追上和持有 quiesce 才能确认静止。回程允许多一拍 compute 延迟，源端采样节拍不等待此后台事务。没有添加时序例外或更改 SDC。

父级独立执行双初值真实 WAV48／44.1、近回绕、背压、source 停钟／reset／取消、最终路由回归；共 480 次 quiet 重取消和 4,160 次实际解码检查通过，错误 quiet 发布和缺少最高前缀跨度两个负控被拒绝。完整 TF 服务链通过每种缓存配置各 22 service、六 CLEAR、11 STOP 场景，disabled 分支及旧路径 12,531 逐周期对照通过；提前 final ACK 与旧组合环负控仍被检出。accepted 来源 17 项、enabled profile 20 项（一个可选历史项跳过）通过。

四份新 prepare 分别为 `ade82500f8f67057`、`24658db0674e60a0`、`b5ad09e4ab5fb5da`、`9784c6656070774a`，各 12 项来源测试通过。相对各自前序，实际 staged 改变仅桥 RTL 与契约 Markdown。首轮父级 delta guard 漏列被复制的契约文档，正确拒绝；原 v1 失败记录保留，v2 只读逐项核验两项精确 delta、全部输入 SHA 并补跑来源测试，未将 guard 失败改写为成功。详情见[机器证据](workstation_task_20261030/tf_quiet_publication_prefix_parent.json)。

本阶段仅源码／prepare／离线功能接受。后续实际新 VG 仍须审查发布 FF、严格两级回程、完整 reset／fanout 和 compute D 锥，再做名义时钟 P&R／完整 CDC／PLL／五类 STA；本次不安装 first-D cut。旧 277／FF 审计不转移给新源码，无位流、SRAM 或 Flash 部署，整机任务方框保持未完成。
