# CNN Flash→DDR 实施记录

截至2026-10-10 03:19，完整工作站AD已通过三次实际配置Flash重载和实时演奏，但实际DDR时序未过门禁，板上及默认版本已恢复full85。B3～B9均已完成离线验收并因DDR UI负裕量被拒绝；B9最差−2.688ns，未写板。BA～BD正在独立构建，BD绑定实际注册仲裁器的50组TF协议已通过。状态表见CNN_FLASH_BOOT_CURRENT.md，由实际构建/验收工件生成；以下记录保留各阶段证据。

AD最终268/340物理BSRAM，clk50 55.362MHz、视频187.261MHz。严格时序门禁仍发现DDR UI setup −2.107ns（旧文字/分析渲染为主，hold+0.165ns）和视频PLL全传播10.757ns>10ns，因此AD只作为明确的临时诊断，**配置Flash已恢复full85、旧UART模型E及现场检查PASS，LATEST仍85**。AE保持AD全部RTL，仅增加严格8ns DDR路径/6ns PLL端点物理预算；其已完成结果仍未闭合。原有时钟、hold、CRC、自检和独立PLL10ns门槛全部保留。

实证工件：`results/workstation_flashad_20261009_local_payload/temporary_flash_diagnosis/result.json`（三次真实Flash与恢复）；`sram_diagnosis/result.json`（完整工作站SRAM诊断）；`automatic_acceptance/result.json`（正式时序拒绝）。以下为保留的分阶段历史，早期“正在构建/尚未验收”只描述当时状态。


当前模型已写入外部 Flash 的 `0x600000` 分区，104,510 字节，载荷 CRC32 `AF01A61B`；Programmer 字节交叉校验通过。独立 SRAM 探针 0x96 完整读出 52,239 字并通过本地 RAM CRC；0x98 进一步通过实际 115200 波特率、内部 BPN1 串行连线和原模型解析器。这两项没有 PC 上传模型，均不代表完整工作站 DDR 验收。

独立 0x9E SRAM 探针进一步使用真实板载 DDR、原 DDR 平台/PHY、原 UART 解析器和 DDR16/CDC 端口：完整 52,239 字从 Flash 自主写入 DDR，并回读 CRC `AF01A61B`，连续三条来源=Flash/状态=E/DDR就绪=7。未使用 PC 模型上传，证明 Flash→实际DDR单独链路可行；该探针无CPU/显示/DMA并发，因此不算完整工作站验收。探针后已恢复full85/modelE。

完整工作站 0x95 的 clk50 闭合、Flash 配置状态正常，但模型 DDR 回读与 CPU 内存/UI 自检失败。兼容方案 0x97/0x99 保留 full85 原解析器、DDR16/CDC、CNN 和固件；两次布局 clk50 均未闭合。0x99 的临时 Flash 诊断确认真实配置 UserCode=99、状态=26020，但 CPU 自检未通过、自动搬运未启动；已经自动恢复 full85，重新上传其易失模型，完整启动及实时 scope smoke 通过。

0x9A 缓存修正构建已完成，SYN216、P&R260，clk50 Fmax51.569、setup+0.609ns、hold+0.165ns、TNS0。CPU bus满足要求，但视频134.229<148.5MHz，正式发布门槛拒绝。临时 Flash 启动诊断仍出现 DDR校准0、CPU0、模型0，已恢复 full85/modelE/smoke。缓存与 full85 逐周期等价、10,000周期统计比较和三帧 CNN 六层哈希回归均通过；这些仿真不替代完整板级DDR验收。

0x9C 的官方 `.p` / `inc_place` 构建在布线阶段持续约两小时未完成，已终止，工具返回 -15、冻结输入不变，没有生成可验收位流，也没有用于板级测试。此前0x93使用`.pr`入口的未布线网络失败记录保留；较新官方SUG100指定`.pr`，旧Tcl手册指定`.p`，因此扩展名作为根因的早期判断已撤回。

后续三个候选分别验证独立措施：0x9F 使用缓存等价修正、place3/route0，并对已知视频控制路径增加更严格的6ns约束；0xA0 保留原 CNN/缓存，通过官方 `.p` 入口和同名 `.pr` 配套文件复用完整布局/布线参考；0xA1 在 A0 基础上增加音频/视频 PLL 稳定后100ms的 DDR 初始复位门控。A1不改原PHY、DDR数据路径或正常恢复，启动顺序假设尚未经过硬件证明。三组当前仍在构建，全部结果通过资源、输入完整性和时钟门槛后才做正式 Flash 验收。

初始 DDR 门控的五项参数化仿真通过：1/8/31周期正常情况、0/50,000,001非法配置拒绝；覆盖无锁定、短锁定脉冲、最低等待时间、无时钟异步复位、重新启动和运行后辅助PLL失锁。

资源基线 SYN 216、P&R 260/340 BSRAM；Flash 启动模块没有模型 ROM。默认 serial 方案在 CPU/DDR 自检通过后先校验 Flash，再交给原模型装载器，启动耗时约 9 秒串行传输加 Flash/DDR 校验。非法/空白头和首遍载荷错误可回退 UART，第二遍模型变化或 DDR 错误显式失败。

部署工具先验证原 clk50 与 full85 原本通过的各时钟；CPU/视频退化在任何硬件命令前拒绝。十项离线部署/回滚测试通过，包括坏模型来源、自动启动失败位、FTDI 陈旧成功报文、CPU/视频时序退化，以及三次模型启动通过后实时演奏测试失败的自动回滚。

板上仍为可用 full85，LATEST 未提升；物理断电重上电未执行。机器可读结果与各工件路径见 `CNN_FLASH_BOOT_IMPLEMENTATION.json` 和 `CNN_FLASH_BOOT_TESTS.json`。

2026-10-09 10:43 的旧 full85 运行复查：CPU/DDR/模型E/三音/立体声/静音/Panic均通过，但健康字00010000表示累计序列化器欠载1次、核心故障0，因此整体烟雾测试判失败。原因未确定；10:46从已有Flash重载full85（没有重写配置、没有SRAM下载），恢复其旧易失模型后重新做完整实时测试通过，健康字00000000。失败与恢复记录分别位于`results/baseline85_flash_model_work_health_20261009_104311`和`results/baseline85_health_recover_20261009_104641`。此旧模型UART恢复不计入新Flash→DDR验收。

0x9F已完成：SYN216/PNR260，视频172.654MHz，但clk50 Fmax46.813、setupWNS-1.362ns、TNS-82.433/103端点；DDR UI84.737<100MHz，视频PLL_INIT全传播10.232>10ns。路由CDC审计通过，正式时序/PLL门槛失败；未执行任何9F硬件编程。A0/A1仍在布线。

官方增量文件说明冲突：SUG100-4.4.6E第42页要求布局+布线`.pr`，SUG1220-2.0E第44页却写`.p`。A0/A1的`.p`配对方式仍属实验，不是已验证修复；构建器新增显式入口格式记录，pnr默认按较新SUG100用`.pr`，仍保存并核验两份配套参考，任何未布线网络/时序/硬件失败都不验收。

A2备选：沿用9A的place2/route0、缓存与统计等价修正，增加6ns已知视频控制预算和100ms初始DDR门控；A3对照：保留A1原CNN/缓存，改为SUG100指定的`.pr`增量入口，`.p/.pr`配对hash记录保留。两者目前未测试硬件，不提升LATEST。

初始DDR等待的副作用已检查：100ms/4800帧超过P10维护用512项FIFO，新构建先在CPU/DDR/UI就绪后发内部一次Panic有序flush，再装模型，不改效果器/DMA/FIFO。独立串口控制测试与满队列后43000样本逐拍等价通过，另外2000样本为预期欠载的长停顿故障注入。已冻结的A1/A2/A3没有此历史对齐，不能作为正式发布候选；其布线结果可用于诊断，但部署器在硬件I/O前拒绝。

A0/A1的`.p`增量实验持续约110/90分钟仍未产出最终布线报告，已仅终止各自Gowin子进程，结果保留，无硬件测试。A3`.pr`对照和A4完整启动历史修正版继续；A2保留作布局诊断。

A2布局诊断已完成：SYN216/PNR260，clk50 44.792MHz/WNS-2.325ns，视频147.676<148.5，DDR UI192.167MHz；未执行硬件测试。A4在综合阶段由A5取代，返回-15、冻结输入不变。A5增加启动倒计时零值寄存：实际顶层HDL的30000周期边界转移对比和未强制赋值的2500012周期完整自然歌曲启动均逐拍一致，无新增启停延迟。

A5综合完成仍为216BSRAM；元数据记录缓存/启动判断等价修正、100ms初始DDR等待和一次启动Panic。已安排本地审计完全通过后调用统一物理验收入口，失败保留原始证据并恢复full85，LATEST不自动改变。当前尚未开始A5硬件写入。

A3`.pr`对照持续约65分钟没有最终布线结果，且没有后续启动历史对齐，已终止保留工件、无硬件测试。两种增量格式均未通过本项目完整验收，不宣称手册冲突已解决。当前A5全新布局/布线继续，先前其它未完成实验均停止。


2026-10-09 14时后的继续排查：A5临时Flash诊断未通过，已回滚full85+UART模型E并完成实时烟雾PASS；A6布局完成但视频139.745MHz不满足148.5MHz，未烧录。A5 CPU仍为UIBY、取指0x80000A5C，DDR校准/BIST通过但共享DDR故障置位，模型搬运尚未启动。

发现DDR UI逐路径建立时间违例被正Fmax摘要掩盖：full85 -3.648ns、A5 -5.470ns、A6 -4.314ns。尚不能据此断言物理根因，但已加入显式DDR UI setup/hold门槛。注册返回FIFO读信用补丁在3组真实DDR16/FIFO背压测试中通过；A9已启动新构建。另构建RTL/IP/ROM/引脚/时钟/工具选项完全一致的full85对照A7，仅改变配置身份。两者均尚未实体验收，LATEST不提升。


A9实际完成后仍未通过DDR UI（setup -4.368ns）/clk50（-0.108ns）/视频PLL_INIT（10.594ns>10ns），禁止正式烧录；视频自身180.580MHz已通过。对照A7配置二进制仅UserCode一字节变化。接着实现共享DDR命令/返回边界寄存并启动AA；八客户端独立内存模型的3组仲裁、掩码、返回顺序、tag满和复位测试PASS。32项tag、两拍命令发起/一拍返回；尚未核验AA物理资源/时序/实体，LATEST85。


AA临时SRAM实验中CPU/UI终于PASS，但Flash模型状态F/stage3，DDR读回CRC202C97F0与AF01A61B不符；已恢复full85及模型E/现场PASS，Flash配置未改。AA物理260BSRAM，DDR UI -6.783ns、video143.397MHz、clk50 setup+1.053ns但复位recovery -1.184ns，不具备发布条件。后续AB为one-hot ready+同步P10维护写FIFO，原效果算法/DMA保持；为这个FIFO明确配置264物理BSRAM上限，设备340。队列/仲裁独立测试PASS，完整效果器等价性仍在运行，AB尚未实体验收。

2026-10-09 16:58：AB最终P&R为264/340 BSRAM，clk50 56.016MHz、video151.651MHz及CDC/PLL检查通过，DDR UI真正同钟setup仍−3.773ns（hold+0.167ns），严格发布门禁失败。临时SRAM诊断的CPU/DDR已PASS，但音频自检BAD00008（CC123后48000样本仍1个voice），模型搬运未启动。已从既有Flash重载full85并恢复其旧UART模型E、实时三音/立体声/静音/Panic全部PASS；未写候选配置Flash，未做物理断电。AC将验证独立客户端请求槽和寄存仲裁选择，加局部TF写缓冲时序修改，不降低原自检或时序门禁。

AC请求边界验证：八路局部请求槽+寄存仲裁选择，三个tag深度/随机种子分别完成5275/5156/5393条独立参考命令，逐客户端有序、返回归属、带mask内存、tag满/连续返回/全复位均PASS；八组TF原版/修改版与直连/新仲裁、背压组合均PASS。完整52239权重NOR→内部UART→解析器→DDR16/credit→新仲裁→独立masked内存在竞争/背压下完成52239写/读、CRC AF01A61B、source=1，小规模31词为实际115200波特率。源对照发现根目录解析器增加CLK_HZ/BAUD参数，而冻结full85保留常量；默认语义完全相同。另以AC冻结源码补做测试，31词保持115200源码逐字相同，完整内容仅把RX实例波特率加速并显式记录原/测试哈希。AC尚在P&R，无板上/Flash启动验收。

AC冻结源码模型复验PASS：31词原115200解析器未修改；52239词仅在仿真副本替换UART RX常数为3125000，其余冻结源逐字相同，52239写/读、CRC AF01A61B/source1通过，覆盖竞争/背压。综合218BSRAM/1049分布式RAM/56239LUT/43058寄存器，物理占用仍待路由。CPU释放仿真重现原固件预设73/全效果/CC123，1189帧释放；干声与踏板双音均23887帧释放，均小于48000帧，固件自检门槛不变。

2026-10-09 18:00：AC完成P&R，264/340物理BSRAM，clk50 52.014MHz/setup+0.775ns；CDC/PLL PASS。DDR UI真实setup仍−3.183ns（hold+0.179ns），最差路径转为TF可用字节计算到旧command_buffer地址CE；video143.101MHz，pixel_reset到TMDS input_ones仍负。严格自动门禁在任何硬件操作前拒绝发布。继续有依据的局部retime，full85板上状态保持。

AD局部时序修改已提交6e8f104：TF payload CE改为本地idle，capture终值提前寄存；P10写/读FIFO均同步BSRAM且满标志寄存，物理预算268/340；显示启用/故障门寄存1个UI周期，TMDS只取消被den掩码覆盖的统计值复位。TMDS100000周期/325复位周期10-bit输出逐bit同原版；TF独立队列20000周期/4复位PASS、十二组流式/背压与UINT32终值拒绝/重启PASS；4800冷启动溢出后Panic恢复、43000正常效果样本逐周期同原版。Flash/UART/DDR16/credit/仲裁源码逐字同AC完整权重CRC测试版，单独记录复用哈希。AD仍综合中。18:12只读UART检查原full85模型E保持、控制/故障计数无异常；没有重写或模型PC传输。

2026-10-09 19:05首次完整工作站硬件成功：AD临时SRAM下载后自动读既有NOR权重，B138模型E/source1连续通过，未从PC上传模型；candidate_live_smoke全部PASS，三音/立体声/静音/Panic及CPU/DDR健康均通过。随后按诊断策略从原Flash恢复full85，其旧模型E和现场烟雾PASS。正式配置Flash未改，LATEST仍85，物理断电未验证。AD最终268/340BSRAM，clk50 55.362MHz、video187.261MHz及原先正时钟全部PASS；DDR同钟setup−2.107ns（最差旧文字渲染读X→textline），hold+0.165ns，video PLL ICPSEL传播10.757ns>10ns。正式发布门禁仍拒绝；模型持久化/自动装载已在完整工作站证明，时序发布尚未完成。

2026-10-09 19:29真正配置Flash验收诊断完成：AD配置与600000权重分区均Program/Verify PASS，逐字节model复验且保留原地址0配置证明通过；连续三次SRAM擦除→Flash重载，准确UserCodeAD/状态26020，每次模型E/source1至少3条新UART报告，无SRAM下载、无模型PC上传。全实时scope三音/LR/静音/Panic PASS。该次明确使用临时时序诊断override，release_eligible=false，物理断电未测；无条件回写/校验/重载full85，恢复其旧UART模型E并live PASS。AE只比AD改变更严格SDC和UserCode脚本，所有RTL逐字一致，仍布局中。LATEST仍85。

2026-10-09 20:06：AE（AD全部RTL不变，严格8ns DDR与6ns PLL端点物理预算）完成P&R268BSRAM，clk50 55.536MHz/video172.962MHz/原先正时钟与CDC通过；DDR严格8ns路径slack−3.514ns，实际延迟11.468ns，最差仍文字渲染。PLL完整传播10.523ns=IBUF0.532+clockroute3.807+C2Q0.275+RomDreg到ICProute5.909，原10ns审计失败；需源到端点预算收紧，不能把PLL预算改大。AE未上板。原AD真实Flash三次模型E/source1与现场PASS实证保留，板上full85已完整恢复。

AF开始完整构建：保留AD模型/DDR边界，增加51个坐标谓词预译码和一致stop的1拍renderer流水；Dashboard完整1920x1080加随机metadata/复位/stall共2137105像素逐bit同原版（仅额外1个enable周期），双renderer独立DDR背压下1036800双像素beat内容/地址/valid/last全部同原版，哈希与AF冻结源绑定。PLL以实际SDF分解为依据，对RomDreg/Q到ICPSEL/LPFRES直接设4.5ns物理预算，原官方helper及独立完整10ns审计不改。未修改显示算法/图形内容，纯流水延迟。AF仍综合中。

2026-10-09 20:54 AF布线/验收：SYN220、PNR268/340 BSRAM，clk50 56.454MHz、视频187.190MHz；DDR UI文字路径为13.800ns/余量-3.815ns，Fmax72.383MHz，hold+0.168ns。PLL审计首条失败10.561ns；另外逐端点检查的完整最差传播为RESET11.434ns，不能只报告首条设置线。scope CDC和clk50 CDC通过，严格发布门禁失败，自动验收在任何programmer IO前停止，板上仍85。

B0将文字锚点的常量减法和动态卡片命中移入现有预解码级，增加延迟仍为1个enable周期，停顿语义及全文本优先级保持；未触及模型、CPU固件、DDR PHY。完整1920×1080含分析页的2,137,105次像素比较PASS；两独立完整renderer在随机DDR停顿下1,036,800双像素beat内容/地址/valid/last一致。延迟读指针32位并行+4通过1,001,024组输入含进位/UINT32环绕/非对齐值，TF11种容量含非2幂退回原算法的1,100,022组合法offset检查通过；TF16种native/direct/backpressure组合通过，P10双同步FIFO含新指针在43,000正常样本上逐位一致，2,000长停顿及4,800冷启动/Panic场景按预期通过。全激励只在仿真内存，不保存音频文件。测试证据：CNN_FLASH_BOOT_B0_COORDINATE_TESTS.json。

B0使用官方placement1/route1算法，候选冻结输入完整校验，资源上限仍268。指针DMA的新允许项仅接受确定性的、逐位验证过的+4转换，原源码哈希仍强制一致。准备阶段第一次被旧冻结白名单拒绝，未综合/未生成bitstream；拒绝产物另存prepare_rejected并修正精确规范化检查后，重新启动B0。实际时序/资源及烧录状态以最终automatic_acceptance为准。

21:38补充修正测试证据的键名：P10新FIFO实例和新DMA同时派生时原单一键会覆盖前者，改为唯一derived文件名并重新执行整套冷启动/43000样本逐位测试PASS；TF16组合增加每个变体的独立源哈希，实际B0的power_two_ring和FIFO/DMA各文件哈希已逐项匹配。功能未改，不能用单一变体哈希代表所有变体。

物理修正准备：AF参考PLL长连线已定位，设置线单独5.916ns、RESET组合加最后一段5.776ns；full传播RESET11.434ns。新增可选locate-reference-pll-helper使用官方SUG935 GROUP/GRP_LOC将初始化helper区域置于R[100:108]C[24:44]，所有官方源/时钟/审计门槛保持，非exclusive。准备/冻结源码检验PASS；不添加到在运行的B0，是否采用取决于B0实测。准备阶段不分配UserCode，无hardware IO。

2026-10-09 21:39只读核验当前板卡：UserCode85/status26020，三条fresh B138均模型E（旧85未实现source字段，值0）。没有UART写数据，没有配置/模型写操作；结果保存B0/baseline_readonly_status.json。

B0综合实测：220 BSRAM、505 SSRAM、43533 FF、55398 LUT；相对AF（43438 FF、55674 LUT）为FF+95/LUT−276，BSRAM不增加。PNR物理占用仍待最终结果，不将综合220当成完整物理用量。

21:54 B0完成：物理BSRAM268、clk50 54.326MHz、视频183.837MHz、DDR UI摘要227.082MHz，所有先前正时钟摘要通过。明确same-clockDDR UI setup仍-1.799ns/hold+0.167ns，最差是read_x→effect_text_x，随后render_meta→动画effect_x；PLL首条10.360ns失败。clk50/两项CDC通过，发布门禁阻止所有hardware IO，LATEST/board仍85。不能以227.082MHz摘要替代真实CE/约束路径检查。B1只增加官方参考PLL辅助逻辑区域约束，自动门禁失败后开始构建，其它B0 RTL完全一致；实际物理区域合法性/布线改善待测。

22:26 B1完成：物理BSRAM268，clk50 56.981MHz、DDR UI摘要234.288MHz；参考PLL区域合法并且全部独立PLL_INIT路径通过，最差全传播7.964ns<10ns，ICPSEL0为5.366ns（B0为10.360ns），官方helper/参数未变。DDR UI仍setup-1.718ns/hold+0.172ns，视频134.533MHz未满足148.5MHz，最差pixel_reset→TMDS输入统计7.421ns。两CDC通过但发布门禁失败，programming_started=false，board/LATEST85。后续精确修正仅针对报表指出的动画晚选择、卡片双减法和TMDS输入popcount，保留原时序/优先级/参数，所有等价测试先通过再冻结下一候选。

B2冻结并启动：保留B1参考PLL区域，只变dashboard动画/文本坐标并行组合、TMDS4-bit LUT popcount、UserCodeTcl。动画穷举8mask×64order×3id×2048位置3,145,728组和2048×2048文字相对坐标4,194,304组共7,340,032组PASS。最初的动画else错误把“有效mask但id缺席所有order”的情况定位到第三位，完整随机元数据像素测试明确失败；修复为原停车位后重新执行像素/双渲染器/独立穷举全部PASS，只有修复后的源进入B2。TMDS100000周期含所有256数据及325reset周期10bit逐拍一致。source-bound哈希匹配，原B0的TF/P10/FIFO/DMA测试逐项哈希复用。具体见CNN_FLASH_BOOT_B2_CARD_TMDS_TESTS.json，不将未测候选写板或更新LATEST。

B2综合实测220BSRAM/505SSRAM/43555FF/56555LUT，所有完整工作站必需模块审计通过（USB/Push/合成/矢量cue/TF FAT-SPI-DDR播放/BasicPitch/DDR/CPU/HDMI/串联效果）。新增并行卡片运算的LUT成本已明报，PNR物理计量尚待结果。

B1还暴露A坐标→B背景色的旧长优先链；趁B2布线准备背景坐标预解码，只把纯a_x/a_y条件在原A寄存同一enable捕获，文本/动态波形和颜色选择时刻不变，不额外增添像素周期。包含分析页2137105像素、完整renderer1036800双像素beat的逐位比较通过，源哈希135a2507…；未修改B2输入，等待B2实际路径决定是否采用。见CNN_FLASH_BOOT_BACKGROUND_COORDINATE_TESTS.json。

B2冻结源回归：CPU preset73全效果CC123在1189帧释放，干声和双音sustain在23887帧释放，均满足48000帧截止，三个场景PASS；11项离线部署故障测试再次PASS，Programmer/UART均替身，不能代替实体。完整31字模型以真实115200通过，52239字CRC仿真仍运行。

B2冻结源全模型回归PASS：52239字NOR→双遍片内串行→原解析器→DDR16/credit→寄存共享仲裁→独立掩码内存，含scan/writer并发及native背压；52239写/52239读，CRC AF01A61B、source1。完整数据为3125000加速波特率仅修改仿真副本RX字面参数；31字真实115200验证原文件字节未变。工件frozen_full_model_simulation.json明确simulation_overrides，不以加速仿真称实体结果。

2026-10-10 00:01针对B0的command_full→tag count反馈准备同拍full/empty预测，计数/命令/返回延迟均保留。direct和每客户端slot两种、TAG_BITS2/3/5共6组独立掩码内存队列测试PASS，强制检查每拍flags等于实际count，覆盖全部8客户端/满tag/背压/连续返回/BISTepoch及带在途请求复位；未加入B2。完整模型测试额外启动后再决定是否采用。背景准备模板已通过源哈希/冻结检查，无UserCode/PNR/硬件IO。

2026-10-10 00:03 B2约80分钟路由后正常完成：PNR268BSRAM，video157.907MHz、PLL全部通过、两CDC通过；clk50 feature-cache地址最差-2.226ns/Fmax44.993MHz，DDR UI校准Q→原DDR16使能-1.800ns（hold+0.179ns）。门禁停止programming_started=false，无板卡改写。B3保留所有CNN/缓存算术/官方DDR PHY/固件，对已观测feature-cache地址加严格19ns物理预算（原20ns仍不变）、模型客户端本地寄存同域calibration（1memorycycle初始level延迟，reset立即清）、现有预解码级内波形shift/clamp、背景谓词和tagflags预测。实际wrapper100000组合/异步reset和全部像素/双renderer测试PASS，tagflags六组独立队列PASS；完整模型候选源回归与B3构建同时启动。B3相对B2仅SDC、UserCode脚本、模型边界link、仲裁模块、dashboard5文件变化，原模型/固件/PHY及CNN算术源哈希全部保留。

同拍tagflags完整52239系数NOR/串行/原DDR客户端/仲裁独立内存回归PASS，52239写/读CRC AF01A61B；未作实体 IO。B3采用冻结解析器的全模型测试另跑，新增本地ready真实115200小模型链路单独检查。

B3本地ready完整链路31字/真实115200已通过，原RX文件完全相同，actual frozen link wrapper与请求谓词进入TB，测试源哈希记录。该结果只覆盖初始校准等待，独立PHY单域恢复仍不作扩展承诺。

2026-10-10 B3完整模型回归已把实际本地memory-ready寄存片段接入冻结原解析器/DDR16及共享arbiter/客户端队列：31字真实115200、52239字仅仿真RX加速到3125000，完整52239写/52239读CRC AF01A61B/source1均PASS，含并发扫描/写入与原生背压。B3综合220BSRAM、505SSRAM、43607寄存器、56494LUT；物理占用和时序尚待最终路由。源码绑定证据已加入CNN_FLASH_BOOT_B3_LOCAL_PATH_TESTS.json。另针对B2 kh→feature缓存地址路径准备零延迟3位slot算术，Yosys SAT对实际原/新解码器149位所有输入、FRAME_LIMIT=1/172/512证明全部观测输出相同，包含三条合法最大地址可达性；只做prepare，未修改B3，也未分配UserCode或操作硬件。

2026-10-10 B4已启动，新增实际特征读地址slot位宽约束；与B3仅两份输入不同：UserCode脚本、basic_pitch_pcm_pipeline.sv中的三个有边界保护的slot乘法输入。其余603份冻结输入相同。实际B4源码与已经证明的变换完全相符，SAT149位等价证据绑定到CNN_FLASH_BOOT_B4_FEATURE_SLOT_TESTS.json，零新增周期。B3仍继续独立布线/验收，B4未写板。

2026-10-10 B3路由完成：SYN220、物理268/340。clk50 51.197MHz/setup+0.468/hold+0.160，视频156.577MHz，独立PLL全传播与两组CDC通过；真实DDR UI setup−2.049/hold+0.169，最差u_writer/full→renderer/front_effect CE、11.802ns，正式门禁拒绝且programming_started=false。B4正在布线。针对剩余背压路径新增两拍64-bit像素寄存缓冲，source-ready按精确下一占用注册，done延迟到全部像素送达writer。原frame_writer和renderer未改。三种seed各99984周期、25复位epoch检查通过；完整1920x1080/1036800双像素输出与129601原生DDR地址/RGB565/meta在独立长停顿下逐项相同，frame_pending必须晚于最后DDR数据及meta提交。新增BSRAM为0；统一门禁重新绑定实际冻结源运行这些测试。

2026-10-10 B5已启动综合/路由，新增原writer之前的寄存两拍像素ready；与B4只有HDMI连接、新skid文件、gprj和UserCode脚本不同，其余源保持冻结，实际冻结副本完整1036800像素/129601DDR命令比较PASS。根据B3另两类次要路径，准备TF32bit+6bit分段进位（Yosys SAT对全部38位输入证明相同、20组原/新TF直连/队列/背压实例回归PASS）和完整背景坐标预解码（含sized literal、菱形、箭头，保持已有1启用拍；2137105像素和完整DDR帧比较PASS）。上述修正不增加周期或BSRAM，不放宽时钟门禁。

2026-10-10 B4完成物理路由268BSRAM，clk50 50.790MHz、视频180.112MHz、PLL/CDC/源绑定地址证明通过；DDR UI −2.362/hold+0.168，最差spectrum_left→background颜色，正式拒绝且未烧录。B6已开始构建，较B5只增加TF三个计数器并行进位和完整背景预解码，实际冻结源绑定的SAT/20组TF控制/完整帧提交全部PASS。B5/B6综合分别43678/43685寄存器、56442/56423 LUT、220BSRAM，物理结果待定。

2026-10-10 B5已完成路由268/340BSRAM。clk50 57.536MHz、视频163.513MHz、PLL/CDC/地址SAT/像素缓冲协议/完整帧提交通过；DDR UI−0.995/hold+0.169，较B3的−2.049ns有改善，但最差read_x→odd effect_relative和skidready→analysis列地址等未过。正式门禁仍拒绝、programming_started=false；B6继续路由。

2026-10-10 B7已启动，较B6只有动态背景判定与BIST期望值预生成（另UserCode脚本）不同，其他输入全部冻结。实际冻结原FFT/分析/capture/renderer/writer在ENABLE_ANALYSIS=1/SHARED_EXPORT=1的完整1036800双像素和129601原生DDR命令比较PASS；BIST15组正常、最终错误位、全通道错误、读/写超时各3复位epochs逐周期相同。源绑定证据CNN_FLASH_BOOT_B7_DYNAMIC_BIST_TESTS.json；B6继续独立路由和严格验收。


2026-10-10 01:57：B6布线完整268/340物理BSRAM，clk50 55.134MHz、视频164.640MHz、PLL/CDC通过，真实DDR UI setup −4.714ns/hold+0.169ns，拒绝且无硬件IO。TF write_total→read_total路径经available相减、末帧字数选择和增加计数形成14.692ns链；B8在请求期提前计算post-read count、尾帧直接使用write_total，保留同周期响应，65输入bit SAT全空间等价、36组协议比较通过。B8同时并行预计算当前/下一频谱列再选择，4种WIDTH每种12输入bit SAT及实际分析页完整1036800双像素/129601 DDR命令逐位通过。源码绑定证据见CNN_FLASH_BOOT_B8_TF_SPECTRUM_TESTS.json。

2026-10-10T02:04:33.437369+08:00：B8完整Flash→内部UART→原解析器→DDR16/credit/注册仲裁流水线仿真通过52239写/52239读、CRC AF01A61B/source1，带并发显示写/扫描及原生背压；31字短模型保持真实115200，完整内容仅仿真接收实例3125000。权重和构建源码不变。备用卡片优先选择优化（未用于B8）68bit全输入SAT及2137105随机/完整像素、1036800双像素完整实际分析页/129601DDR命令通过。烧录/回滚11故障分支复测PASS，无硬件IO。

2026-10-10T02:10:54.308237+08:00：B7完成268/340物理BSRAM、clk50 54.700MHz、视频182.441MHz、PLL/CDC/所有绑定协议/SAT/完整分析帧/BIST故障测试通过；DDR UI TF write_total→read_total仍−5.551ns/hold+0.167ns，正式拒绝、无硬件IO。B8正在布线。

2026-10-10T02:14:49.846268+08:00：B9开始完整构建，相对B8只新增TF grouped availability和卡片priority浅层组合选择；实际源码绑定42组TF协议、64bitavailability/65bitnextcount/68bitcard SAT及实际分析页完整帧PASS，额外0周期/0BSRAM。其模型链路11个实际测试源码及模型镜像与B8全模型执行逐哈希一致，已记录组合证明，不标为B9另一次执行。自动验收等待B8完成，任一成功硬件结果后续候选只做本地门禁。

B9 TF协议回归进一步绑定实际构建内的注册tagflags仲裁器60aec35b和client queues，42组全部通过；缓冲模式使用候选构建源码，直接/同周期响应仍使用独立native memory oracle。不是仅TF模块的源码绑定。

共享显示整链路补强：B9实际FFT/XY银行所有权、非均匀front RAM→原snapshot writer→DDR packet→原display cache→完整渲染，3帧全部payload/descriptor、25ms停顿、冷启动无FFT状态PASS，首帧1036800像素对与冻结源相同。备用quiet-shared-analysis变换（尚未用于B8/B9）同样通过，0周期/0BSRAM；共享模式本地column只依赖实际导出地址，直接模式原式不变。

2026-10-10T02:40:56.289940+08:00：BA开始构建，加入SHARED_RENDER local FFT exporter-only地址。实际源码绑定共享display3帧/全payload+descriptor/25ms停顿/冷启动、非均匀front array、完整1036800双像素及129601 DDR命令、4WIDTH地址SAT通过。02:40板上baseline只读健康检查PASS：E/health0/CRC0/每报告48000样本/Push帧+2、0控制字节。BA模型链路11源码及镜像与执行B8逐哈希相同（组合证明）。

2026-10-10T02:54:13.700197+08:00：B8完整路由268/340，clk50 58.176MHz/setup+2.811/hold+.165，视频167.823，所有PLL/CDC/地址SAT/TF36/实际共享整链路/BIST功能通过，前正时钟摘要全部通过；真实DDR UI仍BIST expected_pattern→failed CE−2.936ns/hold+.169，拒绝烧录。TF旧读总量−5.551ns路径消失，剩BIST+TF重启clear/card相对坐标。BB加入已独立18case验证的lane比较pipeline，8MiB正反两轮读明确+5.24288ms启动、0BSRAM，actual-source tests通过。

2026-10-10T02:58:26.528114+08:00：BC开始完整构建（BB+TF byte validity），实际源码绑定100000任意控制周期256bit逐拍比较和48组TF ring/背压/同周期响应PASS，无额外周期/BSRAM。验收等待器现在遍历全部前序，前序实体成功则全部后续候选只做本地门禁；前序尝试烧录而未成功时显式停止要求检查回滚，避免后续默认85假设。

BC最终源码绑定BIST18故障/正常case、65bit读nextcount/64bit可用量SAT已补充通过；模型链路11源码及镜像相同的组合证明附到BC报告。


BD只在已审计的注册DDR仲裁器/TF请求缓冲拓扑内去除新读命令的同拍返回分支，不增加周期或BSRAM。源码绑定50组TF协议及11个原模型/DDR源文件与已执行B8全模型仿真逐文件相同；源文件一致属于组合证明，没有重新声称实体执行。通用同拍接口保留的+1周期响应/数据寄存备选54组协议通过，尚未构建。


BE在BC基础上对完整限定后的读响应和256位数据成对寄存，明确增加每块1个DDR UI周期（10ns），保留直接同拍返回兼容，不增加BSRAM。绑定BE实际源码的54组协议通过，其中18组接入实际TF前级命令缓冲、客户端队列、原生注册仲裁器，并覆盖读命令在途时重启、旧响应丢弃和随后65字节新流的完整字节/环形地址检查。BD同样补充18组完整链路在途重启并通过；修正测试中的过强假设：跨epoch取消后合法旧app_rvalid可以出现于read_pending清零之后，不能直接当作协议错误。没有放松负载字节、地址、tag fault或原生停顿断言。BA～BE按所有前驱验收结果序列化，任一前驱实体验收成功后后续只做离线门禁。


验收等待器补齐构建结束的发布竞态：tool_result.json可能先于workstation_memory.json和flash_bundle.json生成，必须三者完整后才能调用验收；半写入/未完成的前驱报告不授权硬件IO。9组纯主机测试通过，覆盖终端工件缺失/半写入、前驱实体成功/首次尝试/尝试失败、构建失败、重复输出、前驱未结束/半写入。已重新加载BA～BE等待器，没有停止任何构建、验收或programmer进程。


03:45 BA完成：SYN220、物理268BSRAM；所有源码绑定像素、完整共享显示、TF全链路、地址/计数SAT、clk50/video/PLL/CDC均通过；真实DDR UI最差−2.254ns、hold+0.166ns，拒绝且未写板。主要端点是TF emit_index/read_buf CE和未分级的BIST failed CE。03:44锁内被动健康读取modelE/CRC0/health0/精确48000样本每秒/Push帧+2，没有控制命令。

BF保留BE全部606个输入中的RTL/IP/模型逐字节一致，只变显式UserCode与观察到的DDR UI控制端点8ns物理预算。预算比原10ns更严格，未增加false_path、未改时钟或hold要求；本地官方SUG940-2.0.4E §5.4.2定义get_clocks/get_pins max-delay端点语义。该分支是针对CE/同步reset端点的物理实现约束，没有宣称其时序通过。


为BA中u_music_slot.full→queued_data/RESET的控制反馈准备空槽采样可选项；不改full/ready/valid状态机，full=0时采样总线，full=1持有到原仲裁消费。实际原/新槽模块SAT时序归纳证明所有输入序列下ready/valid和318位有效载荷等价。3个tag深度/随机种子独立八客户端记分板共15824条命令、10359次读响应通过，含掩码写、原生背压、连续返回、BIST epoch及顺序检查。此优化尚未用于新构建。发布门禁另增加所有缓冲仲裁器候选实际源码的全八客户端记分板。


04:00前后BB/BC/BD全部完成门禁，DDR UI分别−2.461/−2.336/−1.463ns、hold均正，其他时钟/PLL/CDC及完整源码绑定功能门禁通过；均未烧录。BD最差为pixel_ready→frame_start→卡片front_effect/visible_mask CE，剩TF response_owner→emit_index、及槽位payload同步reset。

C0以BE成对读响应寄存＋BF控制端点物理预算为基础，加入空槽payload采样和帧首first_issue_pending标志；frame_start边沿与原advance&&坐标原点逐拍一致，正常导出/停顿期间保留标志。尺寸显式约束偶数WIDTH2..2048/HEIGHT1..2048，越界例化报错。完整1080p对照1036800双像素/129601 DDR命令通过，C0实际源的完整共享显示3帧/25ms停顿/冷invalidanalysis、54组TF全链路含18组在途重启、全八客户端15824命令10359读响应、槽位时序归纳均通过。改变模型客户端队列后重新执行52239词完整Flash→DDR仿真，结果尚在运行；没有沿用B8源文件等价来代替此执行。门禁明确要求该新执行报告及源hash正确后才可写板。


04:10 C0新执行完整模型仿真通过：52239写＋52239读、CRC AF01A61B/source1、30831665仿真周期，11源hash绑定真实C0（包含变更后的空槽采样队列）。独立native记分板包含并发扫描/写入及DDR背压；31词真实50MHz/115200用例也通过，全模型仅仿真RX副本加速到3125000，原工程115200未改。未据此声称时序闭合或实体执行。


04:45 C0布线完成SYN220/PNR268；最差−1.319ns（新增8ns预算的musicpayload数据到槽位RESET），TFwrite_total+pending_bytes仍有原10ns路径−1.013ns，hold+0.171ns。帧首标志及TF读响应已不再是全局最慢路径；仍有read_pending接收控制/卡片text/清屏FFT/显示写桥负路径，不能据主路径消失宣称闭合。正式验收等待BE/BF前驱完成，确保不会并行硬件IO。状态表已展示该提前结束候选的真实路由指标。


04:52 BE完成SYN220/PNR268，DDR UI−1.615ns、hold+0.169ns，主要卡片relative坐标和帧首CE，正式门禁进行中，未写板。C1保留C0变更，仅将字节加法高位进位改为并行4位组；实际源码38bit加法全空间SAT、65bit读计数SAT、60组TF协议（20组完整前级缓冲＋native链路在途重启）通过。全模型NOR→DDR执行单独启动，原50/100/148.5MHz时钟和发布门禁不变。


05:03 C1新执行完整模型也通过：52239写/52239读/AF01A61B/source1，11源hash绑定C1实际模块；31词真实115200先例同时通过，完整仅仿真RX加速。C1综合完成进入布局，尚无路由时序，不声称可写板。
