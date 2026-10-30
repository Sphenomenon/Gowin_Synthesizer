# no-CNN FA：首轮资源 P&R 失败（2026-10-30）

`C11030FA` 的实际 P&R 于 16:46:44—16:58:44（Asia/Shanghai）运行，返回 1，耗时 719.840 秒。工具完成布局后报告 **PR0004：556 条未布通网络**，没有位流或完整 routed STA；这是路由失败，不是超时。输入为[已审准备](WORKSTATION_NO_CNN_FA_PHYSICAL_PREPARE_20261030.md)的 `custom138k-workstation-no-cnn-v1-525ffff10d622031`，place2／route0、replicate=false。

| 物理资源 | 实际占用 | 报告利用率 |
|---|---:|---:|
| Logic | 102,591 / 138,240 | 75% |
| Register | 51,122 / 139,095 | 37% |
| CLS | 61,804 / 69,120 | 90% |
| BSRAM | 272 / 340 | 80% |
| DSP | 126.5 / 298 | 43% |
| PRIMARY、LW | 各 8 / 8 | 100% |
| PLL | 7 / 12 | 59% |

综合 BSRAM 245 与物理 BSRAM 272 是不同口径。相较保留 CNN 的 F8／F9，no-CNN 的实际资源压力下降，但注册控制修复也已改变 RTL，不能把差值全归因于关闭 CNN；路由和完整功能均未接受，时钟通道仍满。后续只在独立候选中探索物理算法，不放宽时钟或时序例外，不将失败 VO 当作已布通产物。

父级事后独立重验全部 18 项登记输入、六项输出、工具和日志，均与原 manifest／process 一致；另确认磁盘无 FS。输入 manifest SHA256 为 `5a595a358d0d539d75ad6f305c745850968eb914b2a2b4d3d1f0837fef24cc40`，process 为 `c107903a13d777d2a58e3588f1ddb5d0c0e1cefb5de3218967af73ca2a1a84c7`，TXT 报告为 `bfe305edf7f49a1dac6be6049d99f464a9d5d1555d1c0c614084e41799c6367b`。完整输入、输出与资源证据见[机器记录](workstation_task_20261030/conditional_no_cnn_fa_resource_failure.json)。原目录 `/Users/sphenicidition/.cache/gw138k-task-20261030/no-cnn-physical-C11030FA` 保留，旧准备记录不改。

随后 PCM 检查器的新 prepare `60cae14e43255a2b` 与本候选 staged 相同，但身份不同且尚未综合；本结果不改名继承。完整 CDC／复位、观察 RAM 数据时序、PLL、双模式 routed timing、功能／电气与硬件仍未通过。没有 JTAG、SRAM 或 Flash 操作，所有部署门禁保持 false；回退仍引用已有接受和部署记录。
