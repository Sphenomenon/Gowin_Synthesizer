# Classic 安全会话源码父级集成

导入作者固定 `45ef475` 为主树 `28b9f00`，以显式 xPack GCC 15.2 重新运行实际 C fixture。
native 与 ASan／UBSan 各通过 14,445 个检查和 4,000 个有效封包 fuzz；
26 个行为 mutant 全部拒绝。一个被第二道 guard 遮蔽的单删除控制明确预期通过，
不能计作 killed；同时删除两道 guard 的历史晚到事件复现仍被拒绝。
首轮父级 mutant 失败记录保留。

本批覆盖断开后未保存新密钥的清理、合法 HCI Disconnect reason、
旧 CommandStatus／ACL／密钥／PIN／IO 事件不得复活失效 generation 或产生旧应答。
此前 Delay 11,199、Classic 49,640 个 native／sanitized 检查以及 11 个 SBC 参考例继续通过；
这些源码 fixture 不等于实际手机的配对、认证或播放测试。

xPack 下安全 owner `.text + .rodata` 为 11,564 字节，owner／command／bond 对象
为 540／48／32 字节，单函数最大 frame 64 字节。作者另一编译器的 11,876 字节记录保留，
不混用精确成本；对象体积和单函数 frame 不构成完整链接、回调调用链栈或周期预算。

默认策略保持 SSP Mode 4 Level 2、NoInputNoOutput、GeneralBonding，
无 MITM／SC／旧 PIN。原子持久化回调尚无实际存储后端，缺少后端时 fail closed，
不把 RAM 密钥称作持久化；显式 NoBonding 会话属于独立后续工作。
本批未选入实际 native HCI／PCM 路径。既有 business `b552eccb` 和默认 `4e5dfeea`
prepare 均重新核验通过，编译输入和来源选择保持各自固定身份。

父级包 `~/.cache/gw138k-task-20261030/b04-security-main-parent-v1` 保存 51 份输入源码快照、
400 个固定输出／工具／检查文件，seal
`5d537e4b2a55f2ef83e3a8295e544ecf0d7b7453531b0b77a676916d94b2a7e3`。
机器索引见 [b04_security_main.json](workstation_task_20261030/b04_security_main.json)。
无 EDA、板测、SRAM 或 Flash 操作；不能升级 B04 的整项验收。
回退可移除本批未选中的源码；实际集成须使用新候选和完整运行证据。
