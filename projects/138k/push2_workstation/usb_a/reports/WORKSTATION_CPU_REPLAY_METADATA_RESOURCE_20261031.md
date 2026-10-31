# 回放元数据：同功能组件综合资源对照

固定主树 `d745697`，沿用[主树功能复验](WORKSTATION_CPU_REPLAY_METADATA_BSRAM_MAIN_20261031.md)
生成的 before／after 输入，各运行一次实际 Gowin V1.9.12 综合。两次均退出 0，
输入及工具哈希前后保持；耗时分别为 33.645／33.769 秒。
顶层适配只改变 distributed／block 参数，业务接口、容量、源时钟与其余组件相同。

| 工具资源项 | before | after | 变化 |
|---|---:|---:|---:|
| Logic | 10,506 | 10,250 | −256 |
| LUT | 8,531 | 8,517 | −14 |
| ALU | 1,663 | 1,661 | −2 |
| RAM16 | 52 | 12 | −40 |
| Register | 6,057 | 6,066 | +9 |
| 综合 BSRAM | 7 | 10 | +3 |

Logic 是工具的 LUT＋ALU＋6×RAM16 口径，不能把 −256 表述成 LUT 或物理 CLS 节省。
实际网表的 `g_block_metadata.ids/times/sizes` 分别连接一块 32／32／16-bit SDPB，
32 个地址、同一 50 MHz 输入时钟、同步 bypass 读、完整写掩码，复位端保持无效；
三个 metadata module 内没有分布式 RAM 原语。其余数据路径仍使用自身存储。
旧宽度截断警告分别 17／16 条，均无 AG 组合环诊断，不据此宣称完整时序或 CDC 通过。

父级封存包 `~/.cache/gw138k-task-20261030/cpu-replay-metadata-cell-resource-parent-v1`
保存独立审计器、过程记录及 37 个外部文件身份；seal
`9d98874d38ec86c608b2c016f324b01c1344f00ca86e2b2e7b2e2d464d72dc9f`，
`verify.py` 复验通过。机器结果见
[cpu_replay_metadata_cell_resources.json](workstation_task_20261030/cpu_replay_metadata_cell_resources.json)。
前序真实 parser、官方 SDPB 模型和 C／APB 回归继续引用各自冻结证据。

本阶段只测得组件综合变化。整机同功能对照、物理 BSRAM／CLS、布线、routed 时序、
手机音频与硬件接受分别留待对应候选；没有位流、板卡操作、SRAM 或 Flash 部署。
回退为原 distributed 参数路径及其固定来源，不能把本结果转授给其他 profile。
