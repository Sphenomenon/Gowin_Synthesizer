# 完整工作站黑屏：官方 DDR 对照与物理约束修复

日期：2026-10-26，时间均为 UTC+08:00。接续 [DDR 校准排查](WORKSTATION_DDR_CALIBRATION_20261026.md)。用户授权“试试吧”，本轮只使用 SRAM 和 JTAG，不操作 Flash、OTP 或断电重启，不改冻结基线或 vendor。用户此前在官方 138K 底板正常显示是历史对照，不应把当前黑屏直接归为硬件故障。

## 已确认的差异

1. 独立官方工程 B1 在同一块板上完成 DDR 校准，三次抓取均无读数据比较错误，后两次实际观察到读数据有效脉冲。
2. 工作站隔离工程 E6 的网表、复位、PLL/IP、BIST 和 SDC 均不改，仅补官方的三项硬资源定位、增量 P&R 得到 B2；B2 连续三次观测均为 `0xDF`：校准完成、UI 复位释放、8 MiB BIST 完成且失败标志为零。
3. E6 的 400 MHz 内存时钟使用额外 PRIMARY 路径及 `BANK7_HCLK1 BANK6_HCLK0`；B2 与官方 B1 一样，使用 `BANK6_HCLK0 BANK7_HCLK0`，不再出现该内存时钟的额外 PRIMARY 路径。

因此，已有同板正向对照，问题收敛到遗漏官方硬资源布局约束后的物理实现，不能继续将“可能 DDR 硬件有问题”当作已证实根因。三项约束中各自的必要性尚未逐个剥离；B2 通过仍不等于完整工作站声画验收。

## B1：原始官方逻辑对照

来源为 `sipeed/TangMega-138K-example` 固定提交 `06e7d8b118d345915ab6f257b7c22226f81575cd`。通过 GitHub API 获取目录树及 blob；19 个文件逐个核对 Git blob SHA1 和 SHA256，实际综合输入为官方工程列出的 11 份 Verilog。官方 top、按键去抖、PLL/PLL_INIT、加密 DDR IP、读写测试和 UART 源码保持原始字节；没有引入工作站的复位 guard、平台、仲裁或 BIST。

输出根目录为 `out/official_ddr_ab_20261026_01/`，不是生产输入。官方原始工程和清单在 `official/`、`repository_tree.json`、`download_manifest.json`，下载清单 SHA256 为 `57188783d38738bd19ad30c94cffc00a5bc6eab390c1d17febb8913f4dbdb431`。

单独适配保存在 B1，不改原始约束：

- 实际器件为 `GW5AST-LV138PG484AC2/I1`、C 版，官方工程声明 C1/I0。
- 官方原 SDC 将输入声明为 100 MHz，并将三个时钟设为互斥；本次单独 SDC 使用实际 50 MHz 输入、相关的 400 MHz DDR 与 100 MHz UI，保留当前已审计的 PHY 例外，不沿用错误频率或互斥声明。
- 官方 CST 的 DDR 球位、电气属性及 PLL/DLL/CLKDIV 位置保留；追加既有 E6 的两个 hold 布局边界。UART 为 U15/V14，按键 F4，LED V13，参考时钟 V22。
- 追加 32 位 GAO，50 MHz 采样；原始状态、错误比较字及二进制读计数为跨域原始观察，不声称是相干快照或严格全容量压力测试。

| 项目 | B1 |
|---|---|
| UserCode / GAO | `C11026B1` / `26B1` |
| 输入清单 SHA256 | `dade6e3e384eda846c48ee3b0bbef038fb92d8e30ccec66689302dbae53cd970` |
| 位流 SHA256 | `697d38687e78e95f8141f7e42f26debcb49410049b8a8d29b1ba9d9fd49b3b50` |
| setup / hold / recovery / removal | `+2.008 / +0.005 / +2.878 / +0.344 ns` |
| SRAM 部署结果 SHA256 | `96adf5102d187cd66d140b8502b84b483bf8e268385d86ebfc5793ffbbe25427` |

`c11026b1/jtag_capture_20261026_01..03/` 每次独立校验前后 ID、WINUSB OPEN、全部 READ_RAM 和 1024 样本布局。三次均为 PLL 锁定、`init_calib_complete=1`，全部错误字位为零；第 2、3 次各捕获 141 个读有效样本。计数低八位发生变化，只作为读活动证据，不解释为完整容量测试通过。

## B2：只补位置，复用 E6 网表

`c11026b2/` 逐字复用 E6 `diagnostic.vg` 和 SDC，复位、DDR 平台、PLL/IP、8 MiB BIST 及 20 位观测逻辑全部不改，不重综合。复用 E6 `.p/.pr` 增量 P&R，仅追加：

```text
INS_LOC "u_memory/u_pll/u_pll_0/PLL_inst" PLL_L[0];
INS_LOC "u_memory/u_ddr3/gw3_top/u_ddr_phy_top/u_dll" DDRDLLM_BL;
INS_LOC "u_memory/u_ddr3/gw3_top/u_ddr_phy_top/fclkdiv" LEFTSIDE[4];
```

原 hold 布局边界和所有时钟/例外不变。完整重跑既有隔离核验器，源/输入身份、四类 STA、PLL400/UI100 拓扑、状态及 Gray CDC、GAO 连接均通过。setup/hold/recovery/removal 为 `+0.631/+0.130/+2.536/+0.253 ns`。

| 项目 | B2 |
|---|---|
| UserCode / GAO | `C11026B2` / `26B2` |
| 输入清单 SHA256 | `d0b5dc0d324303d3bb1114081cc9db1155dd187341e04d3e135f647a40f39bd5` |
| 位流 SHA256 | `b1160972329e51428c14e16cb46d641359a35e8d76852506b07802591f55480a` |
| 核验结果 SHA256 | `aea06d0d8ea36bfd2cef83e4ff6593c5b9e8dfa1f60e95ca256b0d01fc5ad0eb` |
| SRAM 部署结果 SHA256 | `bcf0d47e01677979af7593168820451acebf8b1c5186e41868ac0581dcbeae7e` |

09:48:51～09:48:58 从 B1 只下载 SRAM 并独立读回 B2，随后三次抓取全部 1024 样本均为 `0xDF`，Gray 计数持续活动。不是通过强制校准、跳过 BIST 或删除功能获得通过。

随后进行反向回切，排除只在官方例程之后偶然启动成功：精确原 E6 位流再次下载，两个 1024 点捕获全部为 `0x03`，PLL/UI 时钟活动但仍未校准；重新下载精确 B2，两次再次全部为 `0xDF`。反向证据为 `e6_repeat_01/`、B2 `sram_deployment_02/` 及 `jtag_capture_20261026_04..05/`。本轮 B2 共五次捕获、两个 SRAM 启动均通过。

## 进入原生构建与完整工作站验证

三项位置约束进入版本化 `boards/custom_138k/ddr.cst`，由原生准备入口合并到唯一有效 CST，并纳入 source/staged 哈希及综合审计。新准备身份为 `custom138k-native-integration-20261026-a24`，保留此前所有音频、USB、BLE、模型 Flash 和时钟检查，不改 accepted full83、pinned timing85 或冻结基线。

针对性回归共 37 项通过：采集/解码七项、隔离 DDR 契约两项、accepted 输入边界十项、原生准备/隔离三项、物理候选准备十五项。日志、命令和脚本哈希在 `regressions_01/results.json`；相关 Python 编译和所改 tracked 工具/测试的 whitespace 检查通过。未重新综合完整工作站来跑这些回归。

完整工作站 B3 独立候选保存在 `c11026b3/`：消费原 a23 完整 VG 和 SDC，仅补三项位置，保留 E4 的 16 位 GAO 并复用 E4 数据库增量 P&R。它不是 a24 已重新综合的网表，也不能冒充原 `C1102515`；所有业务仍在，GAO 是单独调试开销。

`constraint_delta_verification.json` 重新核对原物理清单，证明 B2/B3 的业务 VG、SDC 均与各自父候选逐字相同，CST 的唯一增量正是版本化三行位置；`ddr.cst` SHA256 为 `21e89c37258ecff827aaa16d071bc7ba70124332d01897256623d76becc2fbdc`。B3 最初继承的 E1/E3/E4 准备元数据有旧 GAO/数据库描述，保存在 `initial_preparation_inputs.json`、`initial_physical_inputs.json`；部署前另行规范当前清单并记录原清单哈希及修订原因，没有改任何实现输入或历史父清单。

## B3：完整工作站实测与当前部署

09:52:26～10:35:50 完成增量 P&R，耗时 2604.375 秒，没有重综合完整工作站。保留原 SDC、hold 布局与业务功能；新位流身份独立，不转移旧位流的用户接受范围。

| 项目 | B3 |
|---|---|
| UserCode / GAO | `C11026B3` / `26B3` |
| 输入清单 SHA256 | `8ed43c158332ea4cbe3aebd703bffc0cc762ba5eb656cbd60421ea88077aeac3` |
| 位流 SHA256 | `a901738a4e07eb777cbc32eb571179e93ebae86e8488e573d4b65696e100011c` |
| 核验结果 SHA256 | `5d083c29b2d1b67021b5359a3c4f8e27f48fac9486f1ca21943db42632629710` |
| SRAM 部署结果 SHA256 | `d12491f944967893a5551efda56f4c451adf8d63a07af932e948043bd07385bb` |
| setup / hold / recovery / removal | `−0.394 / +0.085 / +2.942 / +0.250 ns` |
| BSRAM | 业务 321 + GAO 1 = 322/340；GAO 不展开在业务 `.vo` 中，由资源报告单列 |

CDC、PLL/初始化、原生路由三项通过。严格时序检查仍失败，保留 setup/Fmax 违例及 GAO 新增 TCK 造成的时钟清单差异；没有放宽时钟、删除例外检查或宣称 `timing_closed`。本次仅使用用户授权的 SRAM 诊断，不作为 Flash 发布。

**10:40:16～10:40:24 仅烧 SRAM，从 B2 切换至完整工作站 B3。** 下载前后独立读取设备 ID `0x0001081B`，下载后 UserCode `0xC11026B3`、Status `0x00022230`；没有 SRAM 内容逐位读回，没有 Flash 操作或冷启动。随后三次抓取均核对前后身份、WINUSB OPEN、全部 READ_RAM 和 1024 样本，结果一致：

- `memory_flags=0xEB`：DDR/视频 PLL 锁定、DDR 校准完成、BIST 完成且未失败、前台帧有效、取数/仲裁/共享加载故障为零。
- `video_flags=0x2E`：像素和显示取数复位均已释放，串行器不在复位；与原 E4 的 `0xC0/0x26` 相比，原黑屏的 DDR/显示就绪阻塞已解除。
- 渲染帧计数最低位在不同抓取间由 0 变为 1，确认有渲染进展；仅一位投影，不能给出完整帧率或断言无丢帧。
- **欠载历史标志为 1。** 当前探针没有欠载完整计数，不能区分启动瞬态和持续欠载，不能声称显示性能已验收。
- HPD 采样为 0，不门控本链路；不据此认定用户没有插线或重新归因线路故障。

三份 summary SHA256 依次为 `faee4850bec01e5e41ec1c4fbeb166d4effcac50c46afbe4efbad1d6dfefcfeb`、`dab7cdb500ad7d841e467c459f44e2ed9bef43879dd6b9d166c940e488fc831f`、`1f0f5bbee9a7e9e87169a18f68bdcf6943f2ae2d670a7063122287e671a85829`。完整汇总为根目录 `final_status.json`，SHA256 `022790c2cfe5a31a7980c7b9a1a988d0bcd6be8be5e7aa5d4a0ac6b39e3f246a`。

当前保留完整工作站诊断版 B3 在 SRAM 供用户确认实屏；不是隔离 DDR 工程。尚未取得用户的实际画面确认，也未重做整机音频、Push/25K、BLE 或冷启动验收，`hardware_acceptance=false`、`release_ready=false`。

本轮暂不把实验目录设为默认生产来源。退出条件为完整工作站物理核验、DDR/BIST/显示抓取及用户实屏确认后，将三项版本化约束随现有原生配置交付；实验脚本和捕获保留为 dated 证据，不新增编号生产构建器。

回退为原完整工作站 `C1102515`：`out/workstation_physical_20261025_c1102515/impl/pnr/custom_138k_integration.fs`，SHA256 `c5006e8f511fed84ced3cd284dabcb8a47359fadd4f64b4f34fdafc6ec880f68`。如 B3 未通过必要诊断检查则只恢复该 SRAM 镜像；不操作 Flash，不将恢复称为黑屏修复。

## 随后的用户实屏反馈

2026-10-26，用户确认 B3“有画面了，虽然在快速闪烁，但确实有画面了”。本节追加新的实际画面证据，不改写前述抓取时“尚未取得用户确认”的历史快照。B3 已实现出图，但仍未通过稳定显示验收；后续转入 [闪烁排查](WORKSTATION_HDMI_FLICKER_20261026.md)，优先测量持续欠载与帧进展。该后续诊断首选回退改为保留已出图的 B3，不主动恢复旧黑屏版，也不操作 Flash。
