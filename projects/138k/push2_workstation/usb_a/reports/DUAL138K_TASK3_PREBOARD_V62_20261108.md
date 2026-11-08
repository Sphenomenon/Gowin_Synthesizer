# 双 138K v62：W 故障反馈与录音比较修复

本阶段仍止于上板前。M 保留普通 32／矢量 8 声部、唯一参数应用点、基础音频、最终输出和本地混响；W 保留实际 CNN、手机接收解码及唯一录音对象。task2、单板回退、冻结基线和历史失败证据均保留。没有连接、识别、加载或操作板卡，没有写入 SRAM／Flash。

## 已封存来源与综合

| 项目 | M | W |
| --- | --- | --- |
| 配置 | `custom138k-workstation-task3-m-preboard-v1` | `custom138k-workstation-task3-w-preboard-v1` |
| v62 候选后缀 | `1823489029b73b89` | `0f13850db3f5c180` |
| 配置 SHA-256 | `f1ee82ae6b0df15f8ccee3c2d61df1e541320509aecd50cc3ea207cbc4808b17` | `9184b1d1e6c3325005a2cb682bbed215a14bbf97efa198dd52b809c011b04bb5` |
| 来源锁／实际暂存文件 | 1088／736 | 1142／724 |
| 独立 prepare | 全部实际文件及候选身份一致 | 全部实际文件及候选身份一致 |
| v62 完整综合审计 | **29/29** | **27/27** |

两板使用 xPack RISC-V GCC 15.2.0-1。v59 已分别完成完整综合（229.38／183.31 秒）；v62 与该综合的完整编译输入、顺序、工程及选项相同，仅审计／物理准备工具有明确列出的变化。`tools/workstation_synthesis_reuse.py --audit-tool-only` 逐字节检查后复用原产物，并绑定新旧身份及所有产物哈希；没有重新综合或编辑 VG。两个独立 prepare 的每一个实际暂存文件均重新计算哈希。

## 本轮生产修改与证明范围

1. **原始 DDR 故障诊断 cofactor**：在真实 arbiter／queues／media／raw-store 边界传递诊断探针。transport=0 时探针与实际观察相等，transport=1 时同拍故障优先，X/Z 走原表达式。实际接受、派发、返回、协议粘滞状态及退休方程不改；不增加状态或接受权威。由 W 显式策略选择，默认配置关闭。五份生产源码受独立 adaptation 清单及严格逆向哈希约束，清单 SHA-256 为 `6364b49195640070e6fd732c2a522307f88cdb21287fb6acb21ab81bf102d053`。
2. **录音 peer/session 比较**：保持全部 64 位及同拍 CANCEL，将实际 v17 的 64 位串行 carry 比较拆成八组保留的 8 位比较。不增加寄存器或周期。生产源码有完整四态比较回归；最新完整 W 网表逐字节证明全部 64 个输入，逐字节破坏操作数均被拒绝。该网表门仅证明八个字节方程，不声称证明整个 ingress 状态机。
3. **精确 W 布局**：保留 128 个 tag FF、257 个返回 FF、完整 75 门因果库存及 280 个 held 覆盖；仅解除共享 watchdog 门 `delay_dma/n420_s2` 的位置限制，另将真实 status[4]／fetch-fault FF 分开。共 741 个精确对象、5 组；9347 个相关 primitive 经库存核查。v17 的该共享门造成 6.318 ns 跨区往返线延迟。没有放宽时钟、false path、min/max 或 hold 检查。
4. **审计适配修复**：CNN ready 从真实唯一驱动查找，仍校验 LUT、四个真实输入、完整 truth table、native release 和两级消费者闭包。新增录音比较位于 phone ACK 适配外层，审计先严格逆向该层，再识别原 ACK 身份；历史哈希和原断言保留。v61 的四项失败因误选旧分支而查询不存在的 `n12046_12`；失败原件保留，v62 完整审计已通过。

真实完整 W 综合网表的只读拓扑对比：read-pointer→completion_generation 从 15 层降为 8 层，最差 raw endpoint 从 17 降为 13 层；RX payload135→record result 从 72 层降为 17 层。raw-store 2175 个 FF、录音引擎 974 个 FF 保持不变。这些是结构诊断，不能代替 sensitization、实际线延迟或 STA。

## 验证与证据复用

- native fault 四态组合证明通过 3 个等价命题，5 个破坏版本被拒绝；完整 raw-store 双时钟 twins 的 6 组顺序场景及 8192 组任意 binary/X/Z next-edge 检查通过。它不是整机归纳证明。
- record peer 四态 16673 次比较及 3 个破坏版本通过；实际网表 8 个完整字节证明及 8 个操作数破坏版本通过。
- W 当前批处理映射 238 位请求、256 位回复、完整身份和真实发送状态依赖通过；57 个破坏性检查被拒绝。
- CNN ready／退休门独立证明及 7 个破坏版本通过；741 对象实际布局／接收边界检查通过。
- 实际 M/W paired-bus 与 PCM block／混版本回归通过。其 22／14 个记录输入、native 组合证明的 3 个输入重新逐一验 hash，全部未变，复用原有效证据。
- `sim/test_current_workstation_sources.py` 17/17 通过；原有 CANCEL、ACK、pack／tuple／terminal 及 native 选择／历史逆向验证沿用输入未变的本轮证据。
- 历史 `test_workstation_task3_w_paired_cdc` 类初始化仍不适配当前完整 SDC 后缀；原失败日志保留。本轮单独执行该类中当前退休／ready 破坏检查，并以完整 v62 审计为整机证明入口，不把初始化失败说成整套测试通过。

## 物理阶段与未放行事项

W v18（`D21108D2`）绑定上述精确 v62 来源，使用既定 place2／route0，正在进行一次完整 P&R；结果尚未用于放行。上一份 W v17（`D21108D1`）仍保留为失败证据：BSRAM 287/340，setup／hold／recovery／removal = −3.461／−1.991／+2.216／+0.337 ns，位流 SHA-256 `45c92ccea99207291aab70b5420b56ce12eab0212d92af621bf7f737df83f522`，不能加载。

M v17 仍有 2416 条未布通网络，没有有效位流或最终 STA；v18 增量实验保持退役。本轮只在独立副本启用工具后端 `-dpr` 诊断输出，重放精确 v17 输入，目标是取得具名未布通网络。该诊断不生成位流，原 place2／route0 和全部约束不变，不算新 M 候选。首次启动因独立目录缺工具的相对 device 资源而在 P&R 前失败；修正只读资源路径后正在运行，不能据此推断拥塞原因。

两板均未放行 SRAM。W 新物理时序、完整 routed CDC、M 路由阻塞、两板最终资源／STA／PLL仍需通过。真实 LCD 吞吐、DAC 延迟、独立演奏及 TF→CNN→Push／手机 D／录音下载整机演示留给正确目标板的下一阶段。执行步骤见 [SRAM 清单](DUAL138K_TASK3_SRAM_CHECKLIST_20261108.md)。

## 复现入口

缓存根：`/Users/sphenicidition/.cache/gw138k-task3-20261108`。源码准备使用现有 `build.py --prepare-custom-board`、上述显式 profile、锁定网表目录 `gw138k-task3-20261103/locked-netlists` 和 `/Users/sphenicidition/.local/opt/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf`，输出到全新目录；不得覆盖冻结 prepare。

v62 主／独立 prepare 为 `{m,w}-preboard-prepare-v62{,-repro}`；完整审计位于 `diagnosis/{m,w}-audit-v62.json`，输入复现凭据为 `diagnosis/reproduction-v62.json`。完整来源、审计、验证及运行凭据的摘要见同名 [JSON](DUAL138K_TASK3_PREBOARD_V62_20261108.json)。物理输出、原始失败及诊断均保留在缓存，不纳入源码。
