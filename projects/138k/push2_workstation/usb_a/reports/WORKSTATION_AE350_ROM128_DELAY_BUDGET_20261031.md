# AE350 ROM128：Delay Reporting 全量预算更新

2026-10-31，源码基于 `1ff14c3b701f9a251635da7fffc7a2a702902991`，另合入 Delay Reporting 作者提交
`3c90448f14a38e8453e3c794de39b22b3d9a5272`。这是新的未选中实验身份
`ae350-rom128-delay-budget-v1`；旧 ROM128 封存包和已验收候选均保留。
机器记录：`workstation_task_20261030/ae350_rom128_delay_budget_source.json`。

## 实际容量

25 个链接翻译单元全部重新编译，保留 UI、时钟、录音、业务 mailbox/BLE owner、
完整 classic、SBC service 和全部14个 Apache OI decoder 源文件；无 GC、无 LTO。
`tick` 在每轮实验 step 前调用，`delay_update` 由实际 switch 入口保活，
两者均从 `services_main` 可达，且存在实际跨区 AUIPC/JALR 调用。

| 指标 | 此前 ROM128 实验 | 含 Delay Reporting 的本次完整镜像 |
|---|---:|---:|
| BIN 文件 | 82,288 B | 83,488 B |
| 实际加载 payload | 63,936 B | 65,136 B |
| ROM 两 bank 间地址空洞 | 18,352 B | 18,352 B |
| ROM_COLD 代码 | 16,752 B | 17,952 B |
| ROM_COLD 可用余量 | 48,784 B | 47,584 B |
| ILM 代码与常量 | 46,576 B | 46,576 B |
| ILM 扣除末字预留后的余量 | 18,956 B | 18,956 B |
| DLM 静态跨度 | 8,448 B | 8,480 B |
| DLM 预留16KiB栈后的未分配区 | 40,448 B | 40,416 B |
| 全部预算适配对象 | 7,816 B | 7,852 B |
| 实际 RV32 classic 对象 | 2,848 B | 2,876 B |
| 完整静态调用图栈上界 | 1,792 B | 1,808 B |
| 可达函数 / 直接远调用 / 审查间接点 | 112 / 35 / 77 | 115 / 38 / 77 |

对象大小来自实际 RV32 ELF `nm -S`，另用同编译器、同头文件编译但绝不链接的
`ae350_budget_abi_witness.o` 提供 `sizeof` 符号见证。六个真实缓冲区、十个控制变量、
四个528B PCM槽逐项核对，拒绝把旧2848B数字直接继承给新结构体。
额外见证单元不计入25个链接单元，也不占实际镜像。
DLM 静态跨度增32B而预算对象合计增36B，是实际链接对齐变化；二者分别记录。

ILM/DLM 仍各64KiB，启动代码、CSR几何检查、末字预留、栈和 cache-off 策略未改。
本次把现有 ILM/DLM 空间实际计入预算；I-cache/D-cache 仍关闭。
缓存提速还需缓存维护、DMA一致性和真实CPU负载验证，不能把缓存直接记作通用RAM容量。
额外BSRAM分配和扩容的物理块数、CDC/时序由后续独立整机候选验证，本包无此结论。

## 机器码与失败门禁

真实启动模型执行生成指令，继续校验清零、复制、读回与 fence.i。
除了既有 classic ACL/TX 和11组SBC参考向量各两帧，本次从 ROM_COLD 实际执行
`tick`、`delay_update`、ACL分片信令协商、DelayReporting配置与首报。
逐字断言报告 `05007000000d8c1234`，Accept后允许改值，第二报
`05007000100d8c1235`；outstanding期间更新返回BUSY。
独立tick按不超过100ms间隔推进，在1200ms精确截止处fence，随后迟到Accept仍被拒绝。
输入延迟是测试值，没有声称物理延迟测量或手机互通。

SBC仍核对3,712个PCM标量样本，最大5LSB误差；模型执行60,312条RV32M指令。
本模型子集观测栈336B，不能替代完整1,808B保守栈上界或板上watermark。
77个可达间接调用点继续完整绑定来源、调用者、指令字和目标集合；四张ELF回调表逐字核对。

实际编译三种负例：去掉tick入口、去掉delay_update入口、见证对象故意少4B。
前两者仍有导出函数并链接成功，但完整可达性门禁拒绝；后一例真实镜像不变而ABI门禁拒绝。
原真实ROM64/96失败链接、缺SBC实现、ILM溢出、DLM覆盖栈、栈不足、
缺漏/漂移的间接审查、篡改AUIPC保留旧注释、删除GCC远调用图边、
ROM上半区别名、cache/几何/复制/fence错误门禁均继续通过。

修复调用图同成本分支见证受Python集合顺序影响的问题：仍取最大栈成本，
仅以调用链tuple字典序明确tie-break，保留所有边与计费。
四种真实 `PYTHONHASHSEED=0,1,17,random` 计算的完整调用图结果逐字一致。
涉及本helper的native profile锁更新由父级集成阶段统一处理，不在此篡改冻结输入。

49项回归通过：分区12、local-memory12、boot-storage4、callback-stack4、accepted来源17。
两次独立构建的ELF/BIN/ROM一致：

* ELF：`6c4b8bfe19ab3ca51caa6863d46e7ea9168381eb3667668c8515c254e446f3da`
* BIN：`053be0565c6bb923be9ebab2285e2f24ba3093d8cc93523acdd5ed17b756501c`
* ROM：`4eb21507d0685b4aba95c5a0d3670ded1e879db1aa4a1c8a8e84463a3b943a86`

复现：`tools/experiment_ae350_rom_split.py --output /absolute/new/output --riscv-prefix /path/to/riscv-none-elf`，
再以 `GW138K_ROM_SPLIT_OUTPUT` 指向输出运行 `sim/test_ae350_rom_split.py -v`。
使用xPack GCC15.2，RV32IM/Zicsr/Zifencei；最终来源和工具哈希在机器记录中。
封存包 `~/.cache/gw138k-task-20261030/ae350-rom128-delay-budget-parent-v1` 的校验器
从新临时源快照实际重建，并重放完整12项分区测试；旧包不变。

现有生产profile/staging继续拒绝ROM128，原loader未启用cache。
本次没有EDA、板卡操作或push，也未完成HCI/安全配对、transport调度、物理音频延迟、
实际CPUcycles、整机资源/时序及SRAM/Flash验收。回退为保留现有已选profile；
实验两锚点overlay须在真实cooperative transport owner接入时退出。
