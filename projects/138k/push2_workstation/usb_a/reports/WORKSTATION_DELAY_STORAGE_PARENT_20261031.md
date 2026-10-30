# Native Delay FIFO 存储选择父级复验（2026-10-31）

原生 `workstation_runtime_stereo_effects.sv` 在自己的 delay 组合处新增两条 `defparam`，选择写／读 FIFO 的 `RAM_STYLE="block_ram"`。当前维护 custom 非 runtime 分支已有对应选择；三个 frozen baseline 没有，不能将本次改动追认为 accepted full83 原有行为。公共 FIFO 源码及默认 distributed 选择保持；本次不改变深度、时钟、端口、状态机、show-ahead、握手或周期延迟。

原 effects provenance 原字节保留。独立 sidecar/helper 只逆去两条插入，恢复原 native hash，再逆原 provenance 得到原 prepared slice，并核对维护的完整 stereo_effects 源。runtime profile 明确记录／复制新策略，artifact verifier 重新计算 metadata，拒绝虚报策略、adaptation 或物理映射。四份 profile 精确应用十项必要源锁增量，同时保留父级较新的 pitch／Chorus 锁。

主仓库 13 项完整 effects 回归通过，包含可逆来源负控、native block／reference distributed 的真实层次检查、双率 wet path、顺序／mask／历史、PANIC、fence 和停钟。修正 Icarus 宏选项顺序后，父级在独占 EDA 锁下重新运行原 storage 两项测试，两项均通过且无 skip：四种深度／时钟比 RTL 检查，以及真正 Gowin 映射后的两组官方原语逐周期仿真。单 FIFO 实际为四 SDPX9B、零 SSRAM，工具／源码／厂商库八项输入前后保持。

独立审查另外复验 128 深度两组时钟比及已完成的映射，证明小分支功能保持；该异步读分支没有使用 RAM_STYLE 属性，不宣称其 BSRAM 推断。默认 65×512 的两 bank 读 head 早已存在，本次不是增加额外时延。当前 6b 两 FIFO 共 1,088 SSRAM 的局部替换目标不能当作整机实际收益。

四份 fresh prepare 各 12 项来源通过：enabled `50b1be7b17d7582d`（579/260）、no-CNN `c7df5286b048d47b`（580/260）、R00 `e24537dd15244315`（592/267）、no-panel `18ed947312186187`（599/269）。staged 仅该 RTL 改变，另增三个非编译来源文件，编译清单、SDC/CST 字节保持。profile21（一项旧 prepare 跳过）和 accepted17 通过。完整来源／seal／工具与测试路径见[机器记录](workstation_task_20261030/delay_storage_parent.json)。

原组件测试的宏排序失败保留，原输入已另存；修后的完整重跑不是 skip 或替换原失败。父级合并时四 descriptor 冲突按精确十 key 增量解决；最初误把 seal 中已有 prepare 前缀重复拼接的校验脚本也已修正，完整 14 源／17 证据／644 prepared／12 外部依赖重验通过。

本阶段只有单 FIFO 组件综合接受；尚无整机 BSRAM／CLS／拥塞净收益。下一固定新候选须核验两个 native 实例实际各四 RAM、完整 payload／Gray／RAM 时序与新 VG 的所有门禁，再 P&R。未改时钟／SDC，未操作板卡，无 SRAM／Flash 部署。
