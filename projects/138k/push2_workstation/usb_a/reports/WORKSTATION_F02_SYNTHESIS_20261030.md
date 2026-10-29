# F02 revision 2：干净克隆综合与来源审计

日期：2026-10-30（Asia/Shanghai）。固定源码 `3d4b3175d0f20d0b787b61b43e4543739b26bca1` 的完整工作站综合成功，正式 source/hierarchy audit 成功；USB CPU 的 16,384 words 和新 AE350 固件的 4,096 words 均已从综合网表重建并逐字核对。**综合后严格 profile verify 仍失败**：Gowin 新增了会话文件，原有 510 项 staged 闭包没有缺失或字节变化。本轮没有 P&R、位流、板测、SRAM 或 Flash 操作。

机器可读记录：[f02_synthesis.json](workstation_task_20261030/f02_synthesis.json)。此前固件导入、容量和回归见 [F02 AE350 报告](WORKSTATION_F02_AE350_20261030.md)。两份报告对应不同验证阶段。

## 固定输入及运行方式

使用 `git clone --no-local --no-checkout` 后 detached checkout 的干净克隆：

```text
/Users/sphenicidition/.cache/gw138k-task-20261030/clean-rev2-3d4b317
```

显式选择 `custom138k-workstation-v1` revision 2；244 项 profile 来源全部受 Git 跟踪，230 个启用编译输入，原生来源快照 665 项，完整 staged 闭包 510 项。正式审计之后克隆的 `git status --porcelain` 仍为空。本次未从正在修改的共享工作区取源，也未改冻结基线、候选 RTL、ROM 或约束。

候选目录为：

```text
/Users/sphenicidition/.cache/gw138k-task-20261030/clean-rev2-profile-candidate
```

本次 authoritative profile 身份为 `custom138k-workstation-v1-f5b723250388add5`；底层装配继承的 `custom138k-native-integration-20261027-a26` 仅说明组合来源，不能作为新 AE350 ROM 的部署身份。HDMI 为 1080p60，USB HS 允许标志为 true，TF 为 WAV；该 profile 目前只声明实际实现的 48 kHz，未声明 44.1 kHz 已接整机。器件为 `GW5AST-LV138PG484AC2/I1`，顶层为 `workstation_custom_138k_top`。

| 输入或产物 | SHA256 |
|---|---|
| profile 配置 | `0dc585ff6a1674b0bf6e8b791197ebd507922f820547cd1b04795f632f0aba24` |
| profile artifact | `ea87fd29d07287831073e0b9effa1953d92aa8b8e1300c69f454a9737b091d33` |
| integration_inputs | `10deb0aa1cd172838c98b1f8d675b0ae41b812641549ba3bde432b355caabd2b` |
| USB CPU ROM | `4211ea0f1fc1d5a3dde02979e25652b2cbf5a1329cf109b1206c151c3b4eabc1` |
| AE350 ROM | `3ded01f97acaa87a9331038cc490e2dc03f7afbfa7bd4880296dbfad8632435b` |
| AE350 ELF | `4986d67e445aa593575b76cf17065e4561a315f10b19c43111dee693ef753845` |
| 综合 netlist | `27b30ac791323f05dc68cd5d9ea6ccaaf14d6a122c5fe2b978cb4714b7fdcf18` |
| 综合资源报告 | `d54b5672a8bb5a4f9fa708e26f011933762ed684b312e89c1a6a90e964618b8b` |
| 完整 synthesis.log | `27647493414af20df7dc63c69d4d91fbeab771b904b93080a7bac856a99a2fc7` |

清洁目录 prepare 先通过严格 profile verify 及全部 12 项 profile 回归。与共享工作区 prepare 相比，只有生成的 BLE `patch_path.vh` 绝对路径和 USB 固件 `build.log` 中警告的源码路径不同；USB／AE350 ROM 和 AE350 ELF 字节相同。闭包纳入了这些路径相关字节，所以不能沿用共享目录的 `…-2bce61be83aaff38` 身份。完整配置、固件工具、CST／SDC／GPRJ／Tcl、审计器及产物哈希均在 JSON 中。

从候选 `workstation/Prj1` 工作目录调用既有 `scripts/custom_board_synthesis.tcl`：

```text
/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/bin/gw_sh scripts/custom_board_synthesis.tcl
```

工具报告版本为 **V1.9.12**。`gw_sh` SHA256 为 `c7650c2d6840da20eb9a32a7a8b5ecc385c428d3ed74fef436150a85ca8bac01`，`GowinSynthesis` 为 `5dbd2b4d47f823c8844d55867eb06c9c0151e5ae79a93e2b61322f5e474f17b2`。初次 `--version` 探测缺少 `@rpath/libGWTE.dylib`；正式调用将 `DYLD_LIBRARY_PATH` 和 `DYLD_FRAMEWORK_PATH` 均设为该 IDE 的 `lib` 目录后成功。运行持有 `/private/tmp/gw138k-build.lock`，04:16:12 至 04:22:57，405.159 秒，退出码 0，末尾为 `GowinSynthesis finish`。仅执行 `run syn`，没有配置 GAO 或执行 `run pnr`。

## 资源与时钟结果

| 综合资源 | 数量 |
|---|---:|
| Register | 55,571 |
| LUT | 73,648 |
| ALU | 15,552 |
| BSRAM（综合等效） | 272 |
| SSRAM | 419 |
| MULTALU27X18 | 46 |
| MULT12X12 | 41 |
| MULT27X36 | 45 |

272 是**综合等效** BSRAM，不能用 `340−272` 声称物理可用余量。历史 C1 是业务物理 BSRAM 317 加 GAO 1、总计 318/340，CLS 61,184；本次未测物理数值，也未复用其时序结论。

| 时钟 | 综合报告要求 MHz | 综合估算 MHz |
|---|---:|---:|
| clk_50m | 50 | 54.944 |
| usb2_ulpi_clk | 100 | 72.966 |
| clk_12m288 | 100 | 76.287 |
| audio PLL | 76.8 | **60.489** |
| USB PLL | 48 | 59.723 |
| LCD PLL | 31.5 | 42.464 |
| DDR memory PLL | 400 | 1338.315 |
| CPU RAM PLL | 50 | 311.818 |
| CPU core PLL | 100 | 1455.604 |
| DDR UI CLKDIV | 100 | 201.532 |
| HDMI pixel | 148.5 | 212.902 |

ULPI 与 12.288 MHz 参考在综合报告中的 100 MHz 是工具默认要求；板级权威时钟仍为 60 MHz 和 12.288 MHz，不据此改钟或放宽约束。音频域实际目标为 76.8 MHz，60.489 MHz 的不利估算需要后续定位。上述全部是综合估算，均不构成 routed STA。

日志共有 351 条 WARN，无 ERROR／FATAL。代码计数：CK3000=3、CV0016=1、EX1998=9、EX2478=1、EX2526=1、EX2565=108、EX2598=16、EX3073=13、EX3638=41、EX3670=1、EX3780=3、EX3791=141、NL0002=13。包含隐式重复声明、表达式宽度处理、未连接／优化掉的端口及未用 `amp_fpga_det`；不能将综合成功理解为警告已解决。完整日志原样保留并锁定哈希。三个 CK3000 关系警告为：

```text
clk_50m → u_lcd/u_pll/PLL_inst/CLKOUT0.default_gen_clk
u_audio_clock/g_hardware.u_pll/PLL_inst/CLKOUT0.default_gen_clk → u_lcd/u_pll/PLL_inst/CLKOUT0.default_gen_clk
u_lcd/u_pll/PLL_inst/CLKOUT0.default_gen_clk → u_audio_clock/g_hardware.u_pll/PLL_inst/CLKOUT0.default_gen_clk
```

## 审计结果及严格清单失败

使用固定克隆自身的 `tools.workstation_custom_board_audit`，退出码 0，输出保存在候选根目录 `source_hierarchy_audit.json`。24 项 feature/storage 层次存在；133 项逻辑引脚位置对应 142 个物理端口位，包含明确的负端隐式配对。USB2 CDC、事件 FIFO 端点、复位释放链、反馈时钟域、主音量权威连接及 Delay 双向 512×65 FIFO 各 4 个 BSRAM 均经过源码／综合网表检查。共享 CDC 有 157 项约束、145 个已解析 selector，opaque DDR 中的 13 个 selector 留给路由阶段。DDR UI 时钟仅验证到封装／观察寄存器边界，审计中的完整时钟、物理 CDC、PLL／时序完成标志继续为 false。

正式审计已重建 USB ROM 全部 16,384 words。另用只读脚本 `/Users/sphenicidition/.cache/gw138k-task-20261030/verify_f02_ae350_netlist.py` 独立核对 AE350：唯一 `gw138k_boot_memory` 模块中的 8 个 `pROM` 均为 4-bit、`READ_MODE=0`，地址为 `{rom_address[13:2],GND,GND}`，各输出对应一个 nibble。先核对当前工具 GW5A `prim_sim.v` 的 64 个 INIT 默认值均为零及其 4-bit 地址语义，再按 `INIT_RAM_XX` 拼接并重建 4,096 words；与安装的新 `firmware/boot.mem` 无差异。该证据为 `ae350_netlist_rom_verification.json`，摘要和原语／核对脚本哈希纳入版本化 JSON。它证明 ROM 装入本综合网表，未证明 CPU 实板执行或业务服务时限。

紧接着运行固定克隆的 `tools.workstation_profile verify`，退出码 **1**，报：

```text
ValueError: workstation profile staged file inventory changed
```

逐项比较结果为 missing=0、changed=0、extra=1。唯一新增项 `Prj1.gprj.user` 为 830 B，SHA256 `8d6a69454c001be5ae95ef6ea3407e33c0b395e45c15b392eac39ef7f5bf445b`，是 Gowin 的 `ProjectUserData` XML，记录 `Synthesis=2`、`Pnr=0` 及 `impl/gwsynthesis` 下的 netlist／report／resource 路径。它不是启用编译输入，但严格验证器只排除 `impl` 目录，因此仍正确报告清单不同。该文件和失败 stderr 均保留；本轮未删除工具输出、修改 validator 或改写 prepare 元数据。需另行明确综合后工具输出的精确分类和漂移拒绝规则，才可把该命令报告为通过。

## P&R 前置核对及剩余边界

既有 `workstation_custom_board_implementation.py` 会先重跑正式综合审计，再以新八位 UserCode、显式离线电气风险确认，把经哈希检查的 netlist／CST／SDC 复制到独立物理实验目录；默认 place=2、route=0、replicate=0。可选 ULPI bypass 适配仅追加已核对的 12 个 LVCMOS33 声明，不改球位或 SDC，不表示电气／外部 IO 时序验收。

物理检查入口仍为 `reports/workstation_physical_20261025/` 的 `check_timing.py`、`check_pll.py`、`check_common_cdc.py`、`check_routes.py`，脚本哈希已记录。**已发现覆盖缺口**：`check_routes.py` 仅在父身份以 `-a23` 结尾时核对 DDR initialization hold 路径及可选 floorplan；本次继承的 a26 不进入该分支。后续必须按实际 a26 路径／约束做受检适配或独立核对，不能用该脚本的绿色退出码冒充已覆盖此路径。

本阶段仅完成新固件整机候选的综合及来源／网表核对。严格 profile 清单分类、完整 IO／CDC／PLL／routed timing／物理资源、双采样率切换、统一最终 PCM/tap、D5 scan window 整机接入、DDR USB 像素和 AE350 业务迁移均继续按各任务验收；AE350 调用链栈上界、运行水位及最坏服务间隔也未验证。`physical_gates_passed`、`hardware_tested`、`sram_programmed`、`flash_programmed`、`deployment_allowed` 和 `release_ready` 全部为 false，`bitstream_sha256` 为 null。

回退无需板卡操作：本轮未改变板上内容。保留固定克隆及候选证据，可按 `3d4b317` 与所列哈希复现；既有 accepted／pinned／未指定 profile 来源策略没有因本轮综合发生变化。
