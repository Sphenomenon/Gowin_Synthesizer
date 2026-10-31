# W13 raw START：完整实际映射与有条件下一状态比较

日期：2026-11-01。对应 [机器记录](dual138k_w13_raw_mapping_20261101.json)。本轮只读 W12／W13 的完整真实 VG，未修改生产 RTL、VG、冻结审计器或原物理结果。

W13 的显式 START case 确实使主要 `write_address` CE 不再直接包含 64 个 command／read timeout FF 叶；其余宽状态的 CE 仍包含这些叶。全部 122 个目标 FF 的有效下一状态比较通过，但有明确的状态与黑盒输入配对条件，不能称为整机等价或时序通过。W13 默认完整物理结果仍为 setup −5.765 ns、6,829 端点，hold −3.537 ns、3 端点。

## 1. 输入身份与审计边界

| 对象 | SHA-256 |
|---|---|
| W12 实际 VG | `e2bc658c7bb33953d2982e863f59d6500cc00f4fd478b60a4ecb6fb7f2977894` |
| W13 实际 VG | `3c7866321188f7b36dc601c36f6b572b04ee5c5f7786f434a10a1b0d2bb4a787` |
| W13 prepared manifest | `78c2602862e32ecc193c475f156d0ba58b164220f7ebeb84777fa26b997468cd` |
| W13 实际 raw-store 源码 | `21471d722da294e841829f6ff1ec396fab016358bf6a796f93d17ec0f95c978d` |
| W12 完整锥清单 | `440cbf3bd3d4228229fc3fc37ebad877c7b805e5756a7822b293879f505629cb` |
| W13 完整锥清单 | `3ecd7e9a5182430e1d0929d4209d6393a642cf93305575c299df3e8faeaef229` |
| 最终 122FF 函数证书 v6 | `80fada31ec26b4a7c42a2d8cf129623fbb4824bc80029bcf0c36c8a4828a6c66` |

缓存根为 `/Users/sphenicidition/.cache/gw138k-dual-20261031/`。两个完整清单位于 `w13-raw-mapping-review-v2/`，最终函数证书位于 `w13-raw-mapping-review-v6/actual-functional-certificate-v6.json`；外部工具副本及总封口位于 `w13-raw-mapping-final-v1/`。机器记录保留每份证据的绝对路径与哈希。

输入使用 W13 的 1,365 文件冻结快照 `w13-audits-v1/source-tools`，不使用当前活动 RTL 代替候选。最终独立 wrapper 在执行前后逐项复验 W13 manifest、645 个 staged 文件和全部 1,365 个冻结文件。两个 VG 在全部破坏负控前后哈希相同。

## 2. 完整寄存器、D／CE 与结构支持

两份实际 VG 均恰有 122 个目标 FF：`memory_generation`、`memory_next_index`、`memory_committed` 各 32 个，`write_address` 26 个；后者最低三位为常量。全部寄存器的 primitive kind、参数及引脚都有清单，全部 127 个不同 D／CE 净均展开，未按时钟、前缀或合法状态删减叶。

| CE 净／寄存器族 | W12：FF 数／组合 cell／最大层数／边界叶 | W13：FF 数／组合 cell／最大层数／边界叶 | command_wait／read_wait 叶 |
|---|---:|---:|---:|
| `memory_generation` | 32／155／15／257 | 32／163／15／257 | 两份均 32＋32 |
| `memory_committed` | 32／175／16／284 | 32／181／15／284 | 两份均 32＋32 |
| `memory_next_index` 的门控 CE | 9／260／36／383 | 31／266／36／383 | 两份均 32＋32 |
| `write_address` 的门控 CE | 26／155／16／257 | 25／130／15／193 | W12 32＋32；W13 0＋0 |
| 常高 CE | 23／0／0／0 | 2／0／0／0 | 0 |

常高 CE 与门控 CE 的分配改变，故不能只按某一 CE 名字比较所有位。有效下一状态比较覆盖所有 122 位，也覆盖把原保持路径吸收入 D 的实际映射。以上层数是到显式边界叶的组合图最大深度，包含正常 FIFO 校验等分支，并非 routed timing 数字。

两份完整结构支持均为 445 个不重复边界叶：368 个 FF、66 个 `SDPX9B` 输出、8 个 `RAM16SDP4` 输出、3 个 DDR IP 输出。随后实际展开两个 tag RAM 的 `RAD[3:0]`，补入 4 个真实读指针 FF，总共核对 449 个配对身份。不能据最初 RAM 输出截断后的图宣称读指针不再影响 CE。

## 3. 实际函数比较与破坏负控

每个 FF 计算实际 `CE ? D : Q`，常高／无门控情况按实际引脚处理；LUT 使用 VG 的实际 INIT，ALU 使用官方 GW5A 0—8 模式的 SUM／COUT 函数。两个实际 `RAM16SDP4` tag RAM 用任意 16×4 存储数组及其真实 RAD 表达式求值。122 组 W12／W13 有效下一状态不等式全部 UNSAT，未约束“正常可达业务状态”来排除非法组合。

完整配对表逐项检查 FF primitive、INIT 与 clock，以及 RAM primitive 与参数。三个剩余输入只允许来自实际 `u_memory/u_ddr3/gw3_top` 实例、公开 `DDR3_Memory_Interface_Top` 的 scalar output 声明及对应端口连接：`controller_rvalid`、`controller_wrdy`、`full`。没有把任意未识别净按名字配对。两个公开 wrapper 的合成临时 clock 名不同，原始 wrapper 哈希分别记录，未以文本相同冒充 IP 功能证明。

| 仅施加在内存中实际 cell 的破坏 | 结果 | 见证下受影响目标 FF 数 |
|---|---|---:|
| `write_address_28_s4` CE LUT INIT 反相，并强制 `published_valid=0` | SAT，检出 | 1 |
| 删除实际 generation bit31 比较操作数 | SAT，检出 | 94 |
| 实际 request-sync 输入改接 command ACK | SAT，检出 | 112 |
| 删除实际 command-timeout bit14 输入 | SAT，检出 | 26 |

所有破坏均恢复，未写回 VG。证书保留每个实际 cell、原值、新值、SAT 见证及受影响寄存器。

证明范围明确限定为：普通 FF D／CE 操作；配对 FF Q、`SDPX9B` 已寄存输出状态及任意 tag RAM 内容相等，三个实际 DDR IP 输出为任意且配对相等的独立输入。未证明异步复位动作、上游序列历史、BSRAM 写读历史、加密 DDR 内部函数或完整工作站四态等价。先前维护源的完整四态／整模块回归是另份证据，不能与本次二态网表比较混称。

独立交叉检查直接使用本机官方 GW5A `prim_sim.v`（SHA `2ec53fec48601d2d491299bc3a28b4b199d3a79708f1dd38f72555a5c688ebd5`）：75 个实际不同 LUT INIT 配置共 4,800 向量、ALU 全部模式共 1,152 输出向量，以及 RAM 的 16 个实际地址与 64 个模型输出检查均通过。未改厂商库。

## 4. 解析适配与保留失败

冻结 `PcmNetlist` 对 escaped scalar 有专用解析，但缺少 escaped vector bit 的跨层映射。外部独立 accessor 只接受已声明范围与精确宽度的 formal bit，按声明方向解析到实际 binding；原 parser、VG 和生产 oracle 未改。3 个正例覆盖非零上下界、升／降序和显式拼接，3 个反例拒绝越界、宽度不符和缺少范围。

v1 因 escaped vector alias 未识别而拒绝；v2 因 DDR 输出未识别而拒绝；v3 因要求整个 wrapper 文本逐字相同而拒绝；v4 在 64 个 FF 已证明后因 `SDPX9B` 注册输出未建模而拒绝。全部原证书和日志保留。v5 首次完成 122FF 正例，v6 加入四个真实破坏负控及 VG 前后稳定性。原语交叉检查 v1 在已比较向量后拒绝 Icarus 的 `$finish` 提示行，最终 v3 只接受该工具的精确结束行并保留全部严格数据检查；中间脚本语法错误没有产生通过证书。

## 5. 对真实物理瓶颈的含义

W13 默认物理 `D211010A` 的最差 setup 为真实 `read_pointer_0/Q → memory_next_index_29/CE`（同到 bit30）：10.000 ns 关系、15.504 ns 数据延迟、−5.765 ns 余量。原报告的实际节点链为：tag RAM RAD → DO → tag 检查 → response fault → `recording_owner8/fault_now` → raw native bridge → command/read fault 汇合 → FIFO pop → `memory_next_index` CE。该条 routed 路径 15 逻辑级，cell 4.025 ns、route 11.185 ns、tC2Q 0.294 ns。

因此本次只确认主要 write-address CE 的 timeout 直接依赖退出，以及完整 raw 宽状态有条件下一状态保持。不能宣称全部 START 字段短化，也不能把局部组合 cell 数减少记作全局资源或物理收益。`memory_generation` 还承接 CLEAR 命令准入，`memory_committed`／`memory_next_index` 还承接 CLEAR 完成与正常提交／FIFO 消费；这些实际分支仍依赖完整故障许可。下一步只应从真实路径上提出独立、可证明的缓存实验，保持故障／超时与 CLEAR 的原周期、优先级及状态归属。

本轮没有上板，没有 SRAM／Flash 操作，不转授 CDC、STA、真实蓝牙声画或双板并发验收。
