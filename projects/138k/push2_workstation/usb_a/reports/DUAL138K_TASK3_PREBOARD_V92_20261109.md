# 双138K上板前收尾：v92检查点

2026-11-09。W新增generation比较捕获已通过完整综合、消费者与有限物理约束检查；**两板仍未达到上板前放行条件**。未连接或操作任何板卡，未写SRAM／Flash。[JSON记录](DUAL138K_TASK3_PREBOARD_V92_20261109.json)绑定配置、全部暂存输入、综合、物理结果和复现证据。

| 项目 | M | W |
| --- | --- | --- |
| 完整候选 | `custom138k-workstation-task3-m-preboard-v1-5087dc38dd26f6c0` | `custom138k-workstation-task3-w-preboard-v1-0ccd286783f82308` |
| 来源锁／暂存文件／编译输入 | 1135／748／289 | 1189／735／202 |
| 完整综合审计 | 31/31通过 | 29/29通过 |
| 综合 Register／LUT／ALU／BSRAM等效 | 57999／70761／17817／212 | 46822／59866／15926／253 |
| 物理实现 | 复用v29，`D21109CF` | 首次v30b，`D21109DE` |
| 物理 Logic／Register／CLS | 90740／57999／60539 | 81045／46822／56717 |
| 物理 BSRAM／DSP | 253/340／120.5/298 | 287/340／122/298 |
| 结果 | PR0004，1848条未布通；无完整STA或可用位流 | 688.36秒完整布通；PLL／DDR启动及显式有限检查通过，全局setup失败 |

W在原有命令捕获边沿保存两位比较结果，分别供七处后继generation和四处当前generation判断使用。没有新增命令周期，直接命令配置保留原比较。六组实际raw-store公共输出／既有状态／FIFO／cache对照通过，完整映射证明核对全部32位、捕获使能、复位及generation只在business-start写入；条件归纳为UNSAT。七个破坏性映射反例被拒绝。新捕获位纳入原10ns max／1.8ns min保持数据检查，没有关闭hold或放宽时钟。

物理准备按实际映射重建787个tag／保持数据单元及2211个delay单元；旧选择、重复约束和错误watchdog被拒绝。四项完整映射回归通过，含M的108个TF payload CE及W的batch/window、successor和布局重建。来源检查17项通过。首次准备使用的Python缺少z3，在准备阶段停止；改用已安装z3的`/opt/homebrew/bin/python3`、新输出目录v30b后完成，只有一次P&R调用。

W全局setup／hold／recovery／removal为 **−3.082／+0.135／+2.432／+0.287 ns**。显式max／min等有限检查全部非负，最小setup／hold为 **+0.181／+0.233 ns**。这与全局时序分别记录；clk50、audio76m8、DDR UI100仍有setup负路径。最差为接收payload→录音channel fault；效果fault→deferred为−2.908ns，fetch-end→completion为−1.898ns。`.fs` SHA-256为`75dbccb3e12591c15e7b7beb2ffef5d522b8dfe47ebab26c561c94868af70c3d`，**禁止加载**；该身份没有继承历史候选的板测。

两次独立prepare的M 748／W 735个暂存文件、编译顺序及候选身份一致；M元数据逐字一致，W元数据仍有目录相关差异，不声称全量元数据一致。相对v90，M编译字节和配置全同，复用原综合及失败物理结果；W唯一改变的编译文件是raw-store，受检逆变换逐字还原v90，其余固件、CNN、HCI／SBC、滑音、效果、TF及顺序均相同。相关有效功能证据继续按这项范围复用。

M的v29诊断重新捕获到精确1848条失败网络，匹配1703条标量驱动，其余145条为顶层或硬核等未匹配驱动。主要驱动来自显示生产器497条、读取器441条、DDR控制／PHY 198条；不是新的放行实现。针对读取器的未选入方案把元数据校验移到既有捕获边沿，只保存发布仍需要的值，保留坏数据、重试及上次有效图行为。legacy／minor1实际双实现中全部23个公共输出分别在11242／4411295个边沿相同，两个绕过校验反例被拒绝。读取器独立综合Register 1595→1245、ALU 548→516、LUT 890→859、BSRAM等效11不变；**尚未选入配置、没有完整M综合或P&R收益**。下一步须版本化接入、核对实际消费者／映射并完整重建。

W录音连续性诊断的初次组合复位蕴含失败记录保留。进一步追踪实际网表，发现蓝牙observer复位由与入口counter共享异步CLEAR的两级INIT0寄存器释放；两级被综合共享到USB PLL init命名下。32位入口递增、32位previous捕获和sample-seen的实际next-Q均已核对，初始化、时钟边沿、父复位异步断言／释放以及source sequence fault不可达的规范化事件归纳为UNSAT。结论仅限这组真实同域counter／observer／reset-release子系统；生产连续性保护仍在，不能替代全设计等价或CDC检查。

保持M交互、唯一参数、普通32／矢量8、本地混响和最终输出；W实际CNN、手机接收解码及唯一录音对象。task2、单板、冻结基线与历史回退保留。跨板业务默认关闭；真实LCD吞吐、DAC延迟和整机演示留在上板阶段。[SRAM清单](DUAL138K_TASK3_SRAM_CHECKLIST_20261108.md)仍须等最终候选放行后执行。

在`projects/138k/push2_workstation/usb_a`目录中，来源复核命令为`/opt/homebrew/bin/python3 -B -m tools.workstation_profile verify <候选目录>`，综合审计入口为`tools/workstation_custom_board_audit.py`；v92候选目录位于`/Users/sphenicidition/.cache/gw138k-task3-20261108/{m,w}-preboard-prepare-v92`，另有独立的`-repro`目录。物理父身份、CST／SDC／VG和run.tcl的逐项哈希、原始输出目录、诊断脚本及失败日志哈希均在JSON中。后续改动使用新身份，不刷新本检查点或历史证据。
