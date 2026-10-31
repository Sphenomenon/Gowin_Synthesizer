# M15 默认完整物理实现

M15 `D211010C` 已完成全量 P&R 和独立子门，整机时序仍失败，不能进入部署。物理 BSRAM 235／340、DSP 119／298；setup 3,590 个违例端点、最差 −1.914 ns，hold 1 个端点、最差 −3.478 ns。源码 TF 五节点证明另见既有专项报告，不能据此转授物理接受。

来源为 `custom138k-workstation-m-demo-v1-cf9d6319a310d6fe`，保持 M15 冻结的完整乐器／矢量／效果／TF／USB／HDMI 来源，本基础版不含 CNN。physical manifest SHA256 `e79a0e1ced980cf4b0211d5c5889b88d9b5879b885d06a423c2a4947f181ace7`；VG `4707d235626cd446faf4ab00174f51c363c32db7926199cb2aa2449f51eb6a06`；完整 SDC `6fa398b1bf7418d052e6cdc0c98c90512d506cc75931fa952b974f7b7db1562c`；FS `7863081a7d399ae2efef7c350e99da2b0e0c07f7e5f3eaf6c5b37df0ebf923a5`。未混入后续 HCI 或 waveform 维护修改。

Gowin V1.9.12，place2／route0、关闭全局资源复制、保留自动 hold 修复和原 DDR 3.500 ns。P&R 862.265 秒，退出 0、完成布线和位流生成。真实 FF 46,932／LUT 52,008／ALU 13,416／CLS 50,186／SSRAM 141；与综合 equivalent BSRAM 195 分列。

recovery 最差 +3.239 ns，removal +0.275 ns。最差 setup 为 chorus LFO→read_address −1.914 ns；其后 USB audio_online→事件队列 −1.911 ns、TF available_bytes→accepted_used −1.904 ns。原 DDR hold 从 R75C12 到 R75C2，arrival 1.977、required 5.455、skew 0.482 ns，关系仍为 3.500 ns。四条真实 clk50 专项报告：同域／全来源 setup 均 −1.393 ns、20 条负路径；同域 hold +0.180 ns，全来源 hold −3.478 ns。100 路径报告上限不冒称完整专项违例数量。

实际 routed VO 的 native 检查 54 项（51 通过／3 跳过）及 46 个破坏负控、边界 7 项及 61 个破坏负控均通过；官方六 PLL／三 shared tuple／七负控通过。所有六任务退出后重验 30 个完整物理文件、588 staged、1,365 冻结审计输入和 683 个 PLL 依赖。最终封存 `m15-audits-v1/default-complete-seal-v1.json` SHA256 `e88ba12c7aff050bd2ccda252edbe480efa2e4d04900e7267473a8e2165f0a1c`。首版 cache launcher 因过宽目录替换在运行审计前失败，保留原文件；v2 仅修精确路径，未改算法或冻结输入。

保持同一 VG／完整 SDC，追加两条 DDR 远区域 CST 的 `D211010D` 已启动全量 P&R；不继承本次或历史子门的接受状态。[机器报告](dual138k_m15_default_physical_20261101.json)绑定来源、完整资源／四类时序、四条 clk50 报告、执行命令和证据哈希。

本阶段无板卡操作、SRAM 或 Flash。板上旧镜像保持；完整 HDMI／DAC／Push／25K 声画、CNN／跟奏及最终双板联合仍待实际验收。
