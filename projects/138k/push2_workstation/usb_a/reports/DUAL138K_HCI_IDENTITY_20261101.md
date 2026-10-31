# W-DEMO HCI 身份比较的组合路径修正

2026-11-01。W10 `D2103116` 默认布局的实际物理 BSRAM 为293；`clk_50m→clk_50m` 报出的前100条路径均为负裕量，最差 −3.205 ns。原 TR Path1394 从 decoder `handle_o[8]` 到 host RX lease RAM 的 WRE，数据延迟23.098 ns，包含7.437 ns cell、15.355 ns route、0.306 ns C2Q。实际 VO 显示12位 handle 比较的末段 ALU carry 经优先选择 `close_generation[3]`，继续穿过32位 generation identity carry，再进入 owner/fault/readiness 和 RAM 写许可。综合后的 `handles_ER_*` 是合并读网名，本报告不将其误认成某个唯一源码数组。

两处维护源码只把 handle/generation/token 的等于与不等于改为显式 XOR 归约；没有新增周期、寄存器或状态，没有改槽位循环的最后匹配优先级、信用计算和唯一 flow owner。`flow_owner`、event decoder 与 W10 消费字节一致。冻结 W10 工程和物理产物未修改；下一候选须由原 prepare 路径复制这两份维护源，重新测量综合和 P&R。

W10 实际消费副本来自外部 `w-demo-d-v10/workstation/Prj1/rtl/bluetooth/hci_owner/`，在版本化测试 fixture 中保留原字节。host RX 原 SHA256 为 `82ff377a3516d3be912cb98eedf5ef904d3720a69aedf673644bc63ede6a9105`，修改后为 `a4b556159a286ddeb6368d7fe749011664950ad8d78269885194afe69f63384d`；native transport 原值为 `a151aa426f4880dbcbf85239688ec910e8f43a2c2fb240e52161e166f029a10a`，修改后为 `0015cc57c12186a2b06945356adb5ff8ba30968c7403c143b8d7141a3aa5a93c`。

整模块对照严格检查两个源码除列明表达式与注释外的全部字节。host RX 对照17674周期、33输出、39内部状态；native 对照6545周期、33输出、2716内部及 host RX 子状态，包含三组真实包 RAM 的2608个元素。逐周期使用四态 `!==`，native 参考模块也实例化原 host RX。12／16／32位二态操作数的完整等于／不等于关系经 Z3 证明为 UNSAT；三个漏比较位的关系负控均得到反例，两种整模块 token／generation 身份破坏也均被拒绝。整模块对照覆盖既有业务序列，不将其表述为全部状态可达性证明。

既有 host RX 回归通过160228 checks、13个业务破坏负控、8个非法参数与严格 lint；native 回归通过268 checks、11个业务负控及真实 UART8E1／H5 仿真，完成253字节 patch、4个 bootstrap、10次 host return、3次 notification 和1次 reconnect。这里只是实际 UART 帧仿真，没有实板验证。原回归只更新两处变异锚点，保留全部负控。

[机器证据](dual138k_hci_identity_20261101.json) SHA256 `b59144aed76043e4035a5aac63138d42aa38eceabee5970ac2fe21c4058fb882` 固定原物理 TR／VO、全部源码和验证结果身份。最终整模块证据在外部 `hci-identity-whole-compare-v3/verification.json`，SHA256 `4e74845ef73ee1aeab2ddb4dc6177f2ed8f977b34fe8435e58ff6d3225bb3d7f`；早先 v1 测试副本编译失败、v2 尚未补全包 RAM 的结果均保留。物理时序及资源收益仍未测量，未综合本次源、未运行本次源 P&R、未下载 SRAM、未写 Flash。回退可恢复匹配 fixture 的两份原维护源码，并以新候选身份重建。
