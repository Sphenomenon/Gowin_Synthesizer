# 双138K v77：捕获结束地址与可复现物理审计

两板来源、独立prepare和完整综合审计通过，**尚未形成可加载的配对候选**。M保留交互、唯一参数、普通32／矢量8声部、本地混响及最终输出；W保留实际CNN、手机接收解码和唯一录音对象。task2、单板及历史失败／回退保持原样；未操作板卡、SRAM或Flash。[结构化证据](DUAL138K_TASK3_PREBOARD_V77_20261109.json)绑定本轮输入与结果。

| 项目 | M | W |
| --- | --- | --- |
| 配置 | `custom138k-workstation-task3-m-preboard-v1` | `custom138k-workstation-task3-w-preboard-v1` |
| 候选身份后缀 | `3247a2f36593ac05` | `3e256b6b89ace0fa` |
| 来源锁／暂存文件／编译输入 | 1112／744／289 | 1166／729／202 |
| 完整综合审计 | 29/29 | 27/27 |
| 综合Register／LUT／ALU | 58439／70247／18338 | 46826／59034／15892 |
| 综合BSRAM等效／SSRAM | 212／242 | 253／779 |
| 独立prepare | 全部744个暂存文件逐字节一致 | 全部729个暂存文件逐字节一致 |

综合BSRAM等效值不能代替实际物理数量。W固件编译命令路径和`.ci/.su`诊断文件哈希导致部分元数据差异，安装ROM、所有编译输入及候选身份一致；M元数据也一致。

## 本轮改动与验证

W在原有命令捕获边沿预计算完整33位`offset+length`，随同一有效tuple捕获；范围比较使用该值，没有增加命令周期。显式v2适配保留父／子哈希、精确锚点和逆变换。六种捕获／异步时钟组合、8192组任意共同状态对应边沿及具体加一负例通过；实际完整网表证明33位加法、CE／CLEAR／CLK／INIT和消费者闭包。

W延迟DMA／FIFO局部布局进入维护的`--w-delay-locality`准备和审计入口：2233个逻辑单元、8个RAM排除，原生引脚、SDC、时钟和预算保留。完整PLL审计可逐字节重建CST；实际配方重放及11个破坏性反例通过。v24b原先因外部布局不可重建而拒绝的PLL审计现通过，旧位流和历史拒绝记录未改。

v77的M/W综合严格复用与v75／v76相同的全部编译字节，不重复综合。M绘图、事件准入和v71消费者对应证明、W捕获契约的绑定输入均未漂移。`test_current_workstation_sources.py`17/17通过；未变的滑音／效果、TF、识别、手机及录音下载输入继续复用各自有效证据，不扩大验证范围。

提交前复核：W实际布局重放通过且拒绝11个破坏性反例；实际来源／路由修复测试10项通过，另一项M启动测试因误选无SDF的v23夹具失败。该项改用保留的v22完整路由夹具重跑通过，明确不作为v23的物理接受证据。全部失败日志保留。

## 最新物理结果

M v23 `D21109C9`仍为PR0004、2587条未布通网络，部分报告为Logic90759、Register58439、CLS60640/69120、BSRAM253/340；无完整STA／SDF／位流。唯一一次同VG／CST／SDC的P2R1（v24 `D21109CA`）在1801.23秒被监督器超时终止，输入未变，同样没有可用位流。

为定位当前失败，原v23 P2R0在隔离目录仅开启厂商诊断并关闭位流生成，990.75秒后重现相同2587条网络。只读捕获的DesRoute计数与厂商失败数完全相同；2345条匹配到真实FF／组合驱动，242条硬原语等显式未匹配。主要驱动范围为显示producer699、reader661、writer157、DDR246；高扇出失败网络包括cancel delivery pending1360、USB输入控制595及renderer enable533。此清单是诊断依据，尚未证明路由失败根因，不是发布证据。

W v25 `D21109D9`源自本轮W候选，P2R0在758.27秒完成，输入未变，最大实际进程树footprint约6.78GiB。物理资源为Logic80178、Register46826、CLS56197/69120、BSRAM287/340（SP3、SDPB148、SDPX9B40、pROM96）、DSP122/298。

| W v25门禁 | 结果 |
| --- | --- |
| 全局setup／hold | **−1.943／+0.151ns** |
| 全局recovery／removal | +2.062／+0.304ns |
| 显式max／min最差余量 | +0.557／+0.378ns，无负路径 |
| 完整PLL／DDR重建审计 | 通过，所有绑定输入未变 |
| 配对发布／加载 | **未放行，禁止加载** |

加载文件为`w-preboard-physical-v25/impl/pnr/custom_138k_integration.fs`，SHA-256：`7e01a30db6784bde9ed4074a1dca828dba7084e453fefcae0262e31b93f34c5c`。`.bin`另有独立哈希，不能混称加载位流。文件位于缓存根`/Users/sphenicidition/.cache/gw138k-task3-20261108`，只保存失败候选证据。

首次PLL调用因脚本导入方式失败，第二次因未配置官方仿真库失败；保留日志后以直接脚本和`GOWIN_SIMLIB`重验通过，未改冻结脚本或厂商字节。

捕获结束地址修复已移走旧最差范围链。当前最差DDR路径为tag→owner veto→即时transport fault→ddr client ready→delay DMA state；clk50为observed context→status pending（−1.913ns），音频域为delay overflow sticky→decoder overflow count（−1.333ns）。其余raw clear终态、BLE结果及deferred路径仍有负setup。显式约束及PLL通过不能代替全局时序闭合。

## 复现与后续

使用维护`build.py --prepare-custom-board --workstation-profile`，分别选择表中配置，输出到新目录；锁定输入根为`/Users/sphenicidition/.cache/gw138k-task3-20261103/locked-netlists`，RISC-V前缀为`/Users/sphenicidition/.local/opt/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf`。本轮prepare目录为缓存根下`{m,w}-preboard-prepare-v77{,-repro}`。物理准备保留preboard releases、primary clk50及DDR参考选项；W额外显式选择`--w-delay-locality`。JSON绑定完整配置、来源锁、安装字节、实际审计与诊断位置。

PLL审计按脚本方式运行`tools/workstation_physical_pll_audit.py`，设置`GOWIN_SIMLIB=/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/simlib/gw5a`。本轮没有放宽时钟、预算或功能时序例外。

后续按上述真实失败网络和最新STA选择结构修复，先做针对性回归，再对变化的完整编译输入重建。最终还需M完整路由、两板全局／显式STA、绑定最终身份的CDC／PLL／资源及复现全部通过。[SRAM清单](DUAL138K_TASK3_SRAM_CHECKLIST_20261108.md)已经准备正确目标、连接、加载读回、回退和功能步骤；真实LCD吞吐、DAC延迟与整机演示留到上板阶段。当前goal保持未完成。
