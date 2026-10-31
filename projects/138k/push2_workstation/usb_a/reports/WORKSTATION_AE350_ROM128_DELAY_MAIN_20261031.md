# AE350 完整 ROM128／Delay Reporting 父级复验

2026-10-31，主树 `525ead1`，导入作者 `f9a4052409229aa8073bd1099f9b5fb379641657`。
本阶段沿用明确的 ROM128 实验，不改变默认或 accepted 固件容量。
机器记录：`workstation_task_20261030/ae350_rom128_delay_main.json`。

父级以显式 xPack GCC 15.2 前缀重新编译全部 25 个链接单元，无 GC／LTO。
ELF、BIN、ROM 与作者封存版本逐字一致，分别为：

- ELF `6c4b8bfe19ab3ca51caa6863d46e7ea9168381eb3667668c8515c254e446f3da`
- BIN `053be0565c6bb923be9ebab2285e2f24ba3093d8cc93523acdd5ed17b756501c`
- ROM `4eb21507d0685b4aba95c5a0d3670ded1e879db1aa4a1c8a8e84463a3b943a86`

BIN 83,488 B，实际加载 payload 65,136 B；ILM 代码／常量 46,576 B，
扣除末字后余 18,956 B；DLM 静态跨度 8,480 B，预留 16 KiB 栈后余 40,416 B。
完整保守栈上界 1,808 B，115 个可达函数、38 个直接远调用、77 个审查间接点。
实际调用图、回调表、启动／协议／SBC 指令模型和四种 hash seed 结果均与作者一致；
调用图编译位置只在确认两个确切构建根之后按相对位置比较，行／列／函数／栈值保持。

49 项容量／分区／本地启动／存储／栈／accepted 回归通过。
作者校验器另从封存源真实重建镜像，重放 12 项分区测试通过。
六个 native profile 只刷新确定性调用图 helper 的来源哈希，随后实际新 prepare：

| 配置 | 新候选后缀 | staged／enabled | 继续使用的 ROM |
|---|---|---:|---:|
| business revision 3 | `c1751488445e0c8f` | 613／271 | 64 KiB |
| 默认 revision 5 | `60fa7d66fc6db9a4` | 580／260 | 16 KiB |

全部 staged 字节核验通过，业务来源 8 项和默认 profile 21 项通过；默认历史入口 1 项
opt-in 跳过。以上共 78 项实际成功，不把作者重跑计为新增用例。

父级包 `~/.cache/gw138k-task-20261030/ae350-rom128-delay-main-parent-v3`：
seal `f1d676bf7926477440d7ba0b4f4ad5d37f2a92bf6504567119ffb33f67a3e779`，
269 份源快照、1,948 个固定外部文件，`verify.py` 通过。
两个封存前失败尝试保留，原因分别为绝对构建路径差异和计数字段类型，未覆盖旧封存包。

ILM／DLM 容量已实际计入本镜像；I／D Cache 仍关闭，PMA／DMA 一致性、CPU 周期、
最长服务间隔、实际 HCI／PCM 传输和手机互通尚未验收。
本阶段无新综合、P&R、板卡操作或 SRAM／Flash 部署；不转移旧存储综合的精确成本。
后续 BSRAM 分配须与退出的 RTL 业务同功能对照，分列综合与物理资源。
回退为保留现有已选 profile；实验未成为生产构建的隐含输入。
