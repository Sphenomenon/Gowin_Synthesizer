# AE350 现有业务＋classic／SBC 完整链接与存储预算

2026-10-31，固定源码 `5eed03e25aef3df4525e6857606f94533f1b7122` 的隔离预算实验。保留全部既有 second-batch 固件业务，加实际 classic、SBC service 和14个 Apache OI decoder C文件，共25个编译单元，真实 RV32 链接成功。冷启动镜像只余 **1,744 B**，ILM可用余 **2,348 B**；DLM尚余 **40,448 B**，栈余量充足。后续优先扩展程序冷存储，并继续使用空闲 DLM 放工作区；不能把缓存容量直接当作本地 RAM 相加。

本实验不是可部署固件。隔离 `ui_main.c` 两处精确 anchor 接入一个预算适配器，用 volatile 输入使全部 classic 公共 API 和实际 decode／reset 路径保持可达；原 UI、clock、recording、mailbox、BLE C owner 均保留，未使用 LTO／section GC。状态、收发 packet 和四块 PCM 短队列真实进入 DLM，但适配器没有真实 HCI lease／安全／rate grant／PCM交接。它证明此固定源码的容量和调用栈，不证明协议或音频运行闭环。

| 实测项 | 原 second-batch | 加入实际 classic／SBC | 容量与余量 |
|---|---:|---:|---|
| 冷启动 BIN | 29,808 B | 63,792 B | 64 KiB，余1,744 B |
| ILM code＋rodata | 29,200 B | 63,184 B | 64 KiB；保留末word后余2,348 B |
| DLM initialized data＋BSS | 624 B | 8,448 B | 保留256 B前缀和16 KiB栈后余40,448 B |
| 保守调用链栈 | 1,344 B | 1,792 B | 16 KiB预留，余14,592 B，非硬件高水位 |

组合 `.boot`592 B、ILM `.text`61,200 B／`.rodata`1,984 B。真实 RV32 对象包含 classic2,848 B、decoder context＋workspace1,996 B、4×528 B PCM槽共2,112 B，其余为252 B输出frame、296 B TX、280 B输入packet及32 B volatile控制。布局对齐后静态增量7,824 B。四块PCM仅512 stereo frames，约10.67 ms@48k／11.61 ms@44.1k；这是容量预算，尚无抖动／漂移或期限接受。

维护容量／ELF门禁对实际PT_LOAD重建与BIN一致，未定义符号为零。调用链由152个静态compilerframes和真实反汇编构造，112个根可达函数，24个关键入口均实际可达；77个可达JALR包含原业务73与SBC4，四个ELF函数表逐word核对目标地址。保守峰值1,792 B，未知间接目标、动态栈、递归和图外调用均失败。5个实际负控拒绝：栈1,791 B、遗漏JALR、陈旧反汇编、旧16 KiB ROM真实链接、移除真实decoder对象链接。后两项保留GNU ld失败日志，未放宽容量或未定义符号门禁。

完整证据包 `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-combined-fit-budget-parent-v1` 的 `verify.py` 已由父级实际重跑通过：66份源码、315包内文件、1,976外部固定文件及工具；seal `c8609b1a0f397165b0446f68c4475b624419412c2e62bdee5c392dcbe1c32d02`。初次校验把两个并列最长链的见证文本严格比较，受set次序影响失败；新包仅允许并列见证文本不同，峰值、完整可达闭包和其余全部proof字段仍严格相同，并保存四个hash seed的重算回执。另一次只读常量搬DLM的预测尺寸断言失败已停止，不计本表结果。机器记录见[完整预算](workstation_task_20261030/ae350_combined_memory_budget.json)。

ILM／DLM硬核容量仍各64 KiB，I／D Cache保持关闭。Mandatory Delay Reporting、安全／连接策略和真实 adapter尚未计入；当前链接余量不能作为最终fit。常量移DLM可缓解ILM，却不会自动减少冷BIN。后续128 KiB外部BSRAM ROM与ILM热代码／ROM冷代码必须另验地址窗口、loader、真实跨区调用和完整栈；新增BSRAM和CLS净变化要由同功能整机综合／P&R实测，不能从历史245块直接推导剩余容量。

此阶段没有生产profile变化、EDA、SRAM／Flash或板卡操作，也没有CPU周期／最长服务间隔、该组合的硬件本地存储／Cache-DMA、手机和物理声音接受。C9独立探针的启动摘要不能转移为这份预算固件的硬件验收。
