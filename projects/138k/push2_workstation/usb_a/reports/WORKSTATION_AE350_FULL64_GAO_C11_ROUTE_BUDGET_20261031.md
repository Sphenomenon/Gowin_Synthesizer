# C11 完整诊断探针：保留的 GAO 路由中止记录

2026-10-31，C11 `C21031CD`，源码 `1ff14c3`，固定产物位于
`~/.cache/gw138k-task-20261030/ae350-local-probe-main-physical-C21031CD-v11`。
机器记录：`workstation_task_20261030/ae350_local_probe_c11_route_budget.json`。

实际综合网表已通过 2,208 位 GAO 全部在 `clk_50m` 寄存、RTC 保持 FF 及直接端点检查。
工具日志输出主路由 90% 和 timing analysis 95% 后仍持续计算；对实际 `gw_sh`
取样确认位于 `genDesignGaoFuseMap_singleAo → gaoPathRouter → mazeRoute`。
这只定位工具耗时，不等于最终 routed STA 或已完成全部 GAO 布线。

父级在 2,441.447 秒主动发送 SIGTERM，实际退出 −15，所有固定输入前后相同。
这是诊断运行预算决定，**没有认定工具挂起或布局布线失败**。当时进程仍活跃。
输出没有最终 `.fs`、`.tr` 或 `.vo`；无物理通过、位流、完整 64 字板上采集或 SRAM 接受。
原输入、网表、日志、工具取样和中止决定均保留，不覆盖为另一次运行。

C11 从未烧入板卡。随后只执行一次独立 operation 0，读到：

- ID Code `0001081B`
- UserCode `C11028E5`
- Status `00022020`

这是原 Flash 配置的当前身份读回；本阶段没有 SRAM 编程、Flash 写入或重载操作。
此前 C10、SRAM Verify 失败及其他硬件证据保持原身份，不向 C11 转移。

封存包 `~/.cache/gw138k-task-20261030/ae350-c11-route-budget-parent-v1`，
72 个固定外部文件，seal
`11d498412425caa1d1e8608419704fb707e1468e313bd6af1b560f11a96a5f5a`，校验器通过。
核验工具来自 `f8882c5`，源快照单独保存；C11 的实际构建源仍是上述固定输入。

下一步以新身份验证较窄的分组 GAO：同一原子快照分四页，只有完整、同序号、
同身份、稳定页面才可恢复 64 字；保持固件字节对照并补独立物理门禁。
本次中止不消除完整诊断、真实 CPU 周期、Cache／PMA、UART 物理映射和 Verify 失败的缺口。
