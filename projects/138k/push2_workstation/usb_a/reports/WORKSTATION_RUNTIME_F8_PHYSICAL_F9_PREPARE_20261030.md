# revision5：F8 资源失败与 F9 第二次尝试（2026-10-30）

F8 完成布局但路由失败，返回 1，用时 2,230.943 秒，报告 **8,083 条未布通网络**。没有 FS 或完整 routed STA；生成的 `.vo` 是失败物理运行的输出，不能作为路由／功能接受。封存输入全部保持，本阶段没有 SRAM、Flash 或其它板卡操作。

F8 是 `f1be50e853d3700a` 网表的第一次有效资源 P&R 尝试，place2/route0、关闭资源复制；保留 CNN、曲谱及全部功能。此前 F7 仅在读取空 BLE query 时失败，不计资源尝试。

| 物理报告项目 | 占用／容量 | 工具报告利用率 |
|---|---:|---:|
| Logic | 121,552／138,240 | 88% |
| Register | 61,345／139,095 | 45% |
| CLS | 67,110／69,120 | 98% |
| BSRAM | 298／340 | 88% |
| DSP | 202／298 | 68% |
| PRIMARY | 8／8 | 100% |
| LW | 8／8 | 100% |
| PLL | 7／12 | 59% |

这是失败候选的真实资源盘点，不是物理通过。综合 BSRAM 268 不能替代本表 298；CLS 和全局时钟资源已明显拥挤。原始报告含 placement、routing 分段时间及 clock signal 明细，保留在[机器证据](workstation_task_20261030/runtime_rev5_f8_failure_f9_prepare.json)。尚未将全部失败归因到某一功能，也没有把 CNN 盘点当成删除后的物理收益。

F9 已以独立身份 `custom138k-runtime-physical-resource-experiment-C11030F9` 准备并启动第二次离线资源尝试。VG、完整 SDC、CST 与 F8 逐字节相同，仍绑定封存 f1be；仅 maintained implementation Tcl 的 UserCode、place option 和 route option 分别改为 `C11030F9`、4、1。没有新 false path、频率放宽、原语改写、功能删减或资源复制。尚未完成的 PCM bridge/context 50 行新提案没有混入本算法对比。

```text
VG SHA256: 8fc53d099ebead55ca3926c8d4b2b45b3504fcb1ac1ed5dbcaa1b6e1a1834535
SDC SHA256: aee25f28eb1ca057e635f4392f7a7fa00b786cdf931afb2f579247098ca5bf73
F9 manifest SHA256: d3fcdd0a126c0102acb439ca96e58098af3f22f85089141e7630ee2e913da7e6
```

F9 prepare 再核对 570 项综合来源、F8 输入／完整输出／失败日志及资源报告、maintained helper 身份和唯一三项 Tcl 差异；27 个成品输入匹配，8 个负控全部拒绝。父级又独立比较成品 VG/SDC/CST/Tcl 及全部注册哈希后启动 runner。**本报告封存 F8 失败和 F9 prepare，不包含 F9 的未来运行结果。** 若它也在资源／路由方面失败，再执行用户已授权的显式 CNN／曲谱裁剪候选，并保留两次失败及裁剪前后差异；本阶段未提前裁剪。

cache 原件为 `/Users/sphenicidition/.cache/gw138k-task-20261030/runtime-rev5-physical-C11030F8` 和同级 `runtime-rev5-physical-C11030F9`。准备脚本源码及完整 F8 日志／报告、F9 manifest／负控均纳入机器证据。重复运行必须使用新目录和身份。该 cache 算法试验不替代主线 `bd40620bb1b139bb` 的来源，退出条件仍是维护入口的新候选及完整 CDC／复位／PLL、STA、功能与硬件门禁。
