# 双 138K v65：完整综合证明通过，物理收尾仍在进行

本阶段止于上板前。M 保留普通 32／矢量 8 声部、唯一参数应用点、基础音频、本地混响和最终输出；W 保留实际 CNN、手机接收解码及唯一录音对象。没有操作板卡、SRAM 或 Flash。task2、单板和历史回退继续保留。

## 已完成的源码与综合检查点

| 项目 | M | W |
| --- | --- | --- |
| 显式配置 | `custom138k-workstation-task3-m-preboard-v1` | `custom138k-workstation-task3-w-preboard-v1` |
| 候选身份后缀 | `c4f7c61927ce185d` | `4c2da1b5c784b2f3` |
| 配置 SHA-256 | `3373c5d9ff2b3260eb0a7d34c24e28dbf582b300f50e86eace318e7c755b9754` | `9102684be49aeeea6e8ca9e709c26c1f6e09a2547a72bbdc2c8b0718053dd5f8` |
| 来源锁／实际暂存文件 | 1093／738 | 1147／726 |
| 完整综合审计 | **29/29** | **27/27** |
| 独立 prepare | 全部实际文件及候选身份一致 | 全部实际文件及候选身份一致 |

v65 对两板重新执行完整综合审计，逐字节核对后复用 v64 的有效综合产物，没有修改 VG 或重跑输入未变的综合。W 的两份 `integration_inputs.json` 含输出目录相关的固件诊断路径及诊断产物哈希，因而元数据字节不同；实际安装的固件、RTL、工程文件和候选身份一致。该差异不参与硬件身份，也没有被当作工程输入逐字节一致。

W 的 CNN frame／seal／cancel 和 recording ingress 四个完整 128 位身份比较现各使用 16 个保留的字节谓词，无新状态或等待周期，同拍取消不变。独立 adaptation 清单及严格逆变换保持旧父源码哈希；默认与历史配置仍使用其原来源。新映射审计逐项证明实际 root、active、reply、flight 和 watermark 方程，保留完整消费者与 next-Q 检查。

验证范围：

- 四个生产身份谓词通过 **16432** 次四态比较；两个遗漏末字节的可编译反例被拒绝。实际完整 W 网表的 **64** 个字节谓词均有局部方程证明。
- 最新实际 W 批处理映射六项测试全通过，**79** 个破坏检查被拒绝，测试前后网表、工程、来源和审计器哈希不变。较早的整套测试曾在选择唯一 active 输入时失败；其原日志保留，修正后的单项通过和本次完整通过分开记录。
- 真实录音 ingress／维护数据引擎及 CNN task-service／broker／staging FIFO 的有效回归，逐一复核全部来源哈希后复用。CNN deferred-seal 用显式确定性 CNN sink，不声称验证模型识别结果。
- `test_current_workstation_sources.py` **17/17** 通过。既有滑音采样边沿、效果事务、TF、PCM block、取消和录音后端证据按其输入身份保留，不以新比较器测试替代整机验证。

## W 已完成的物理结果与真实故障

W v19 `D21108D3` 完成完整 P2R0：BSRAM **287/340**，CLS **56721/69120**，Logic **80139**，Register **46793**。全局表列 setup／hold／recovery／removal 为 **−4.067／+0.146／+1.395／+0.284 ns**；逐条详细报告还存在 +0.260 ns 的 removal 路径，因此保守记录 removal **+0.260 ns**，两种原始报告均保留。位流 SHA-256：

`e0cee0b056755922e7efb6972491ffab8c8d83b97830d6e217d068b89c6d518f`

该位流 **不能加载**。DDR hold 已通过本次完整 STA，但 setup 仍失败。四 PLL 门和 receiving synchronizers、paired held、raw command capture、raw completion publication 四项选定 routed 子门通过；它们不等于完整物理 CDC 放行。

实际最差路径：DMA state→watchdog CE **−4.067 ns**，包含 C61→C111→C150→C134→C55→C137 的跨区往返；observed-context→BLE stop-reason **−3.998 ns**，其中 ingress 有效门到远端 BLE 消费门的一段线为 **7.912 ns**；F808 release→发送 payload 为 **−2.558 ns**。旧 deferred 路径未出现在本次选出的全局前 2000 条 setup 路径中，备用 release 复制探针没有选入生产。

## M 路由诊断与本次物理尝试

原 M v17 的失败集合已精确取得：厂商计数与唯一具名网络均为 **2416**。只读既有 placement DB 得到 **150408** 个单元的位置，原 **351** 条区域约束全部满足。2035 条失败网匹配到实际驱动，381 条未匹配；其中 runtime-display 为 1523 条、reader 为 953 条，集中在底部 R80–110／C40–79，不能再把拥塞归因于未证实的 F808 角落。

M v19 `D21108C5` 在 v65 正常物理准备后，将六份 reader 私有暂存中实际存在的 **1524** 个 FF，按对应 32 位分为八组。全部是同一 memory clock／reset 的实际 DFFCE；没有修改 RTL、SDC、时钟、取消或 hold 界限。它正在进行一次完整 P&R，尚无有效位流或最终 STA。

W v20 `D21108D4` 的完整控制／录音因果布局在约束解析时触发 12 GiB 进程树 footprint 上限；监督器停止，20.57 秒、原输入未变，尚未进入布局，无 STA 或位流。W v21 `D21108D5` 将同一因果范围拆成相邻的小区域，保留平台 reset／BIST 发布位置，新增约束 2210 个实际对象；所有旧约束、VG、SDC 和同拍取消保持。该次运行仍在处理约束，原生调用栈确认热点为 `check_Instance2Constraint`／`eraselgLocVec`，尚不能判断物理收益。两次尝试的输入与失败记录分别保存。

这些缓存布局是有诊断依据的实验输入。只有实际结果有效后才移入维护的物理准备入口；不能将缓存脚本当作最终候选的唯一生产来源。

## 复现与剩余工作

缓存根 `/Users/sphenicidition/.cache/gw138k-task3-20261108`；两板准备目录为 `{m,w}-preboard-prepare-v65{,-repro}`，完整审计为 `diagnosis/{m,w}-audit-v65.json`，逐文件复现为 `diagnosis/reproduction-v65.json`。现有 `build.py --prepare-custom-board`、上述显式 profile、`gw138k-task3-20261103/locked-netlists` 和 xPack RISC-V GCC 15.2.0-1 仍是准备入口；物理构建继续使用正常 reference 模式和原 P2R0。完整身份与证据哈希见同名 [JSON](DUAL138K_TASK3_PREBOARD_V65_20261108.json)。

两板上板前目标尚未完成：M 完整布通及 STA、W setup、最终两板资源／时序／PLL／CDC 与有效布局的正式入口仍须收尾。全部门禁通过前没有可加载的最终配对候选。[SRAM 清单](DUAL138K_TASK3_SRAM_CHECKLIST_20261108.md)仅准备正确目标板、连接、加载、回退和功能验收步骤；真实 LCD 吞吐、DAC 延迟及整机演示留给上板阶段。
