# 注册控制／no-CNN：PCM源检查器精确适配（2026-10-30）

维护检查器现已支持两份实际注册控制网表的已审查拓扑。父级分别完成完整15项回归，各94个负控全部拒绝，无跳过；实际installed审计得到以下独立身份。原检查器对变化的context闭包和比较器先拒绝，未通过删除失败项、隐藏消费者或放宽SDC使其接受。

| 实际综合候选 | VG后缀 | 父级PCM审计身份 |
|---|---|---|
| `custom138k-workstation-v1-1aea3c01fa6c1b14` | `b8bd2a02…` | `runtime-pcm-context-source-v1-ab01a46b5f0b0d29` |
| `custom138k-workstation-no-cnn-v1-525ffff10d622031` | `37c811ff…` | `runtime-pcm-context-source-v1-bdeae24ef9dcca9a` |

两份审计各核对229个发布位、864个精确pin selector、16组同步和五组global release、19项布尔契约。四组完整首级消费者闭包为65／263／141／207；后两组相对旧139／205各新增实际注册的quiesce／mute D反馈端点，没有忽略新增消费者。所有约束仍是原50行，字节不变；异步reset assertion、recovery／removal没有新增cut。

quiesce从已知control域DFFPE Q发布，resume从已知mute DFFPE Q向前找到唯一runtime-local INV并证明反相。两发布者要求实际clock、preset和无条件CE；不再依赖数值网名，也不从目标首D反推“可能源”。stream_flush在选中完整顶层没有消费者，实际综合网表已删除它，因此没有伪造第三个保留FF或硬件接受。

比较器优化只接受两种精确的完整操作数集合，每种都单独证明最终门控：enabled网表的ready carry含32个epoch位，rate在scalar gate；no-CNN的carry含全部33个epoch／rate位。enabled reply的carry含全部64个sequence／epoch位；no-CNN carry为63位，只有epoch31留在scalar gate。reply rate总是另行核对。缺位、错位、重复、绕过scalar比较和未审查拓扑均失败；不以数字alias选择分支。生产测试显式选择installed模式，proposal模式仍拒绝已安装SDC，不能临时追加约束冒充封存输入。

父级另在独立副本复验两份实际注册输出D锥证明，生成的inventory均与各自独立seal逐字一致。实际LUT／INV的ROBDD检查十种有效current state及对应next-state／输出同沿关系；registered网表量化185个自由boundary位，no-CNN量化174位，分别拒绝十个clock／CE／preset／Dgate／滞后一拍负控。每份BDD实现另经4,096个LUT直接真值对照。此证明以reset建立的输出／状态不变量为前提，不声称重证全部业务条件、器件PVT、DAC模拟行为或复位物理时序。完整首级FF闭包同时保留mute到DAC SMUTE输出的组合分支。

两份新prepare来自主工作区的新双profile锁，结果如下；与前一份主线prepare逐项比较，全部staged字节保持相同。

| 新来源候选 | config SHA256 | staged／enabled |
|---|---|---:|
| `custom138k-workstation-v1-63028f9b77637e25` | `3cb7e0d8368f8b9e362111189c96fb7bd6fdf514c5b5c1a0fb76a1faca603d86` | 570／259 |
| `custom138k-workstation-no-cnn-v1-60cae14e43255a2b` | `7bee58e7b6d3090909f4003f984450c3840a62807d8d2c033772e3973e0b515e` | 571／259 |

父级prepare回归：enabled profile20、识别policy7、两配置来源各12、accepted来源10，全部通过且无跳过。新prepare尚未综合；上述actual审计明确绑定表前的原综合候选。不能把新source-only身份冒充已综合，也不能把正在运行的FA物理结果改名给新prepare。FA继续使用它原先的锁定输入，未被本阶段修改。

原始三文件提案及23个交付文件均重新hash；cache试验policy的结果另用cache身份封存，未将“加载cache代码却hash旧root依赖”的中间product前缀冒充正式接受。本阶段正式audit从集成后的主工作区工具重新运行，完整工具／source／test／profile／process／VG身份见[机器证据](workstation_task_20261030/runtime_pcm_registered_and_no_cnn_main.json)。稳定维护说明在 [WORKSTATION_RUNTIME_PCM_CDC.md](../tools/WORKSTATION_RUNTIME_PCM_CDC.md)。

检查器仍只覆盖指定PCM/context及控制边界。组合prefill／context-ready稳定性、观察RAM数据弧、其余shared CDC、全量reset／PLL、Gowin对象解析、两模式routed setup／hold与实板仍须分别完成；完整CDC与部署标志为false。本阶段无EDA或板卡操作，没有位流、SRAM或Flash交付。
