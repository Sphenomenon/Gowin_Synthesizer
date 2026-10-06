# 50MHz 低 BSRAM 时序修复（2026-10-07，进行中）

## 当前状态（随最终 P&R 更新）

板上保持完整full84（0x00000084），模型E；未烧录任何0x85候选。
最终RTL快照735aaa3：Viterbi标量流水、CQT降采样/幅值/请求地址分拍、前端写译码寄存、
本地DDR并行授权与诊断级别两级同步。原50MHz/20ns约束、所有缓存和冻结文件保留。
资源：最终综合BSRAM216、SSRAM1607、寄存器40609；此前完整候选PNR均260，最终
物理结果待查。幅值一步只加82FF，不增加RAM；整套修复的前端译码使原4Kbit分布式
RAM转为4096个FF，加4116FF，需明确计入逻辑代价。未经实测不能宣称窗速率不回退。

最终源码验证全部通过：四种CQT本地/DDR配置逐笔对照、2100组独立整数幅值oracle、
12帧六层哈希/出谱A/B、完整暂存树18项（含TF16、guidance与DDR隔离）。
全新默认综合route1候选040915_479309正在P&R。另042458_983585只把Gowin综合目标
从auto设为timing；RTL/IP/模型/SDC全部逐文件相同，允许复用逻辑测试，资源/布线/
CDC/QoR必须独立复核。没有把额外工具选项当作闭合证据。

已完成的route0诊断候选032151_169144：clk50 Fmax26.342MHz、setup WNS=-17.961ns，
暴露幅值和地址长链，未闭合、不可部署。后文为调查记录，早期“进行中”的候选名称
表示当时状态；最终选用位流与板级验收将以本节和LATEST_WORKSTATION.json为准。

本轮目标是修复当前 full84 的 50MHz 域，保留 CNN 分级缓存和示波器/TF 集成，
P&R BSRAM 预算不高于 260。板上仍是 0x00000084；候选 0x00000085 尚未烧录。
全设计音频/USB/DDR 的其他时序问题与 50MHz 域闭合分别记录。

## 基线与定位

- 当前基线：`results/workstation_scope83_20261006_230626_011557/`，提交 `ffd007d` 的
  权威状态记录板上 full84，P&R BSRAM=260。
- 原报告 clk50 Fmax=41.813MHz，Setup TNS=-669.020ns / 356 端点，Hold TNS=0。
- 原报告默认最差 50 条主要被跨时钟路径占满，没有显式 clk50->clk50 setup/hold
  报告。不能依据总 TNS 确定全部内部瓶颈，更不能把构建成功标记为闭合。
- 保留所有原始 RTL/时钟/时序例外，在复制的完整 full84 树加专项报告，独立增量
  P&R 定位：`results/clk50_fix_20261007/baseline_clk50/`。基线原树不修改。

## 第一项 RTL 改动

`rtl/music/basic_pitch_viterbi.sv` 将候选循环拆分为 READ / SUM / SELECT，最后一项
比较完成后另拍 COMMIT。原来一拍串联 RAM/mux、转移代价、32bit 加法、比较、选择与
最终分数加法，现在用 3 个 32bit 标量寄存器隔开。score、prev_score、emission 与
历史 RAM 原样保留；未加数组、未复制 CNN 特征缓存，卷积 MAC 节拍未改。

`p_cnt` 在 READ/SUM/SELECT 期间保持，索引与数据一致；严格 `>` 保留首次获胜的
平分规则；最后候选先更新 best，再提交分数/回溯指针，避免 NBA 最后一项漏比较。
理论额外周期为 171×89×(2×89+1)=2,724,201，即 50MHz 下约 54.48ms/172 帧窗；
板上窗耗时影响仍须实测，不能把理论值当实测。

## 已完成验证

- Icarus 四态 172×89 数学递推 oracle PASS：全部分数/回溯指针、静音/平分、DDR
  延迟/背压、并行 delay 写流、28 项出谱。旧地址负对照仍在 frame=1/state=0 捕获碰撞。
  证据 `results/clk50_fix_20261007/dp_oracle/`。
- 新 full85 完整 staging 的 scope 8 项、菜单/playlist/guidance 7 项已 PASS；
  完整回归 18/18 PASS（含 TF 16 项、delay 等价和回溯隔离）。
  另三项 Viterbi 有序出谱、DDR 出谱和首音符对齐 TB 全部 PASS。
- 12 帧 CNN 双配置 PASS：逐 wave 六层哈希、写出覆盖和 3 项出谱一致，最终六哈希
  与迁址前后已验收参考完全相同。证据 `results/clk50_fix_20261007/cnn_ab_12frames.log`。

## 构建与检查工具

- `tools/build_full_song_85_clk50_timing.py` 从完整 full84 树构建，仅显式覆盖允许文件，
  UserCode=00000085，保留原 SDC 并新增 clk50 专项报告。构建前后检查输入与冻结 SHA256，
  P&R BSRAM >260 即失败；不操作板子，不修改部署状态。
- `tools/audit_clk50_timing.py` 必须看到显式 clk50 setup/hold 报告，检查 WNS、端点
  TNS 和 Fmax。缺报告返回未闭合；不会把默认报告遗漏的路径当通过。
- 第一候选：`results/song_guide_full85_clk50_20261007_002805_594995/`，完整构建进行中。
- 五项冻结文件全部 SHA256 未变，BP 回溯地址继续保持 0x30400000。

尚未宣告时序闭合或候选板级验收。最终结果将在取得 P&R 路径、资源和回归后补充。

综合资源复核：基线/候选均为 SYN BSRAM=216，Viterbi 均为6。50MHz 综合估计
从50.351提升到54.406MHz；最终资源与时序以尚在运行的 P&R 为准。

## 专项报告确认后的 CQT 修复

- 基线增量 P&R 已完成。该次路由 clk50 WNS=-4.114ns，Hold WNS=+0.160ns，
  Fmax=41.469MHz，Setup TNS=-791.625ns/392 端点；与原部署的 41.813MHz 分别记录。
  100 条内部路径的最差项为 `u_cqt/dec_i -> dec_head / sig_pending_data`；
  Viterbi `p_cnt -> score` 同时存在约 -3.671ns 的长链。
- CQT 降采样的 `dec_raw/valid -> sample mux -> multiply -> 48bit add -> saturation`
  拆分为请求时锁存 valid、16x16 乘积寄存、累加、最后单独写回。16x16 的精确积
  使用32bit并显式符号扩展到原48bit累加器，保留原移位/饱和语义。
  第一128项仍延迟到源已消费后 flush；未改变原信号/头部缓存分配。
- 额外标量为 valid 1bit 和 product 32bit。每降采样 tap 增1拍，每输出末尾增1拍；
  43844样本、8次降采样的输出数共43671，理论额外 43671×257/50MHz=224.469ms/窗。
  加上DP约54.48ms，理论总增量约279ms，相对约57s/窗约0.5%；实测仍待板级确认。
- 第一项仅DP候选在确认上述 CQT 证据后取消 P&R，没有烧板，不写作闭合。
  合并候选 `results/song_guide_full85_clk50_20261007_004457_617018/` 正在完整构建。
- 新测试 `sim/music/run_cqt_pipeline_equivalence.py` 从已验收Git标签取原CQT RTL，
  分别验证片内/DDR模式的三窗三octave，逐笔比较896次信号写与216个输出bin，
  覆盖极值、伪随机、饱和、127/128边界及非等长DDR等待。初次DDR测试达到过短周期顶，
  两窗已一致；提升到明确5M周期并补充片内写比较后，片内/DDR三窗全部 PASS。

合并 CQT+DP 的12帧 CNN A/B 也已 PASS，六层哈希与此前参考相同，出谱3项一致。

合并候选综合 clk50 估计61.890MHz，SYN BSRAM=216，CQT自身=0，Viterbi=6；
与 full84 的RAM结构相同。尚以 P&R 实际 setup/hold 与资源数决定是否闭合。

合并候选最终暂存树的18/18门禁已重新通过。资源差分（SYN同口径）：Register +14、
LUT +202、ALU +51；BSRAM/SSRAM/DSP净增均为0。机器记录见同名JSON。

发布检查边界测试 `sim/music/test_clk50_audit.py` 4/4 PASS：复现 Gowin HTML缺频率
单元格、缺hold报告、setup/hold微小负裕量、放宽24ns时钟，后3类都不能误判闭合。

## 复位时序门禁补充

`audit_clk50_timing.py` 现在区分 setup/hold 闭合与完整 clk50 门禁，后者还要求
异步复位 recovery/removal 有非负的全局最差报告或显式 to-clk50 报告作为证据。
缺复位报告、只有其他时钟域失败的全局报告、或已知 clk50 复位负 slack，均拒绝发布。
六项门禁单测 PASS。基线复核 recovery=-6.053ns，目标为
`u_song_command_cdc/destination_release*/CLEAR`；removal=+0.253ns。
该链是跨时钟复位的三拍本域释放入口，后续若补约束须仅覆盖此入口，保留
释放寄存器输出到本域业务寄存器 CLEAR 的检查。
证据 `results/clk50_fix_20261007/baseline_clk50/clk50_reset_audit.json`。

## 选歌命令 CDC 约束与路由证明

构建工具对后续候选补充 `u_song_command_cdc` 的4bit保持数据20ns最大传播时间、
保持总线hold例外、握手第一级采样D例外，以及两个三拍本域释放链的CLEAR入口例外。
未屏蔽第二级同步器、额外settled拍或释放链输出到业务寄存器的复位时序。
新工具 `tools/audit_clk50_cdc_routes.py` 从实际VO/SDF检查3拍释放链、双向2FF、
req第三拍及4bit保持数据直连与传播时间，并要求上述具体约束确实存在。
基线结构检查PASS，最大保持数据传播0.635ns；因基线缺上述约束，发布检查仍为FAIL。
证据 `results/clk50_fix_20261007/baseline_song_cdc_routes.json`。
当前仍运行的首个合并候选SDC不被中途修改；新约束将在下一次构建/路由中采用。

## 构建耗时与增量对照

首个合并完整路由在80分钟后仍处于最后优化，进程持续计算且无错误。为了取得
含命令CDC补约束的结果，另起 `results/song_guide_full85_clk50_20261007_020351_908656/`，
从已完成full84的 `.pr` 作增量参考，显式覆盖RTL重新综合；不是复用旧逻辑网表。
构建工具校验其余全部RTL/IP/初始化数据与工具选项、冻结文件和参考 `.pr` SHA。
对于只有SDC变化的同身份full85，也支持更严格的全部逻辑一致后复用综合。
两个候选独立目录；最终都要通过实际PNR的时序/结构/资源门禁。

## 首轮完整PNR结果与第三项修复

完整PNR耗时约84分钟，SYN216/PNR260，clk50 Fmax46.083MHz，内部
WNS=-1.700ns、hold=+0.164ns、Setup TNS=-115.919ns/190端点；未闭合、未烧录。
最差内部路径已移到前端 `wr_ptr -> dline_RAMREG*/D`，原DP/CQT降采样不再占据最差位置。
前端将256项写地址译码寄存为one-hot和16bit写数据，下一拍提交到原延迟线。
采样计数/系数节拍不变；next_window_i时仍提交之前已接受的数据；无新增RAM数组。
另外报告暴露format/source音频状态直接驱动clk50 sticky/UART：补2FF，再使用第二级。
TF PCM、score和playlist的Gray指针第一采样级按10ns传播边界约束，保留后级STA，
被优化成binary MSB的Gray最高位只匹配该位，未屏蔽全部二进制指针。
新候选 `results/song_guide_full85_clk50_20261007_021238_778346/` 从首轮完整PNR
结果增量路由并重新综合；02:03候选在新路径明确后取消，没有烧板。
前端独立旧RTL对照：本地/DDR系数各4窗、512输出、1295PCM，所有控制/输出逐周期
等价，覆盖极值/饱和、环回、背压和窗口换页PASS。首版TB在最后一次NBA输出
计数前提前终止，修正采样时机后PASS；没有把该TB断言错误归为RTL失败。
证据 `results/clk50_fix_20261007/frontend_equivalence_final/`。

## 前端候选综合与约束修正

前端/diagnostic候选18/18回归通过（`current_regression_20261007_021511_989953`）。
综合BSRAM仍216，clk50估计62.233MHz；SSRAM由1671降到1607，寄存器
36393->40509：one-hot逐项写回让原4096bit延迟线从分布式RAM变为普通寄存器，
而不是只增加256个控制FF。这是零新增BSRAM的面积交换，寄存器总量约30%容量。
该候选SDC在进入PNR前因已被优化掉的3个write-binary-MSB模式报TA2003，
保留记录为失败，未烧录。修正后仅read最高位匹配已证明存在的binary别名，
write侧使用保留的Gray名；新候选 `results/song_guide_full85_clk50_20261007_022219_094886/`
核对全部逻辑/模型/工具输入一致，尝试复用综合与增量参考。Gowin实际在新目录
自动重新综合，不能宣称跳过综合；构建工具新增再生成输出记录，不把报告输出
变化误算成RTL输入漂移。运行中的旧构建脚本若误拒绝再生成输出，将以另份
源输入校验澄清，保留原始记录。最终PNR仍待完成。

前端合并后的12帧CNN A/B PASS，六层哈希/各层写出覆盖与3项出谱均一致；
耗时558.909秒，证据 `results/clk50_fix_20261007/cnn_ab_frontend_12frames.log`。
修改后已验收原前端逐周期、CQT逐bin和DP逐分数各有独立对照，再加完整CNN A/B；
这些逻辑验证不代替待完成的PNR和板上TRAVLER验收。

## 相同逻辑/约束的路由算法对照

最终候选route_option=1在最后优化阶段持续较久，另起
`results/song_guide_full85_clk50_20261007_025509_105405/` 使用官方默认
route_option=0，对照相同RTL/模型/SDC和20ns时钟。timing_driven=1、
correct_hold_violation=1、place_option=2仍保持。变更仅为PNR路由算法，
不降低时钟、不增RAM、不增加时序例外；两者均接受相同最终门禁。
构建脚本将PNR算法单独记入metadata，复用综合的核对允许此PNR选项差异，
其余综合选项仍完全匹配。

## 默认路由结果与本地DDR控制长链

默认路由在约21分钟完成，但50MHz Fmax36.471MHz，内部WNS=-7.419ns、
hold=+0.164ns、TNS=-849.353ns/315端点；BSRAM260。复位recovery=+12.128ns、
removal=+0.277ns通过。未闭合，未烧录。
完整最差路径经 `dec_i -> dec_raw/dec_in -> 本地DDR仲裁 -> dp_mem_ready ->
Viterbi d_cnt/RAM地址`，并非CQT完成信号本身。
CQT增加18bit标量请求地址，S_DEC_REQ先寄存，DDR有效tap由S_DEC_ISSUE再发出；
无效tap与本地RAM维持原节拍，避免范围比较穿过共享ready。
PCM pipeline内11客户端的else-if仲裁改成前缀OR授权、one-hot OR payload，
原sig/front/cqt/norm/model/cache/feature/weight/lut/nn/dp优先级和owner编号完全保留。
全局冻结DDR仲裁器没有编辑；本地仲裁不加队列，不增加事务拍数，不增加RAM。
有效DDR降采样tap新增1拍，上限约43671×256/50MHz=223.60ms/窗；
加前两项理论增量上限约503ms/57s窗（<0.9%），卷积帧循环MAC节拍仍不变。
新候选 `results/song_guide_full85_clk50_20261007_032151_169144/` 使用默认路由。
CQT原RTL对照再次PASS（两种模式各3窗×3octave，896写和216bin/window）；
本地仲裁抽取真实新/旧RTL穷举16384例PASS，覆盖2048请求mask、ready/blocked、
读写组合、数据/地址/owner与one-hot ready。TB生成器先出现声明语法与wire lvalue
错误，修正后通过；真实RTL编译及CNN仿真正常。
本轮编辑最初的enum替换断言没有匹配，导致启动了一份旧RTL重复构建，已立即
取消并记录 `results/song_guide_full85_clk50_20261007_032038_555505/candidate_status.json`。
证据 `results/clk50_fix_20261007/local_arbiter_equivalence_pass/`、
`results/clk50_fix_20261007/cqt_request_equivalence/`。

最新请求/仲裁合并候选18/18回归PASS，综合BSRAM216、SSRAM1607、寄存器40527，
比前端候选多18FF；LUT57239（前端候选57581），综合clk50估计61.890MHz。
此时尚无本候选PNR报告。真实RTL snapshot已逐项核验匹配提交 `5cf13b2`，
构建开始时HEAD较旧，metadata另记`rtl_snapshot_commit`，不混淆开始提交与源快照。

请求/仲裁最终合并的12帧CNN A/B PASS；六层最终哈希仍为
`e1e1c8e5/7539c275/c2ca22ba/92afdeec/1ea6f727/5432e32a`，所有层写出覆盖及3项出谱
一致。714.176秒walltime为主机并发构建负载影响的仿真耗时，不是FPGA窗耗时。
证据 `results/clk50_fix_20261007/cnn_ab_arbiter_12frames.log`。

## 发布前全板QoR复核

默认route0对照虽更快出报告，但音频Fmax54.297->28.216MHz、USB38.726->13.681MHz，
明显劣于已运行的full84；该候选不可部署。不能只看clk50门禁而忽略工具选项
带来的其他域退化。最终新RTL另用route1全新P&R：
`results/song_guide_full85_clk50_20261007_034837_423036/`，不复用不良route0路由参考，
避免较大的仲裁改写造成长时间增量匹配。新RTL route0增量构建保留为定位对照，
03:46启动的route1增量构建及时取消；所有候选均未烧录，板上仍full84。
发布前需完整clk50门禁、BSRAM/冻结/输入/CDC检查、其他域QoR对比与板上冒烟。
这不是宣称本轮会闭合音频/USB/DDR全设计时序；各域结果将如实记录。


## 幅值及反射地址路径分拍

请求/仲裁 route0 实测 SYN216/PNR260，clk50 Fmax26.342MHz、WNS=-17.961ns、
TNS=-1507.677ns/590；hold+0.164ns、recovery/removal通过。工具及源输入检查通过，
时序失败，未烧录。路径暴露CQT平方DSP输出→平方求和→动态位选择→开方比较/减法；
另有sig_len→反射地址→共享DDR请求长链。route0其他域也显著恶化，仍不可部署。

提交735aaa3使用已寄存的最后一tap累加器，分S_SQUARE/S_SQUARE_SUM保存两个64bit
平方和总和；开方从sval[63:62]消费两位并左移，替换sbit动态位选择。保留所有符号、
64bit截断、加法wrap及最终root位模式。反射地址另加18bit标量寄存器，经S_MAC_ISSUE
再发DDR请求；系数在S_MAC_REQ保存，保持请求等待中的值。本地RAM原读时序不变。
无新增RAM数组；卷积MAC节拍未动。该步完整窗的保守增量为285.887ms，累计上限约
0.789s/57s（<1.4%），实际窗耗时仍需上板衡量。

四种CQT信号/系数配置逐项对照已验收RTL均PASS，每种3窗×3octave、每窗896信号写
和216bin。Python独立整数oracle对2100组signed48边界/随机值、平方uint64 wrap和
math.isqrt结果均PASS。新完整route1候选040915_479309正在构建，12帧CNN A/B和18项
暂存树回归在运行。老022219增量route1已因被多轮明确RTL修复替代而取消；未烧板。

CDC结构检查初版只支持直接Gray寄存器连接，因此拒绝TF已有clear-to-zero LUT及
合并到父级的clear_meta。修订检查严格证明LUT3 truth table为meta==seen时透传指针、
否则清零，seen.D采样已核验meta.Q；Gray源仍要求跨域注册源，第二级同步链仍逐bit
核对，并把LUT及两段路由计入10ns飞行时间。原始失败记录保留；修订检查5项正/负
门禁测试通过，route0实体证据PASS，最长Gray飞行1.512ns。TF RTL与SDC均未因此修改。


最终幅值/地址暂存树18/18回归PASS（041219_870955），综合BSRAM216，寄存器40609，
SSRAM1607；相比请求/仲裁候选多82FF，Viterbi仍6BSRAM、CQT仍0BSRAM。
原板full84只读15秒冒烟3/3 PASS，模型E、UART CRC0、音频health0；没有控制命令、
没有PCM文件，也没有把该次冒烟当作CNN36项验收。实际板仍0x84，候选均未烧录。


最终幅值/地址RTL的12帧CNN A/B PASS，六层哈希保持已验收参考值，层写出覆盖
25344/3168/33792/1056/33792/1056完全一致，3项出谱相同。主机walltime696.913s
只用于仿真记录，不是板上处理窗耗时。证据cnn_ab_magnitude_12frames.log。


## 系列默认路由对照

官方SUG100 Place and Route Options明确：GW5A(S)(T)-138的默认route_option为2，
用于提高路由速度；1以编译速度换更优路由搜索，0对本设计已有明显QoR退化证据。
新增results/song_guide_full85_clk50_20261007_045710_715943，同735aaa3 RTL/模型/SDC、相同timing综合目标，只把route1改route2，
逐文件SHA256证明仅Tcl改变，逻辑验证可复用，实际时序/资源/CDC/QoR仍独立审计。
旧034837（未幅值分拍）耗时>60分钟的路由已因被新RTL取代取消，未烧板。
最终auto/timing route1都继续完成，本次不宣称route2会闭合或等价于已验收的硬件。


## 接近闭合后的前端最后两条链

040915默认综合route1完整报告：SYN216/PNR260，50MHz Fmax49.250、setup WNS=-0.304ns、
TNS=-3.342ns/22端点，hold+0.165ns/TNS0，recovery/removal通过，CDC与scope路由审计通过。
不能把-0.304ns当通过；未烧录。音频55.416MHz、USB38.898MHz接近或优于full84，
但HDMI pixel退到121.599MHz（<148.5，基线151.305），因此本候选也不宜部署。

剩余负路径20条来自restart/sample_valid长控制链再串256路写译码，另2条tap_cnt→
前端乘加/饱和输出为-0.015ns。a1b8537将dline_we_q每拍只保存wr_ptr onehot，
有效位独立进dline_valid_q，数据/地址/valid仍同拍排队、下一拍提交。DDR系数路径
在现有tap_wait&&coeff_valid拍保存48bit精确乘积，下一拍原MAC加法/饱和节拍不变；
片内同步ROM原时序保留，不提前采样尚未更新的ROM数据。无新增RAM，无额外tap/输出拍。
原两种前端系数端口逐拍等价PASS，扩展同步ROM与寄存DDR载荷模型在验证中。
新候选053045_091636使用timing综合、系列默认route2，尚未烧录。旧735aaa3的
timing route1/2仍运行，若也通过可作为少改动对照，最终选用源码必须与位流匹配。


最后前端两处修复的四种系数端口模型全部逐拍PASS：组合片内、组合DDR、同步ROM、
寄存DDR载荷；各4窗、512次输出、1295 PCM输入，所有控制/地址/样本/输出拍均相同，
最大168990周期。初次4端口扩展触及原120s主机时限而未取得完整结论，没有RTL断言
失败证据；改为vvp -i实时保留日志、600s时限，1M周期硬顶保持，已完整PASS。
证据frontend_final_all_ports_streamed/result.json。只读基线板上仍0x84/模型E。
