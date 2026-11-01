# Raw DDR 最后一级 global failure cofactor（2026-11-01）

维护源码已采用只针对最后一条 `memory_failure` 写入的组合 cofactor。已知 `bridge_fault=1` 直接选择 TRANSPORT7；已知0保留 command-timeout5 → read-timeout6 → protocol8 的错误优先级，X/Z 保留原 `memory_fault_now` 过程式 guard 和三元合并。没有新增时钟状态或延迟。lower failure 写入、channel／cancel、即刻 owner8 transport 拒绝与32位 completion 都保持原位置和行为。

新 raw SHA256：`b654b55a47e017aec5f3c386f26cb2aac34f311bdb564852cf047c24dc1c3809`。唯一构建消费入口 `tools/workstation_bluetooth_ddr.py` 的 raw pin 已同步；完整旧39ae源码保存在 `sim/memory/fixtures/workstation_ble_raw_ddr_store_before_global_failure_case.sv`。独立 runner 严格校验新旧身份及整个 source inverse；原 CLEAR／两 START 门禁先反演这一层，再执行原来的 fixture、guard、完整 twin 与全部负控。16个原 proof helper 函数的 AST 完全相同。

| 校验 | 结果 |
|---|---|
| 新 global guard／错误码／任意4位 prior nextQ | 二态UNSAT；1024四态 guard＋262144四态 prior nextQ |
| 新 global 全模块 twin | 661577 edges；24输出／115原reg声明／180共同信号，真实FIFO／cache／native bridge |
| 新 global 任意状态与负控 | 35 directed＋4096四态内部状态；6项破坏性对照全部拒绝 |
| 原 CLEAR 与两 START | 原二态／四态／完整 twin／全部负控保持通过；CLEAR和最早START各保留16777216实际fault组合 |
| 原 raw suite | 94766／93238 checks、16384帧／8112-byte fetch；5负控＋精确4条lint警告 |
| BLE业务整合 | 24／24 owner cases，protocol6、chain3；27来源／输出／证据负控 |
| native DDR／owner8／authority | 27 native scenarios＋6 bridge fault＋11负控；owner3 tests；authority10 phase＋6负控 |
| 来源边界 | current-workstation17 tests；diff --check通过 |

cache提案的主seal `3c171a8c32f6190b194dc233f36e47e7ea84e6cb04e35956e7f5ef26a3613c30` 绑定50实际产物、9声明输入、6原snapshot输入及10 compile/run cases。维护版首轮在第二项负控构造前因三引号字符串额外缩进被精确anchor拒绝，失败产物保留；最终runner恢复原6组字面量后完整重跑通过。START factor在已通过运行后仅清理一处空白行；旧输入字节已封存，逐行rstrip／AST相同、py_compile及strict inverse重验通过。global module修复只改main内的负控字面量，其余AST保持；旧CLEAR／START不重复16m遍历。这些版本区别均在机器记录和source snapshot中明确记录。

这是源码及离线验证阶段；没有新综合、P&R、板测、SRAM或Flash操作，也不声明资源／时序收益。W14原映射最差路径工具标记15级，14个tINS中route占70.810%；只读逐级／长连线／采样占位审查已封存。现有可读资料不足以证明一个空闲且合法的紧凑region，因此没有添加CST。32位completion／初始化许可锥及即时owner8/tag前缀仍是后续实际映射重点。

机器记录： [dual138k_raw_global_failure_case_20261101.json](dual138k_raw_global_failure_case_20261101.json)。该记录绑定最终维护输入、所有通过及首轮失败证据、style转换证据和不可变input snapshot。回滚按本阶段7文件diff恢复39ae及其唯一pin；历史候选和本次证据保留。W15资源、STA和硬件状态由独立的新候选证据记录。
