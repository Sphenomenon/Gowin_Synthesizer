# PCM 回复 D／CE 适配及 next-Q 证明（2026-10-30）

本阶段独立交付 PCM/context v2 检查器、配对约束提案及回归。四份实际封存综合网表均通过源级审计，各完成 **18 项测试／109 个负控**，无跳过。未修改生产配置、来源锁、已封存 stage、RTL、固件或 vendor；未运行 EDA、操作板卡或部署。生产入口选择 v2、刷新来源锁、prepare 和新综合仍由下一独立阶段完成。

## 实际变化与不变量

R00 `b9a2` 和无本地面板 `e855` 的回复消费者仍是同一组 **197 个 FF／263 个实际依赖 pin**；综合把 `underrun_count_o[0]` 的依赖从 D 移到 CE，把 `wanted_sequence[1,4..30]` 从 CE 移到 D。`wanted_sequence[2,3,31]` 仍在 CE，bit0 仍在 D。原检查器首先拒绝这一闭包变化，本阶段没有删除消费者或过滤未知 FF／MEM。

仅以下 32 个已注册 FF 可选择 D 或 CE：`underrun_count_o[0]` 与 `wanted_sequence[1..31]`。每个必须恰好有一个实际 D／CE 依赖；缺失、两个依赖、第三 pin、新 FF／MEM 均失败。其余 pin 精确不变，完整 FF 投影也精确不变。四组首级完整闭包保持 65／263／141／207；时钟、异步 assertion 及 FF primitive 检查保留。

`paired-nextq-v2` 对这 32 个 FF 同时约束 D 和 CE，回复目标共 295 pins（134 D／161 CE）。仍是 **50 行、13.020 ns**，只改变原回复的两行；新增 32 个相对 pin selector，静态解析总数 896。不新增 reset cut，不放宽时钟或 flight budget。原 263-pin 方案以显式 `legacy-v1` 保留，禁止自动 fallback。

## 独立行为证明

检查器从已知 serializer 状态及 bridge publisher Q 构造期望函数，比较实际 `CE ? D : Q`。全部 32 位 wanted sequence（含保持原 D 形式的 bit0）以及 underrun bit0，共 **33 个 FF** 通过 ROBDD 全赋值等价；没有抽样，也不从目标 D 反推发布者。

逐位递增式为 `next[i] = current[i] XOR (advance AND all lower current bits)`。`advance` 包含 configured、精确双率 half-count 条件、BCK、position63、1,028 帧启动 equality、resume、无 quiesce，以及 playing／next-available。next-available 含 have-next 和真实回复 token／credit／reset／quiesce／rate／sequence／epoch 完整条件。underrun bit0 仅在 advance、无 next-available、32 位计数未饱和时翻转。错误回复仍是 available，不误计为 underrun。

ROBDD 只将已独立核对完整操作数及 GW5A NE 语义的 header carry predicate 作为内部 cut。其他逻辑严格读取实际 LUT／INV，未知 FF leaf、其他 primitive、环、模糊 driver 和资源边界溢出均失败。固定消费者的时钟／复位检查不变。这是上述 next-Q／握手边界证明，不声称重证整个 serializer FSM 或物理复位。

e855 的 request eligibility 还出现故障译码跨层复制：原来以 `compute_fault` net 作 cut 的小锥枚举支持增至 18，超过原 16 上限。本阶段保留原枚举上限，改用同一 ROBDD 展开已检查的命名 fault owner boundary，与固定 renderer／credit／configuration Q 构造的期望函数比较；不增加自由 alias cut。独立反转该 eligibility LUT、保留依赖闭包后，检查器明确拒绝。

## 封存来源与验证

| 实际候选 | staged | VG SHA256 | next-Q 输入／BDD nodes | 实际 reply D／CE | legacy 漏约束 pin |
|---|---:|---|---:|---:|---:|
| registered `1aea3c01fa6c1b14` | 570 | `b8bd2a02e7f073593a9c8e5d7ee8cd15379c779acbbe152a1b901664d5f724b3` | 99／10473 | 103／160 | 0 |
| no-CNN `525ffff10d622031` | 571 | `37c811ffcc0a0ae2ce55aa66550c95bec8bb04cc7fc92aa69c1cc7c17d6f3f4f` | 101／13931 | 103／160 | 0 |
| R00 `b9a2e0fdf36970be` | 584 | `f71d0328da2a5dc2c5487ece298d38ab59761aa97ca76c6bdb80d6bce7f9dc80` | 99／10465 | 130／133 | 29 |
| no-local-panel `e855a1e8a8e6f181` | 584 | `086d2504f1287e226fd55641a3e68c52f632dd91e87044b849a7a29af38ba02e` | 99／10465 | 130／133 | 29 |

最终源级审计身份依次为 `runtime-pcm-context-source-v2-0c0c88e45cfbb12d`、`…-d0037aa8f46a10d3`、`…-6af6e2096cf7085a`、`…-6c03dc52f91285ef`。每份核对原 profile／process／全部 staged 输入／VG 前后封存一致，并绑定当前三个审计文件的哈希。旧 f1be `8fc53d09…` 在修改前 f6bf5ec 检查器与 v2 中均以同一原因拒绝未注册的 quiesce 发布源，未将该历史来源改为接受。

原 94 个负控全部保留；新增 15 个覆盖回复新增 FF／未知 MEM、第三 pin／双 D-CE、保留闭包的四组 D／CE 反相、递增传播、饱和高位及 header cut 操作数。旧 seal 篡改、reset、时钟、ACK／credit、比较器及 SDC 负控继续拒绝。BDD 自检遍历全部 256 个三输入 LUT 的 2,048 次直接真值求值，检查补函数、规约及分配律。

首轮新增 MEM 负控误用了不存在的综合网名，四份各只有该夹具失败，其余 17 项通过。已改为 actual raw Q，并给跨 scope 的第三／双 pin 负控使用已验证本地 alias、断言具体拒绝原因；四份先定向通过，再完整重跑 18 项全部通过。原失败日志保留，没有改网表或降低门禁以通过。

机器证据：[runtime_pcm_reply_next_q_v2.json](workstation_task_20261030/runtime_pcm_reply_next_q_v2.json)。完整 source audit、各候选 109 个负控、日志、配对 SDC、原夹具失败与独立 eligibility 负控位于其列明的 cache 路径，均附 SHA256。

## 安装及退出边界

四份实际 stage 都封存原 `legacy-v1` 约束。审计必须显式使用 `--installed --constraint-revision legacy-v1`，仅报告 `legacy_constraints_installed=true`；**全部 `candidate_constraints_installed=false`**。R00／e855 各 29 个实际遗漏 pin 完整列在 `uncovered_payload_pins.reply`，`selected_constraint_capture_coverage_verified=false`；registered／no-CNN 的 legacy coverage 为 true，但也不是 paired 安装。

新 paired 文本的静态覆盖检查通过，不能把临时文本当新封存产品。v2 helper 默认生成新约束及新 POLICY，生产 profile／artifact metadata 必须显式更新、刷新锁并重新 prepare／综合，不能继承旧 e855、R00 或 FE P&R 身份。回退方式是恢复旧工具／锁及各自原候选；不追改旧 stage。

Gowin 查询解析、required／propagation、双模式 routed setup／hold、完整 reset recovery／removal／pulse、观察 RAM 数据弧、全量 CDC／PLL、整机功能及板测仍未接受。所有 physical、release、deployment 标志为 false；本阶段没有 SRAM／Flash 操作。
