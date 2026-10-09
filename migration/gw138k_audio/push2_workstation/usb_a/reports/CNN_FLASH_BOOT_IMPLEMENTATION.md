# CNN Flash→DDR 实施记录

截至2026-10-09 23:12，**完整工作站AD已通过实际Flash启动诊断**：连续三次SRAM擦除→Flash重载，精确UserCodeAD/状态26020，模型均E/source1，未用SRAM下载或PC模型上传，实时演奏检查PASS。AF/B0/B1发布时序未通过，均未烧录；B1的全部PLL全传播已通过（最差7.964ns），B2等价动画/TMDS修正正在布线。板上配置和LATEST均保留已核验的full85，正式发布及物理断电验收尚未完成。

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
