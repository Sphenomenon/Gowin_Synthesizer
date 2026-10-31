# 双 138K：录音 owner 已持有传输的等价因子化

2026-11-01。W10 默认物理候选的最差建立路径为录音 raw store 的 `published_valid_s1/Q` 到 `write_address_9_s1/CE`，相邻 bit10 也在同一组合锥。实际 VO 两端 DFF 的 CLK 均为 `memory_clk`，STA 时钟为 10 ns 的 `ddr_ui100`。该路径有 13 级逻辑，裕量 −5.583 ns，cell 3.531 ns、route 11.404 ns、C2Q 0.306 ns，源 Q 扇出 347。路径经过 owner8 的 IDLE 地址准入／地址故障、共用 native acceptance、native bridge、store fault allowance 和 CMD_START 初始化 CE。它是同域组合路径；本阶段没有增加 CDC 例外或修改 SDC。实际 LUT 的 `protocol_fault_now_s1` 名字不能直接当作源码表达式，review 同时检查了 INIT 和实际端口。

维护源 `rtl/memory/workstation_recording_ddr_owner_mux.sv` 仅替换 `native_accept_o`／`response_o` 的两处输出门控。已持有的 native transfer 不再依赖无关的 IDLE 地址选择；读返回同理。`native_event` 证明 state=NATIVE 且 native acceptance 存在，因此 IDLE 地址项、invalid-native 和 native timeout 不成立；读返回仍保留 RESPONSE 状态下的 invalid-native veto。即时上游 transport fault、write 与 response 同时出现、sticky fault、authority withdrawal 均保留。四态条件运算的 false arm 使用原表达式，保持初始化前 X/Z 传播。没有增加寄存器或延迟，`fault_now`、`transport_fault_o`、`open`、请求 valid／ready、范围检查、超时、owner／fairness、quarantine 和全部时序状态未改。

旧完整源码为 W10 实际消费的 fixture，SHA256 `2af5a52d3bf9c67f93eef803e07bd9b9e636c1f65348676289dc13b487e76bf5`；新维护源 SHA256 `f13e76e3185b0ab96fe3f7a88bd2f46a2ab9d6fcfe060943889fc1993328e5fb`。证明程序逆向撤销且仅撤销本次输出门控块后，完整文件必须逐字节恢复该 fixture。

## 功能与回归证据

- 全部四种 2-bit state 编码、十个独立 Boolean 谓词的 Z3 全域证明为 UNSAT，不加入可达性假设。四态 bench 穷举 state 的 16 种 0/1/X/Z 编码与十个独立四态谓词，共 16,777,216 组合，两个输出准入门控逐项一致。
- 完整 W10 owner 仅改模块名，与新 owner 双实例运行两个真实 native bridge；每个上升／下降沿比较全部 11 个公共输出、state／owner／prefer／active_write／waited，以及 fault_now／open／native_event／read_return。2,547 个边沿全部相等，不屏蔽复位或未知态。原工作负载 1,937 检查、88 写、75 读通过。
- owner 既有回归 3 tests 通过；原 8 个实际源码负控保留，新增 transport、write+response、RESPONSE 期间 invalid-native 的三个即时 veto 负控均被专门断言拒绝，共 11 个负控。
- 实际所选 top、recording runtime／service／CDC／backend、raw store、owner mux 和 boot authority 组合回归通过。并发窗口／下载／迟到返回 110 检查，CPU 写3／BLE写3／CPU读1／BLE读4；pre-ready ledger epoch loss 4 检查；停止 memory clock 时 root release 5 检查。容量、byte/native 单位、末个 BL8、CPU 重叠、越出 recording pool 五个 allocation 负控全部拒绝。这里 global DDR slot／native／response 使用端点模型，其他整机模块由 Icarus `-i` 留空；不代表完整全局 arbiter、BLE 业务协议或物理 CDC 验收。
- raw store 两个既有配置完整回归分别通过 94,766 和 93,238 检查，均覆盖 16,384 帧容量与 8,112-byte 最大 fetch；五个实际源码负控全部拒绝，四条既有 lint 警告清单未变。此项为 raw store 组件回归，本身不实例化 owner mux。
- 实际维护的 DDR client queues／core／native bridge 回归共 44 cases 通过：TAG_BITS=2/3/5、disabled／idle／active、8/9 owners 与既有完整 legacy miter 的 27 组合，6 个 bridge 故障场景，以及 11 个破坏负控。DDR 端点使用模型，不覆盖 PHY 或硬件。
- owner 的 strict Verilator lint 新旧均因同一处既有 `UNSIGNED` 警告退出1：默认 FIRST0=0 时第37行 `address_o>=FIRST0` 恒真。完整警告清单相等；未添加 waiver，也不将其记为 lint clean。

## 保留的失败及验证程序修正

等价程序 v1 已完成四态穷举，随后完整端口清单检查因声明末尾逗号产生空 token 而失败；修正仅过滤空 token，真实清单为 15 inputs＋11 outputs。v2 显式指定 `--reuse-four-state`，只接受与现 bench 字节相同、已完成的 v1 四态执行，并锁定 bench、vvp、compile log 和 PASS log 四份 SHA；不隐式搜索缓存，也未重写原失败证据。

top 组合回归 v1 的前三个正常场景通过，但第一个 allocation 负控逃逸。原因是 Icarus 优先从进程 cwd 解析 include，原 project cwd 中的真实 `rtl/ddr_address_map.vh` 抢先于 `-I` 的 mutant。正式 harness 仅将 compile subprocess 的 cwd 设为该 case stage，未修改 RTL、约束或断言；v2 正常场景和五个负控全部通过。owner lint 首次直接使用 fixture 文件名额外触发 DECLFILENAME；v2 将两份完整字节分别复制为匹配原模块名的文件，再比较严格警告清单。各 v1 目录和日志均保留。

机器证据：[dual138k_recording_owned_transfer_20261101.json](dual138k_recording_owned_transfer_20261101.json)。原路径 review、equivalence v1/v2、top v1/v2、raw store、native DDR 和 lint v1/v2 均位于 `~/.cache/gw138k-dual-20261031/`，完整输入、运行命令和日志身份由机器证据引用。

## 下一候选与回退

本阶段仅完成维护源码和上述离线验证，没有新综合／P&R、资源或时序收益、SRAM／Flash 或实板验收。W10 原输入、网表、物理约束和证据保持冻结。下一 W 候选必须消费上述新维护源身份，重新全量综合、P&R，检查真实建立／保持、DDR、PLL、CDC 和正式声画／录音下载闭环。新发现的 MIDI acknowledge hold 路径由独立来源审查处理，不沿用其他历史端点的例外。若本因子化在物理实现中无收益或引入问题，可只恢复旧 fixture 中的两处原输出赋值并重建新的候选身份；不复用或追改已冻结 W10。
