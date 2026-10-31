# AE350 ROM128 / ILM64 / DLM64 分区执行实验

2026-10-31，独立源码基线 `5eed03e25aef3df4525e6857606f94533f1b7122`。
这是未选入工作站 profile 的可执行布局实验，尚未综合、P&R、上板或部署。
机器记录见 `workstation_task_20261030/ae350_rom128_split_source.json`。

## 实际布局

| 区域 | 范围 | 实际用途与占用 |
|---|---|---|
| ROM_LOAD | `0x80000000–0x8000ffff` | 原 loader、ILM 加载副本、DLM 初值，共 47,184 B |
| ROM_COLD | `0x80010000–0x8001ffff` | `classic_service.o` 与 `ui_render.o` 的代码，共 16,752 B |
| ILM | `0xa0000000–0xa000ffff` | 原业务、全部 SBC decoder 与常量，46,576 B；末字预留后余 18,956 B |
| DLM | `0xa0200000–0xa020ffff` | 前缀 256 B，静态 8,448 B，栈 16,384 B，余 40,448 B；无 heap |

实际 BIN 为 82,288 B，其中 18,352 B 是两个 ROM bank 之间的地址空洞；
真实 ELF 加载 payload 为 63,936 B。容量检查分别核对物理容量、payload、空洞和运行跨度，
不再用 `GNU size text+data == BIN bytes` 这一单跨度假设。
这只是代码放置试验；classic 协议处理是否适合慢总线取指，需要真实 CPU 周期与实时负载测量。

128 KiB 对应现有掩码式 ROM 地址译码的二次幂容量。96 KiB 在本实验明确拒绝，
不能只替换容量数字而保留掩码。native ROM 增加显式 128 KiB 参数支持，
默认仍为 64 KiB；既有 profile、普通固件 staging 和 `decode_rom` 继续只允许原 16/64 KiB。
新 linker 和 driver 均未接入这些选择路径。

原 `start_ilm_dlm.inc` 未改。它仍检查 ILM/DLM 几何与 cache 关闭，清空本地存储，
复制并读回热代码和 DLM 初值，再执行 fence.i。冷代码不被复制到 ILM。
指令/数据 cache 继续关闭；本实验没有把 cache 当普通 SRAM，也没有扩大硬核 ILM/DLM 几何。
外部 BSRAM 的实际物理块数、布线压力与可用余量尚须整机综合和布局布线核对。

## 保留来源与实际校验

25 个实际编译单元保留原 UI、时钟、录音、业务 mailbox/BLE owner、完整 classic、
SBC service 和 14 个 Apache OI decoder 源文件。未启用 GC 或 LTO。
版本化预算 harness 仅在私有输出副本的 `ui_main.c` 加两处唯一锚点，保活全部 API；
原业务初始化和循环继续执行。该 harness 仍是实验输入，真实 transport owner 完成后须退出。
上一个 63,792 B 组合预算也只证明强制保活下的链接/调用图容量，不能视为 transport 运行闭环。

实际 xPack GCC 15.2 RV32IM/Zicsr/Zifencei 编译，两个独立输出的 ELF/BIN/ROM 哈希相同：

* ELF：`729794de24b7e669ba562e3360ca172614944187d391aa5a3c8c6ca57eb34b86`
* BIN：`4368c2365201e57feec031c649e42f096f6d71370f4baed24b85cfcd1e91da92`
* ROM：`bf75b3d3bb25701ed85677f2e11d486690de1f4815ea78f55cc76ea058dcbfd4`

严格指令模型执行真实 loader 和生成机器码，跨 ROM→ILM→ROM 调用 memset，
运行 classic init/begin、ACL 信令请求、真实 L2CAP 响应和 TX 生命周期。
随后对全部 11 组现有 SBC 参考向量各解码两帧，覆盖 3,712 个 PCM 标量样本，
最大误差 5 LSB。模型实际执行 60,308 条 RV32M 指令；这不是实测 CPU cycles。
本子集观测栈 304 B，完整静态调用图上界 1,792 B，两者分开记录。

调用图含 112 个可达函数、77 个完整审查的间接 JALR 和 35 个直接远调用。
远调用只接受相邻实际 AUIPC/JALR 指令字计算出的确切函数入口，并继续要求 GCC 图边闭合；
不依赖 objdump 注释来替代实际目标。四张实际 ELF 回调表逐字比对源目标集合。

共 47 项针对性检查通过：新分区 10、local-memory 12、boot-storage 4、
callback-stack 4、accepted 来源 17。负例包括实际 64/96 KiB 链接、缺失真实 decoder、
实际 ILM/DLM 溢出、栈不足、间接点缺漏、修改 AUIPC 但保留旧注释、删除 GCC 远调用图边、
ROM 上半区别名、cache/几何不符、复制损坏和缺少 fence.i。
RTL 仿真遍历新增 ROM 的全部 32,768 个字并核对区外和 idle 行为；原 16/64 KiB 行为回归通过。

复现入口：

```sh
python3 tools/experiment_ae350_rom_split.py --output /absolute/new/output --riscv-prefix /path/to/riscv-none-elf
GW138K_ROM_SPLIT_OUTPUT=/absolute/new/output python3 sim/test_ae350_rom_split.py -v
```

输出必须是新目录。独立封存包位于
`~/.cache/gw138k-task-20261030/ae350-rom128-split-parent-v1`，其 verifier 复核来源、
实际 ELF/BIN、调用图、表和指令模型。未修改冻结基线或既有封存包。
回退为继续使用现有 profile/linker；新增源码尚无生产选择点。

## 尚未完成

本实验没有 HCI/安全配对/手机互通、完整音频 transport、实际 CPU 吞吐、DMA 可见性、
整机 BSRAM/CDC/时序或 SRAM/Flash 验收证据；没有提升此前 classic 实验的协议完成度。
128 KiB ROM 只是可执行容量候选，不能因为离线检查通过就成为部署身份。
