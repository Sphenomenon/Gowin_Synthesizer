# M/W 首轮物理测量与局部修复

日期：2026-10-31。工作分支 `codex/dual-138k-workstation`，独立工作树；未修改单板主工作区或其未提交文件。M/W 完整独立演示和实板验收仍未通过。

## M v5：全布通，但时序失败

候选 `custom138k-workstation-m-demo-v1-47d2966d7ee9ccb8`，物理 UserCode `D2103101`。目录 `/Users/sphenicidition/.cache/gw138k-dual-20261031/m-demo-base-v5-physical-v1`。Gowin V1.9.12 完成 P&R、生成位流，进程退出0；这不构成时序或部署通过。

| 口径 | 实测 |
|---|---:|
| 综合 LUT／ALU／FF | 51,765／12,621／45,983 |
| 综合 BSRAM equivalent／SSRAM | 195／141 |
| 物理 Logic／FF | 65,597／45,983 |
| 物理 CLS | 49,644／69,120 |
| 物理 BSRAM | 235／340 |
| 物理 DSP | 120／298 |
| setup／hold 违例端点 | 8,219／71 |
| 最差 setup／hold slack | −7.209／−1.702 ns |
| audio 76.8 MHz 的实际 Fmax | 61.861 MHz |
| DDR UI 100 MHz 的实际 Fmax | 76.230 MHz |

最差setup是观测丢帧级别到显示健康首级同步器；这条异步级别路径需要精确CDC闭包，不能用其slack代替同步音频路径。同步路径另有reverb −3.144 ns、pitch／oscillator约−3.135 ns、显示导出上下文到256-bit `pack_data` 使能约−3.118 ns。最差hold位于加密DDR内部初始化边界，仍需物理修复。原始测量、13项输入／输出hash、位流头UserCode及准备输入复核见[物理证据](dual138k_m_demo_v5_physical_20261031.json)。位流SHA256为 `61b65e88f611cf766f775cb5599fc9d159f1fc5b766cf07711d60ade70deb63d`。

初次启动因缺Gowin动态库环境在加载项目前退出134；保留失败日志，设置其随附库路径后再次运行完整成功。没有修改时钟或放宽false path。没有SRAM下载或Flash写入，本阶段回滚为继续保持已有板上镜像。

## 显示导出局部流水

实际构建消费的维护源 `rtl/display_data/display_data_writer.v` 将宽上下文比较注册后再控制打包寄存器。最后一个有效载荷WRITE之后增加一拍 `VERIFY_CONTEXT`，在元数据写入前检查最后WRITE边界的取消；已经挂起的DDR请求仍原样排空，失败包不发布。默认无上下文minor0分支保持原来的逐周期／逐字节行为。完整波形／FFT／XY和参数快照继续使用原路径，不改变音频采样调度。

三组离线闭环通过，证据清单见[显示验证](dual138k_display_context_pipeline_20261031.json)：

- metadata：615,641周期minor0精确比较，1,098个原有写拍；minor1有14次全缓存检查、3次取消，其中新增最后CAPTURE／已接受WRITE边界各一次。移除最终检查拍的负控在指定最后WRITE断言失败。
- 真实分析：3次发布、1,536波形样本、196,608个XY像素、1,536频谱列，48k／44.1k实际频轴绑定通过。
- 完整显示运行：7次发布、150,810次原子tuple检查、60次CDC丢帧、尾部／读取消和丢帧完成竞争通过；加载边界12场景、47检查、4负控通过。HDMI装配elaboration通过。

默认输入边界回归 `sim/test_current_workstation_sources.py` 17项通过。显示runtime runner首次用M候选时因已退出的录音支持源码不在stage而停止，未改候选补文件；改用保留完整原支持源的固定Classic准备工程完成离线运行。所有参考来源均记录hash，未转授原Classic的硬件或物理验收。

Reverb使用既有RAM等待拍拆分运算，其逐周期等价和双率验证见[reverb修复](DUAL138K_REVERB_PIPELINE_20261031.md)。以上仅说明源码和离线验证通过；新物理资源、routed时序、CDC闭包及声画实板结果必须在新身份下重测，不预记收益。

## W 的约束与候选门禁

W v3已全量综合，之后定向仿真确认HCI函数隐式依赖缺陷，维护源已改为显式参数，旧v3保留作资源测量。v3／新v5网表均有两项真实会话存储selector未命中，正在区分实际存储映射与逻辑裁剪原因；此前把未命中直接归因于函数缺陷的推断尚无网表证据，不能当作已确认因果，也不能退休该路径或部署。W SDC v2对已确认generate层级重绑定／已退出分支退休；每个退休selector须在VG中零匹配，重绑定后的selector须命中。

W v4准备因Classic verifier仍要求旧层级SDC原文而失败；未修改该输出继续构建。修复仅使明确W角色逐行验证适配后SDC；默认Classic原规则保持。21项角色／审计测试通过，删行、重复、10→100 ns松绑、PRESET→CLEAR和伪造元数据均有负控。

W v5 `custom138k-workstation-w-demo-v1-13cd785895ee9996` 已成功准备并完成全量综合，包含显式HCI依赖、SDC v2、reverb和显示流水；实际会话存储端点闭包仍待核验，尚未P&R。W实际长期录音容量、手机无线和声画共存仍未完成。

## 继续复用主线已提交修复

只读核对主工作区后，合并其 `a4e2804143b266fb06eb46aa82e3a0a51a794ac1` 与 `44f804f80ab2aadc73f322a4ae159ccb093c74f8` 两个已提交成果：原生 held-word协议窄约束、显示本地域复位释放、录音epoch资格同步、BLE raw宽字段空槽预装、TF长度有效settle及被动效果quiet。未纳入其未提交reverb、provenance、task或报告；没有中断主线程工具。非DEMO profile保留导入提交的hash，没有为本分支共享源差异静默刷新旧身份。

合并后复验：raw store两配置与行为负控、authority十相位／17场景和六负控、TF四配置各23场景及默认逐周期对照通过。显示runtime同时覆盖新增停钟复位释放，记录 `display-merged-runtime-v1/verification.json`。生产启动实际I2S组合回归通过211个有效帧／127个非零帧、两次配置确认和一次中帧切换，最大render1168／slot1197拍；该定向短场景不代替32声部压力或长期实板检查。运行文件位于 `/Users/sphenicidition/.cache/gw138k-dual-20261031/` 对应的 `recording-merged-raw-v1`、`recording-merged-authority-v1`、`tf-merged-runtime-v1`、`audio-merged-runtime-v3`。音频fixture显式连接新增只读 `effect_state_o`，没有忽略缺端口warning。

原始音频测试首次选择旧Classic准备工程时缺少新增D参数接口，重新选择固定M v5支持源完成；默认来源17项回归另行直接运行通过。由模块方式启动该来源测试曾因其既有本地fixture导入路径失败，随后按文档直接执行原脚本通过，未改测试放行。上述失败启动保留日志，没有修改冻结候选补文件或改变参考输入。

## M v7：同RTL的完整综合与新物理候选

M v6 `custom138k-workstation-m-demo-v1-0fb50b6129cca888` 在局部混响／显示／音高及已提交主线修复后完成全量综合。综合LUT51,820、ALU12,904、FF46,859、BSRAM equivalent195、SSRAM141，DSP primitive为MULTALU27X18=34、MULT12X12=4、MULT27X36=42。与M v5的差额包含本轮全部修改，不能记作某一个局部修复的资源收益。

后续routed VO证明，98位已保持的物理观测数据被Gowin从3片36-bit SDPX9B拆为6片18-bit，新增片带`gowin_add`名称。维护约束源增加一个通配符匹配该拆分，目的端仍逐位列出同样的98个D。M v7 `custom138k-workstation-m-demo-v1-0067ea90a6354485`另行prepare，全部582个staged输入集合及260个enabled路径相同；唯一变化是SDC这两行source selector，581个非SDC输入逐项hash／字节一致。因此透明复用M v6已经完成的全部综合输出，未再宣称第二次综合，也未修改M v6原输入或身份。[复用证据](dual138k_m_demo_v7_synthesis_reuse_20261031.json)记录两候选及每个综合输出hash，M v7仍需独立新P&R。

M v7严格综合网表门禁已通过，包括完整乐器／效果／HDMI／TF保留、蓝牙及录音退出、32声部真存储、时钟与每个可见SDC selector。综合网表SHA256 `4e77d5b5ae1fe7e591ad9824dfa4c7f8c5962fabf3b5ccf833ad75ae9a980cd6`。物理目录 `/Users/sphenicidition/.cache/gw138k-dual-20261031/m-demo-base-v7-physical-v1`，新UserCode `D2103103`；真实P&R已经启动，时序／资源结果尚待取得，未部署SRAM。

手机实际可用性由用户确认当前只有模拟器，真实安卓无线验收推迟到实机可用时。模拟器结果不替代手机A2DP、W D处理或BLE录音下载共存。

M v7实际P&R已全部布通并生成位流，退出0，所有准备输入hash在完成后保持。物理Logic65,950、FF46,859、CLS49,996／69,120、BSRAM235／340、DSP120／298。setup违例4,069、hold1；最差setup−2.074 ns，音频Fmax67.089 MHz仍低于76.8 MHz。setup端点较M v5减少4,150个，hold减少70个，仍未闭合。DDR报告Fmax187.196 MHz不能覆盖其850个setup违例，实际同步epoch→framebuffer控制路径仍−1.894 ns；音频DMA故障→USB输入settle同步路径为−1.885 ns。

唯一hold为DDR初始化→wloadn；slack−3.647 ns含已导入的精确`set_min_delay3.500`要求，数据延迟0.386 ns／skew−0.485 ns，仍是失败门禁，不能与旧1.800 ns约束下数值直接当作物理退化量。PR1014仍警告clk50和12.288MHz参考可能使用普通布线。完整测量／输入与输出hash见[M v7物理证据](dual138k_m_demo_v7_physical_20261031.json)，未下载SRAM或写Flash。

新M v7实际VG与VO、实际安装physical.sdc的4个原生邮箱／98位注册RAM／丢帧健康局部结构闭包通过，详见[原生CDC验证](DUAL138K_NATIVE_CDC_20261031.md)。这是明确局部范围，完整CDC、PLL和routed时序仍未通过。后续继续按实际剩余路径修复，不以新增例外掩盖同步逻辑。
