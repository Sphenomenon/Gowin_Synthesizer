# BLE DDR revision2 实际综合检查点（2026-10-30）

固定父级候选 `custom138k-workstation-r00-no-local-panel-v1-27732817b67e21ac` 已完成新综合，耗时 350.564 秒、退出 0。591 项 staged 输入前后保持，四项输出 SHA 已封存；实际 VG SHA 为 `3ef23f278d862238a97114d3a09e5cc00ff39426e90f5189fdf0d0d7b9a1ca65`。没有 AG 组合环诊断；其他综合警告按类别记录，未据此声称完整 lint 通过。

| 综合报告值 | 前序 PCM v2 `7d1c3b9b` | 本候选 | 差值 |
|---|---:|---:|---:|
| Logic | 103,147 | 106,446 | +3,299 |
| Register | 58,602 | 60,911 | +2,309 |
| BSRAM | 253 | 229 | −24 |

这些是综合值，尚非物理 packing 或净路由收益。前序输入未含后续 seal release、CPU 显式 map 绑定和 BLE DDR 组合，表格不作为单项改动的物理对照。

独立实际原语库存确认：旧 BLE `live_capture.pcm_memory` 的 32 个 SDPB 全部退休，四个 transfer-bank SDPB 保留；新 store 只有四个 16-bit SDPB 缓存和四个 36-bit SDPX9B 双时钟采集 FIFO。与旧 e855 网表的其余所有 block 路径和非初始化参数逐项相同，可见 block 原语 237→213；不能把可见数量和综合等价 BSRAM 或物理 site 数混用。新缓存 A/B clock 都为 50 MHz，FIFO 两端为 50 MHz／memory clock。

独立静态连接审完成 495 项 actual alias／DFF／clock／98-bit PCM 核验，保留物理 PCM 到原 BLE 通路及 CPU 所需半字交换。fault cone 的 146 nodes／175 edges 无组合环；两个 bridge protocol fault 的边界确为 memory-domain DFFCE，移除寄存边界的图负控能够检出环。另登记 17 个精确 reset FF 端点和五个 reset cone，包括 mapper 把 raw control release 合并至 PLL-init 两级 enable 的真实别名。六个可见 PLL、一个 DCS、一个 CLKDIV 及 15 条 SDC clock 声明保留。这里只核对静态结构，未接受物理 CDC、reset pulse／recovery-removal、opaque DDR 或动态失钟行为。

父级重新运行现有维护检查器，全部绑定本次新 VG／process：

- 时钟四项／28 负控通过；静态 clock／DCS 拓扑公开 CLI 通过。
- Gray／media／USB fence 27 项／75 负控通过，其中两项未提供的历史 VG 对照按原规则跳过；公开 CLI 确认原约束安装，仅覆盖既有 21 组 direct Gray 与媒体边界。
- PCM 18 项／109 负控通过；公开 CLI 确认 `paired-nextq-v2` 实际安装，四组闭包为 65／263／141／207，896 个 selector，选定 payload 静态覆盖无遗漏。

独立 seal 的 18 个文件、591 项输入、四输出及三组公开审计／测试证据均由父级重新校验。完整路径与 SHA 见 [机器证据](workstation_task_20261030/ble_ddr_r2_synthesis_parent.json)。

旧 shared／USB2／recording-phase1 的 revision1 配置拒绝仍保留；新 revision2 精确 scope、优化后的合并 release 闭包和新增 raw-store／authority CDC 审查正在另做，不能继承旧接受。上述 checks 不完成整个 RAM 数据、CDC、reset 或 PLL 门禁。尚未 P&R、没有位流或板测／部署；FF 将作为独立名义时钟资源实验，实际布线、五类 STA 和硬件验收继续分别记录。R00／R01／R02 与整机任务方框保持未完成。
