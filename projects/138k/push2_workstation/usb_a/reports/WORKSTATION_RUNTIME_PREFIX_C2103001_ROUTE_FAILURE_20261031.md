# Prefix C2103001 布线失败（2026-10-31）

固定源候选 `c7d66b419868f7f4`／VG `8c5d1e5a…10acb2c` 的 C2103001 实际 P&R 退出 1。工具、实现日志和资源报告均记录 **896 条未布通网络**，工具另报 `DesRoute failed`；耗时 862.776 秒，没有生成位流、SDF 或完整 routed STA。未进行板卡操作或部署。

父级独立重验 manifest、1,517 项物理输入、593 项冻结 staged 输入闭包、四项综合输出、六项已登记 P&R 输出、工具及日志 SHA，全部保持；另三项 `cmd.do/db/p` 在完成态独立记录 hash，明确不冒充 launcher 已封存输出。原 SDC／CST、名义时钟、place1／route0、hold correction 和不复制资源保持。完整身份、输出及封存位置见[机器证据](workstation_task_20261030/runtime_prefix_C2103001_route_failure.json)。VO 的存在不代表布线通过。

| 实际物理资源 | C2103001 | 前序 FF | 差值 |
|---|---:|---:|---:|
| Logic | 107,215 | 106,935 | +280 |
| Register | 60,912 | 60,911 | +1 |
| CLS | 63,060 / 69,120（92%） | 63,084 | −24 |
| BSRAM | 268 / 340 | 268 | 0 |
| DSP | 120.5 / 298 | 120.5 | 0 |

PRIMARY 与 LW 仍各 8/8，PLL 6/12、DCS 1/20。物理 BSRAM 268 与该源综合估算 229 分列。FF 的 1,324 与本次 896 是不同网表的聚合观察，日志未提供逐网络失败清单，不能将变化归因于某个模块，也没有 routed 时序改善结论。

并行只读边界盘点及结果审查工具通过 6 项测试／26 个负控，父级复核其 18 文件和 2,200 依赖 SHA。它定位了 TF 普通同步／36 位 held control、recording phase1／raw／authority Gray 与握手、32 个去重 receiving CLEAR 等尚未显式匹配的 selector；原 TF 21 组及已有约束保持。这里的缺口仅指显式 `get_pins/get_regs` 选择，不等于普通 STA 全无约束，亦不代表已安装新例外。协议、复位、物理传播预算仍须分别验证。

Chorus 精确窄化已以独立候选 `6b9610324164f0c9` 启动后续综合，不回填本次身份。后续继续新网表的 clock／CDC／PCM 复核及新物理实验；完整 CDC、reset、PLL、五类时序、真实非零录音和板级验收均未完成，任务方框保持未勾选。
