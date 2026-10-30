# R00 无本地面板 FE 路由失败（2026-10-30）

`0xC11030FE` 资源实验完成，Gowin 返回 1，报告 `PR0004: 2235 unrouted nets`。本次未生成 FS、TR 或 SDF；setup、hold、recovery、removal、MPW 全部为 null，不把缺失结果记成零余量或通过。没有操作板卡。

实际源为 `custom138k-workstation-r00-no-local-panel-v1-e855a1e8a8e6f181`，VG SHA256 `086d2504f1287e226fd55641a3e68c52f632dd91e87044b849a7a29af38ba02e`。place=1、route=0、replicate=false，timing_driven=1、correct_hold_violation=1；使用原始封存 SDC、维护的 ULPI nominal CST appendix，没有放宽时钟或异常路径。本地 LCD／touch 和 CNN／follow 的显式范围来自已记录的用户选择。

父级独立解析器重新核对 27 项物理输入、584 项固定 staged 输入与六项登记输出，均保持；另核对 source profile／process／VG、物理 manifest 与运行日志。实际用时 1,145.371 秒，结束于 `2026-10-30T12:14:52.490089+00:00`。原始准备接受不升级为路由接受，历史 shared 检查器失败和 PCM reply 漏覆盖仍保留原身份。

| 物理资源 | FD | FE | 差值 |
|---|---:|---:|---:|
| Logic | 104,774 | 103,613 | −1,161 |
| Register | 63,006 | 58,602 | −4,404 |
| CLS | 63,358／69,120 | 62,068／69,120 | −1,290 |
| BSRAM | 274／340 | 288／340 | +14 |
| DSP | 121.5 | 120.5 | −1 |

FE 的 CLS 为 90%、物理 BSRAM 为 85%；综合报告的 253 BSRAM 与这里的物理 288 是不同计数。PRIMARY、LW 仍各占 8／8，PLL 为 6／12。FD→FE 同时改变 tag RAM 与本地面板配置，不能把所有差值归给单一改动，也不能由未布通总数 2,754→2,235 推断具体失败网络或旧关键路径已消除。当前文本／HTML／日志只提供 aggregate PR0004，没有可核验的逐网络失败归属。

输入、输出、解析器哈希及完整资源／时钟表见[机器记录](workstation_task_20261030/r00_no_panel_fe_route_failure.json)。本机证据目录为 `/Users/sphenicidition/.cache/gw138k-task-20261030/r00-FE-parent-completed-review-v1`；物理原目录为 `r00-tag-ram-no-local-panel-physical-C11030FE`。部分 post-P&R VO 只供结构研究，不是已完成路由的网表。

后续先完成 PCM reply 的 D／CE 配对约束与有效 next-Q 证明、owner8 录音跨域／复位审计，再以新来源和未使用身份准备物理候选。FE 没有位流可部署或回退；既有部署证据不变，本报告不推测此刻 SRAM／Flash 内容。完整 CDC、复位、物理时序、功能、硬件和部署接受均保持 false，任务方框不提前勾选。
