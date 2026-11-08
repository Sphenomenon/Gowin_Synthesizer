# v58：W pack/fetch 修复及完整消费者证明

M **29/29**、W **26/26** 完整综合审计通过。两板候选完成独立准备复现，但物理门禁尚未全部通过，**不得加载 SRAM**。未访问板卡或写 Flash。M 继续负责交互、唯一参数、普通32／矢量8声部、本地混响和最终输出；W 实际承担 CNN、手机接收解码及唯一录音对象。

| 板 | 完整候选身份尾号 | 配置 SHA-256 | 综合 FF / LUT / ALU | 综合 BSRAM 等效 |
|---|---|---|---|---|
| M | `ed44feb1b5bf99a9` | `0f13556bcc5359657ba6175b4ae176f01d17af100018dc56b17cd6c6d8e67264` | 58695 / 70171 / 18337 | 212 |
| W | `e95d8efef5b77277` | `abcc032fdde805afb994f93532d2028f6ec1a6445e89c94a0092729786eb8334` | 46764 / 59938 / 15919 | 253 |

身份前缀分别为 `custom138k-workstation-task3-{m,w}-preboard-v1-`。缓存为 `/Users/sphenicidition/.cache/gw138k-task3-20261108/` 下的 `{m,w}-preboard-prepare-v58`；独立复现目录带 `-repro`。M 732、W 720 个全部暂存输入逐字相同；源码、USB 固件及 AE350 ROM／bin／ELF／object 的实际哈希也一致。路径相关的 stack、callgraph、map 和诊断字节单独保留，不宣称这些文件或第二份位流逐字复现。

W pack/fetch 将已知同拍 native fault 的隔离放在最终输入，不增加状态或等待拍；X/Z 保留原过程式写入，复位不受选择条件影响。默认参数保持关闭，只在显式 W preboard 配置选入。独立 adaptation 及严格逆变换保留历史源身份；六组双时钟对照和8192个任意二态／四态边沿通过。17项 accepted-source 检查通过。实际完整 W 网表的 read-pointer→pack CE 组合深度从16降至13；这是拓扑证据，物理收益须由新 STA 判断。

新映射的 endpoint live 为 `LUT4 16'h4000`，I0 对应负极性 `live_4`；审计仅为该精确形式展开两层真实 LUT，在 BDD 中核对实际 live、完整资格方程和精确支持集，保留 command-release veto。reply 使用实际共享 read 控制，256个完整数据 next-Q 方程全部通过。六项定向测试及78个破坏负控制通过，旧 v55 正映射亦保留通过。没有用任意控制切点绕过消费者证明。

W 物理选择核对9331个 broad 原语、128个权威 tag Q及257个返回捕获 FF；实际 tag-return 锥为75个原语，仅新增 `delay_dma/read_outstanding_s4`，总选择740个。四项布局定向测试通过；时钟、重复位置、缺失清单和 FIFO／header／Gray／release 破坏均被拒绝。另针对 v16 的 `status_payload_4_s0/Q → fetch_fault_o_s0/D` −0.040 ns hold，仅添加精确1.8 ns最小数据延迟，检查真实时钟和完整源闭包，保留 setup／hold；无 false path 或总线级例外。相关正／负控制通过。

v57→v58 两板所有实际暂存字节均相同，严格复用有效综合，无审查输入差异。W v57 已执行新完整综合；M 编译字节沿用已有效综合。两板对 v58 身份重新运行完整审计和当前来源检查，不重复运行输入未变的综合。

## 实际物理状态

W v17（`D21108D1`）绑定精确 W v58 输入，保留 DDR 功能复位和 min0.8 ns 策略，采用既定 place2／route0。完整 P&R exit0，1166.80秒，运行前后输入哈希一致；物理 BSRAM **287/340**、CLS **56943/69120**、Logic **81002**、FF **46764**。位流 SHA-256 为 `45c92ccea99207291aab70b5420b56ce12eab0212d92af621bf7f737df83f522`，仅作失败证据保留，不能加载。

| setup | hold | recovery | removal |
|---|---|---|---|
| −3.461 ns | −1.991 ns | +2.216 ns | +0.337 ns |

PLL／启动检查通过；真实 routed receiving-synchronizer、paired-held、raw-command 和 raw-completion 四项选定边界检查通过，仍不是完整物理 CDC 验收。pack 路径从 v16 的−3.029 ns改善到−2.050 ns，但最差setup已落到 read-pointer→completion-generation；delay FIFO→watchdog为−3.163 ns，config→recording result为−3.361 ns。保留全部真实失败，不用局部改善代替整板时序。

status→fetch_fault 的1.8 ns最小延迟要求没有获得所需物理修复：实际数据仅1.212 ns，时钟偏斜−1.343 ns，hold仍失败。该约束改变了检查要求，不能当作插入布线延迟；下一步必须针对实际布局或数据结构修复。delay watchdog 的实际路径在C159→C55→C143之间往返，其中两段线延迟2.971／3.347 ns；需先检查其与tag-return局部约束的共享逻辑，再决定调整。

W v16（`D21108C3`）作为失败历史保留：物理 BSRAM287/340、CLS56980/69120；setup／hold／recovery／removal 为 **−3.029／−0.040／+2.573／+0.284 ns**，PLL通过。DDR recovery已由旧版−0.527 ns转正，但该位流仍不可加载。

M v17（`D21108C2`）仍有2416条未布通网络，物理 BSRAM253/340、CLS60473/69120，无有效位流或最终STA；v18增量放置失败实验退役。实际v14/v17直接扇出比较已保存，但未获得具名未布通网络或物理拥塞定位，不以此启动无诊断的路由参数试跑。既有滑音／效果及队列修复保持；需要解决当前完整布线后重新检查全部STA。

录音 result-payload 的缓存内最终故障选择实验未选入：2048个任意完整顶层寄存器 next-edge 二态／X/Z比较通过，隔离综合 PCM-valid→result D/CE 深度10→8；不等于完整归纳、存储器状态证明或物理改善，也不复制命令验证逻辑进入生产。

[结构化清单](DUAL138K_TASK3_PREBOARD_V58_20261108.json)绑定新候选、完整审计、输入复现、物理运行及日志哈希。334项历史配置／基线再次核对不变，task2额外清单仍绑定v54证据；task2、单板和全部历史失败／回退保留。[SRAM清单](DUAL138K_TASK3_SRAM_CHECKLIST_20261108.md)尚未放行。剩余工作是两板完整路由、全部STA、PLL／复位与完整物理CDC通过；真实LCD吞吐、DAC延迟及整机演示留到上板阶段。
