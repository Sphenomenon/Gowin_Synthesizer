# F03：固定父网表的 DDR capture region 实现与失败门禁

日期：2026-10-30（Asia/Shanghai）。独立物理候选 `custom138k-native-physical-C11030F3` 完成真实 P&R，产生 UserCode `0xC11030F3` 位流。请求的 `wloadn_3_s0` 捕获寄存器落在 `R40C70[0][A]`，该精确路径在原 0.800 ns min-delay 下的 hold slack 为 **+0.814 ns**。**整机 routed STA 仍失败：全局 setup −2.475 ns，不能部署。** 本轮没有操作板卡、下载 SRAM 或写 Flash。

完整机器记录：[f03_physical.json](workstation_task_20261030/f03_physical.json)。其中保留原 prepare manifest、38 个相对路径证据的实际哈希、全部 926 条详细负路径、原始四项门禁及独立 maintained PLL 复核结果。原 [F03 prepare 记录](WORKSTATION_F03_CAPTURE_REGION_PREPARE_20261030.md) 和 [F02 物理失败记录](WORKSTATION_F02_PHYSICAL_20261030.md) 继续保留。

## 输入身份与唯一物理变化

来源仍为固定 commit `3d4b3175d0f20d0b787b61b43e4543739b26bca1`、profile revision 2、authoritative profile identity `custom138k-workstation-v1-f5b723250388add5`。父物理候选为 `custom138k-native-physical-C11030F2`，原综合目录为 `/Users/sphenicidition/.cache/gw138k-task-20261030/clean-rev2-profile-candidate`。底层 `custom138k-native-integration-20261027-a26` 只表示继承的装配来源，不充当本轮部署身份。

输出目录为 `/Users/sphenicidition/.cache/gw138k-task-20261030/f03-capture-region-C11030F3`。本轮直接复用 F02 的 hash-locked VG 和原 SDC，没有新综合，没有消费当前工作树后续 ADSR、USB lights 或其他运行时修复。唯一 CST 增量及新 UserCode 为：

```tcl
INS_LOC "u_memory/u_ddr3/gw3_top/u_ddr_phy_top/wloadn_3_s0" R[40:50]C[70:90];
```

DDR PLL `PLL_L[0]`、DLL `DDRDLLM_BL`、UI divider `LEFTSIDE[4]` 三个硬位置保持；已有 ULPI `LVCMOS33` 名义适配保持。这仍是 U4/U5 bypass 的离线实验假设，尚无实际 USB3300/TXS 电气和完整外部 IO timing 验收。

| 输入 | SHA256 |
|---|---|
| `physical_inputs.json` | `39f97ac143e5b02ce1e85e47a91896c4c2bd4c619758ad7b661564126d947554` |
| 继承 VG | `27b30ac791323f05dc68cd5d9ea6ccaaf14d6a122c5fe2b978cb4714b7fdcf18` |
| F03 CST | `4931317d74a07e7826448c2eea134465fdf813b44504c4e3bdaf6c392f214fef` |
| 未变 SDC | `bfcf675d98f07dbcb51eaedfa554b59e14b3f9efca0c2b66822e774ef5198354` |
| `run.tcl` | `45714dcfaeee9ca6966b2ea9a146aea91101dee2edeaf5b43f1c1f9f5aa00525` |

原 `physical_inputs.json` 是 prepare 时的不可变快照，原 `preparer_sha256=548fed967831eb01a236d6bd02ff9f7b06ab028f6f84af999d7268dd42a6549b` 不替换为随后修改的 builder。其 `EDA_started=false` 等字段保留原阶段含义；实际已完成的 P&R 与当前失败状态分别记在机器记录的 `process`、`status`，不回写原 manifest。

## 实际实现与产物

Gowin V1.9.12，器件 `GW5AST-LV138PG484AC2/I1` version C；place=2、route=0、replicate=0，timing-driven 与 automatic hold repair 开启。时钟、原 timing exceptions 和全部功能保留。06:10:50.557 至 06:23:16.678 的 wrapper 持有 `/private/tmp/gw138k-build.lock`；工具 rc=0，报告 CPU 678 秒、elapsed 709 秒、峰值 2910 MB。运行前后 physical 输入哈希一致。

| 产物 | SHA256 |
|---|---|
| P&R log | `0a2f3fb29ed50523921a10b0452158527d4280f98448b83cc9fe39447c84a183` |
| 正式资源报告 | `4638c38d94e3e80afb3a138d6bd39442cb7f36790efe706201ed44e25a77f8dc` |
| routed timing HTML | `61225a3a1fcc11fa6f400e9c635b4a97685431f55fbd091d5098677e8bedb7ee` |
| VO | `f3249001d5c5fca0d54dc4c8bde6d2903921a05a351cec2b37cf10b940e02b5b` |
| SDF | `544efa9bd493deb5ab8e312580451b502a3e7b4584a74d65c4dfae3c0a291884` |
| `.fs` | `4897fbaf58ce7287297f0bae99d1b2f340887dd2f524d92536379a5ea619349c` |
| `.bin` | `63fad42fb69833c33cf6dd521a724c0598f9d19554a2ada8e0c394fa822b7a37` |

已直接核对 `.fs` 的 `//UserCode: 0xc11030f3` 和 `device.cfg` 的 `set user_code = 0xC11030F3`。这是本地产物核对，没有 JTAG 身份读回。生成数据库、位流、VO/SDF 保留在外部缓存目录，不加入源码提交。P&R log 只有一条 PR1014：`clk_50m_d` 使用 generic routing clock resource，可能增加 delay/skew；没有 ERROR/FATAL。

| 资源 | F03 实际 P&R |
|---|---:|
| Logic | 92,251 / 138,240 |
| LUT / ALU / SSRAM | 73,562 / 16,175 / 419 |
| Register | 55,571 |
| CLS | 60,579 / 69,120 |
| BSRAM | **309 / 340，余 31** |
| SP / SDPB / SDPX9B / pROM / pROMX9 | 3 / 219 / 35 / 45 / 7 |
| DSP | 156.5 / 298 |
| MULT12X12 / MULT27X36 / MULTALU27X18 | 41 / 45 / 46 |
| IO Port / IOLOGIC | 142 / 297、105 / 285 |
| AE350_SOC | 1 / 1 |

综合等效 BSRAM 272 与物理 BSRAM 309 分别记录；本轮没有添加 GAO。不能把等效数量当成物理剩余容量。

## capture 位置与精确 hold 路径

独立只读复核同时检查 routed VO 的 launch/capture DFFCE、直接 Q→D、launch 的 DDR UI CLKDIV4、capture 的 direct clk50，原 SDC 精确存在一次，以及 `.tr` 中自定义 min-delay 的实际完整 hold 报告。没有用“未出现负路径”推断该端点成功。

| 项目 | F03 实测 |
|---|---|
| launch | `ddr_init_internal_r_s0`，`R102C141[0][A]` |
| capture | `wloadn_3_s0`，`R40C70[0][A]`，位于请求 region 内 |
| 原 min-delay / hold relationship | 0.800 ns / 0.800 ns |
| arrival / required | 3.458 ns / 2.644 ns |
| 精确 hold slack | **+0.814 ns**（F02 为 −0.910 ns） |
| clock skew | +0.428 ns |
| 最小角 CQ / data route | 0.144 ns / 1.880 ns |
| SDF 最大角 CQ+route | 3.378 ns；单列，不代替 hold STA |

约束仍为 `ddr_init_internal_r_s0/Q → wloadn_3_s0/D` 的 `set_min_delay 0.800`。全局最差 hold +0.137 ns 属于整份报告，不能替代上述精确端点的 +0.814 ns。该局部修复没有闭合 DQS HOLD setup 或其他域。

## 冻结门禁与 maintained PLL 分别记录

| 门禁 | 结果 | 证据 |
|---|---|---|
| 冻结 routed STA | FAIL，rc=1 | setup −2.475 ns；五个域有负端点；926 条详细负路径 |
| 冻结 PLL/startup | FAIL，rc=1 | 仍假定历史名 `…/pll_stop_s0`，startup 覆盖未完成 |
| common CDC | PASS，rc=0 | 18 gray buses、5 levels，errors=[] |
| native routes | PASS，rc=0 | model readiness flight 1.766 ns ≤ 2 ns；errors=[] |
| maintained PLL/startup | PASS，rc=0 | 完整重跑 DDR source proofs、结构解析及三项真实负例 |
| 精确 DDR capture hold | PASS | 原约束、实际位置、完整 hold path 和 +0.814 ns |

冻结 `pll-audit.json` 未覆盖，SHA256 `24aadd04df0ebbfed03bfa0ac3f89c3dcb3d836491a4b23af46b99a015a35fa2`；新结果写入独立 `maintained-pll-audit-reviewed.json`，SHA256 `dd55bd58e457072815409d8c9585027a0a7c79832c0b49e897d0470d189c0ff6`。新版检查器按实际驱动、类型、INIT 极性、连接和 SDC coverage 解析生成单元，不靠替换报错名字。它仍保留 40 ns reset 预算、80 ns stopped-clock 窗口和 shared PLL 10 ns 原预算。

maintained 检查器直接重跑 DDR startup/recalibration/external-reset/lock-loss 四场景、108 个 reference cells，以及 620 ns STEP freeze、512 个 HOLD truth-table cases、32 条 WSTEP pipelines 和两套官方 PCLK 模型。四条 TMDS serializer reset、一个 pixel divider 和 109 个 DDR reset/clear 端点合计 114 个，都匹配对应 SDC 例外，没有遗漏端点；DDR DLL STEP 八个 capture 的最大 arc+route+setup 为 8.079 ns，低于 40 ns。

TMDS clock lane reset settle+recovery 为 7.923 ns，pixel divider 为 6.633 ns，DDR reset 最差为 7.286 ns。video PLL 11 个动态端点最大 8.581 ns；audio/USB/CPU/LCD shared PLL 控制最大分别为 5.950/6.679/6.838/6.121 ns，均低于原 10 ns。

三个实际 VO 破坏负例均触发对应拒绝：clock serializer D0 破坏 `10'b0000011111`；ELVDS 输入绕过 serializer；USB PLL RESET 从 GND 改为 VCC。另有 6 个输入绑定回归，验证初始输入漂移、manifest 改写、物理输入改写、routed 证据改写、路径逃逸和正常输入；serializer 结构回归 4 项通过。审计开始与结束都绑定 manifest、全部声明输入、VO/SDF、reference、maintained helpers 和父 checker/vendor 依赖哈希；不使用运行时文本 overlay。这个子门禁通过不抵消 STA 失败。

## 未闭合的 setup

| clock | 要求 MHz | F03 MHz | setup 负端点 / TNS ns |
|---|---:|---:|---:|
| clk50 | 50 | 49.935 | 1 / −0.026 |
| ULPI | 60 | 79.851 | 0 / 0 |
| DAC ref | 12.288 | 83.700 | 0 / 0 |
| audio | 76.8 | 70.202 | 742 / −322.661 |
| LCD pixel | 31.5 | 40.840 | 0 / 0 |
| USB | 48 | 46.159 | 11 / −9.138 |
| DDR memory | 400 | 2338.897 | 0 / 0 |
| DDR UI | 100 | 185.942 | 144 / −79.200 |
| HDMI pixel | 148.5 | 130.246 | 24 / −22.470 |
| CPU RAM | 50 | 78.220 | 0 / 0 |
| CPU core | 100 | 1064.113 | 0 / 0 |

全局 recovery +3.301 ns、removal +0.278 ns；pulse-width 最小 +0.583 ns，无 pulse-width 违反。Fmax 不能替代跨钟和特殊 pin 的完整检查：最差 `DDR read_rclksel_conf_2/Q → lane2 DQS HOLD` 为 setup −2.475 ns，data 8.939 ns、skew 3.084 ns；audio 的 event queue head→engine expression gain CE 为 −1.224 ns；HDMI vertical counter→scanout under-count CE 为 −0.944 ns；USB guide read-index→lights value CE 为 −0.831 ns；clk50 Basic Pitch frame→Viterbi peak-note CE 为 −0.026 ns。

详细路径按 source clock 计为 audio 742、DDR UI 148、HDMI pixel 24、USB 11、clk50 1，共 926；DDR 的详细路径数与 summary 中负端点计数并非同一统计口径。全部原始路径留在机器记录，不能只修 worst path 后宣称全域完成。

## 状态、复核与回退

本轮完成固定父输入的 offline P&R、位流生成和门禁归因。`timing_closed`、`physical_gates_passed`、`io_electrical_complete`、`hardware_verified`、`deployment_allowed`、`release_ready` 均为 false。FPC 音频、HDMI、BLE 和实际外围验收仍未完成；没有继承历史版本的板上身份或物理验收。

以下命令只复核离线证据。重复 PLL 复核时写新 JSON，保留已经被下一个候选锁定的报告；不重新运行 P&R，不接触硬件：

```sh
python3 -m unittest discover -s projects/138k/push2_workstation/usb_a/sim -p 'test_workstation_physical_pll_audit.py' -v
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_serializer_startup_audit.py
GOWIN_SIMLIB=/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/simlib/gw5a python3 projects/138k/push2_workstation/usb_a/tools/workstation_physical_pll_audit.py --physical /Users/sphenicidition/.cache/gw138k-task-20261030/f03-capture-region-C11030F3 --json /Users/sphenicidition/.cache/gw138k-task-20261030/f03-capture-region-C11030F3/maintained-pll-independent-review.json --self-test
```

板卡、SRAM、Flash 和 accepted profile 均未被本候选改变。回退方式是弃用独立失败候选 C11030F3，保留父 F02、固定 source commit、原 manifest 和本轮完整证据。后续 DQS 物理布局或运行时源码改变都必须使用新候选身份，重新执行相应实现与完整门禁；不能重用 C11030F3。
