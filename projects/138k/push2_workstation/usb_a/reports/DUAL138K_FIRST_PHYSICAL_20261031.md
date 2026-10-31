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

W v3已全量综合，但HCI函数隐式依赖缺陷使真实会话寄存器被异常折叠，不能部署。维护源已改为显式参数，旧v3保留作资源测量。W SDC v2只对实际generate层级重绑定／已退出分支退休；每个退休selector须在VG中零匹配，重绑定后的selector须命中，不能忽略缺失端点。

W v4准备因Classic verifier仍要求旧层级SDC原文而失败；未修改该输出继续构建。修复仅使明确W角色逐行验证适配后SDC；默认Classic原规则保持。21项角色／审计测试通过，删行、重复、10→100 ns松绑、PRESET→CLEAR和伪造元数据均有负控。

W v5 `custom138k-workstation-w-demo-v1-13cd785895ee9996` 已成功准备并启动全量综合，包含显式HCI依赖、SDC v2、reverb和显示流水；本记录不预记其综合／P&R结果。W实际长期录音容量、手机无线和声画共存仍未完成。
