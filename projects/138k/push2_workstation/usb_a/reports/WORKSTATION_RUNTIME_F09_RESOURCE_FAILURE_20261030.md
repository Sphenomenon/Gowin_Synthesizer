# F9：第二次有效资源 P&R 失败（2026-10-30）

F9 使用[已审准备](WORKSTATION_RUNTIME_F8_PHYSICAL_F9_PREPARE_20261030.md)的同一 sealed f1be VG、F8 SDC 和 CST，仅算法为 place4/route1、UserCode 为 `C11030F9`，replicate=false，保留全部功能。实际运行于 14:36:34—15:40:29（Asia/Shanghai），工具返回1，耗时 3,835.380 秒，完成布局后报 **PR0004：32,709 条未布通网络**。没有位流或完整 routed STA，不是约束语法失败，也不是超时。

| 项目 | F8 place2/route0 | F9 place4/route1 |
|---|---:|---:|
| 未布通网络 | 8,083 | 32,709 |
| Logic | 121,552 / 138,240 | 121,558 / 138,240 |
| Register | 61,345 / 139,095 | 61,345 / 139,095 |
| CLS | 67,110 / 69,120（报告98%） | 67,752 / 69,120（报告99%） |
| 物理 BSRAM | 298 / 340 | 298 / 340 |
| DSP | 202 / 298 | 202 / 298 |
| PRIMARY / LW | 各8 / 8 | 各8 / 8 |
| PLL | 7 / 12 | 7 / 12 |

物理失败输出 VO 不能作为已布通或时序接受。输入清单 SHA256 为 `d3fcdd0a126c0102acb439ca96e58098af3f22f85089141e7630ee2e913da7e6`，27 项登记输入、日志和六项输出均由父级事后独立重验；输入保持。报告 TXT SHA256 为 `7e520c4724b7efc4638f92f019772104fe1a4451fc7cb4488538dd489d9a2ebc`，失败 VO 为 `3beefc1fce4a1c7986367eceb3488f3b703d4b29661c632657b89d6abc477449`。完整 process、输入/输出哈希、日志及资源报告见[机器证据](workstation_task_20261030/runtime_rev5_f9_resource_failure.json)。原目录 `/Users/sphenicidition/.cache/gw138k-task-20261030/runtime-rev5-physical-C11030F9` 保留，不追改输入。

F7 在布局前因空 query 失败，不计资源尝试；F8/F9 为两次有效资源失败。因此已满足用户“尝试两次后仍难布局布线，可舍弃 CNN/曲谱引导”的条件。下一候选采用独立显式 no-CNN profile 和新身份，旧 profile/accepted/pinned/default 仍维持原功能。裁剪必须保留实时音频与效果、TF 原始操作/停止、手工 cue/local score、PC UART、公共参数、FFT/波形/X-Y、Flash guard 和非 CNN 状态；共享存储地址不回收。具体实现和实际资源收益另行验证，本报告不宣称已经裁剪或释放任何 PLL/时钟通道。

新 PCM 约束及待提交的控制 level 注册修复不在 F9 输入中，不能移用 F9 物理结论；下一源码候选必须重新 prepare、综合、完整 CDC/reset/PLL、双模式 routed timing 和功能/硬件检查。本阶段没有 JTAG/SRAM/Flash 操作。回退仍使用原已接受身份和部署记录，不以 F8/F9 失败产物部署。
