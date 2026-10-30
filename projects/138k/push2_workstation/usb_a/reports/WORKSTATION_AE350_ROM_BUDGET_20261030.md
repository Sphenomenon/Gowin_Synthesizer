# AE350 mailbox 子集 ROM 预算实验（2026-10-30）

当前维护 recording-API 固件实际为 14,140 bytes，原 16 KiB ROM 剩余 2,244 bytes。独立实验保留原 16 KiB ROM／8 KiB RAM、全部 18 个旧 public symbol，并将 configure／result／step 三个 pump 入口显式保留；缓存副本在 UI 中实际调用 step。没有通过删除既有服务或使 pump 不可达来得到 fit。

| 编译配置 | 原服务 bytes | 加 pump 子集 bytes | 加入后 ROM 剩余 |
|---|---:|---:|---:|
| O2＋GC | 14,156 | 链接溢出 | −1,996 |
| O2＋LTO＋GC | 14,184 | 链接溢出 | −1,520 |
| Os＋GC | 12,140 | 15,744 | 640 |
| Os＋LTO＋GC | 12,116 | 15,220 | 1,164 |

该 pump 仅包括 probe／context／open／read_request／claim／complete／observe 的实际使用子集。owner／ACK bridge、启动及命令解析仍需代码；既有 UI 轮询／绘图未给出有界调用间隔。因此实验不证明完整 S1b 业务、服务期限或完整固件容量已经成立，也未选择生产编译参数。

Os＋LTO 版本 BSS 为 284 bytes，静态 RAM 结束地址 796，距栈顶剩余 7,396 bytes；最大单函数 services_main frame 352、pump frame 176 bytes，不等于完整调用链栈上界。ELF／BIN 重复构建相同，clock／recording／mailbox 三组 Os＋ASan／UBSan 主机回归通过。父级重新核对整个独立 seal 及当前固件／测试来源，见 [ae350_mailbox_rom_budget_parent.json](workstation_task_20261030/ae350_mailbox_rom_budget_parent.json)。

默认固件和链接脚本未变；本阶段没有新整机 prepare、综合、P&R 或板卡操作。回退无需更改生产输入，实验只保存在列明的 cache。后续 AE350 业务迁移须同时完成 owner、桥、解析、调用期限和完整固件验证，不能把本表作为完成声明。
