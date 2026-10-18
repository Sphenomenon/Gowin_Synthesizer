# NV3007 142×428 SPI 屏幕例程

面向 `GW5A-LV25MG121NC1/I0` 与本板 NV3007 屏幕的独立显示例程，使用 4 线 SPI mode 0、1 MHz、RGB565。默认显示八条竖色条、1 像素白边，以及每 32 行的 `000`、`032`、…、`416` 行号。

本目录从 `prj/lcd_bringup` 最终实板正常版本整理，原工程保留。2026-10-16 原镜像已通过 SRAM Program+Verify，用户确认“正常了。都正常了”：上下白边、行号及显示区域正常，底部杂色消失。来源、参数和哈希见 [PACKAGED_FROM.json](PACKAGED_FROM.json)。整理后已重新完成独立构建和仿真；本次整理未重新下载到实板。

## 文件

| 路径 | 内容 |
|---|---|
| `src/` | 顶层、SPI 字节引擎、初始化 ROM、引脚和时序约束 |
| `nv3007_279_init.txt`、`generate_init.py` | 初始化表及 ROM / 仿真预期生成器 |
| `sim/`、`run_sim.sh` | 字节引擎与完整画面的 SPI 引脚级仿真 |
| `build.tcl`、`build.sh`、`tools/` | 本地独立构建入口 |
| `program_sram.py` | 根据构建清单检查、下载并验证 SRAM |
| `builds/20261016_003736_574229/` | 原实板成功构建产物 |
| `reports/verified_build.json` | 原成功构建在本目录下的可移植清单 |
| `reports/hardware_20261016/` | 原始构建和 SRAM 验证记录 |

## 引脚与硬件

| 信号 | FPGA 球号 | 连接 |
|---|---|---|
| `clk` | E2 | 核心板 50 MHz 输入 |
| `lcd_mosi` | H8 | FPC1.1 SDA |
| `lcd_sck` | K5 | FPC1.2 SCL |
| `lcd_dc` | L5 | FPC1.3 DC |
| `lcd_ncs` | J5 | FPC1.5 CS，低有效 |
| `lcd_te` | H5 | FPC1.6 TE 输入，本例不等待 TE |

LCD 引脚使用 LVCMOS33，所在 BANK 供电为 3.3 V。RST 固定接 3.3 V，没有 FPGA 复位控制；背光没有独立 PWM。重新配置 FPGA 不会使屏幕断电复位。约束按本板连接设置，不能直接套用其他 PMOD LCD 引脚。

SPI 空闲时 SCK 为低，MSB first，RGB565 高字节先发。SDC 约束内部 50 MHz 时钟；尚无完整模组 AC 时序和 PCB 延迟资料，内部时序通过不代表完成屏幕外部时序签核。CST 的 `SLEW_RATE=SLOW` 被当前 Gowin 器件工具忽略，不能视为已生效。

## 构建与仿真

以下命令从本目录执行：

```sh
cd example/NV3007_LCD
sh build.sh
sh run_sim.sh
```

构建默认使用 `/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE`，可通过 `GW25K_IDE_DIR` 指定其他安装路径。入口先检查生成文件，再将项目复制到全新 ASCII 临时目录；综合与仅网表 PnR 分进程执行，并使用全局锁阻止并行 Gowin 构建。成功产物写入独立 `builds/<时间戳>/`，清单为 `reports/build_<时间戳>.json` 和 `reports/last_build.json`，失败保留此前成功产物。

本目录已重新构建通过，清单为 [build_20261016_212245_476061.json](reports/build_20261016_212245_476061.json)，setup / hold 违规端点均为 0，并通过下载前离线检查。原成功镜像也已在整体搬移目录后通过清单、哈希和时序检查。整理验证记录见 [packaging_verification.json](reports/packaging_verification.json)。该新位流尚未重新下载；原实板成功镜像仍由 `reports/verified_build.json` 指向。

仿真需要 PATH 中可用的 Icarus Verilog（`iverilog`、`vvp`），也可通过同名大写环境变量 `IVERILOG`、`VVP` 指定。两项测试已通过：字节引擎覆盖 256 种字节和默认 1 MHz 时序；整屏测试从 SPI 引脚解码，核对 250 个初始化字节、142×428 的 121,552 个像素字节、行号、白边、下一帧窗口和禁用态。仿真只加速等待与分频，保留完整像素窗口。

## SRAM 下载

先离线检查自带的原实板成功镜像，再下载：

```sh
python3 program_sram.py --manifest reports/verified_build.json --check-only
python3 program_sram.py --manifest reports/verified_build.json
```

使用刚构建的镜像时，将清单换为 `reports/last_build.json`。下载前检查 SHA256、器件、安全位及 setup / hold 时序；使用 Gowin `programmer_cli`，适配 FT2232HL cable 1、channel 0、15 MHz，执行 SRAM Program+Verify 并核对 UserCode / Status。只写 SRAM，断电后需重新加载。

原实板成功镜像 SHA256 为：

```text
54577ddec2d4a9d1003c77a43fa9b199a1ff7f91b2b72ae251e17784d5fa7923
```

原镜像 UserCode 为 `294D`，Status 为 `0x70022020`；50 MHz 时钟约束下 setup / hold 违规端点均为 0。原始记录保留历史路径，当前操作使用本目录清单。

## 修改画面与初始化

在 [src/lcd_bringup_top.v](src/lcd_bringup_top.v) 修改顶层参数后重新构建：

| 参数 | 默认值 | 用途 |
|---|---|---|
| `WIDTH` / `HEIGHT` | 142 / 428 | 逻辑画面尺寸 |
| `COL_OFFSET` / `ROW_OFFSET` | 12 / 0 | GRAM 窗口起点，默认 x=12…153、y=0…427 |
| `MADCTL` | `8'h00` | 方向及颜色顺序控制 |
| `INVERT_DISPLAY` | 0 | 不反色 |
| `ENABLE_ROW_LABELS` | 1 | 设为 0 显示纯彩条和白边 |
| `SPI_HALF_PERIOD` | 25 | SCK = 50 MHz / (2 × 此值) |
| `FRAME_GAP_MS` | 500 | 完整帧后的等待时间 |

默认一帧包含 60,776 像素，1 MHz 下传输约 1 秒。`MS_TICKS` 用于仿真加速，实板应保留默认 `CLK_HZ/1000`。修改尺寸或偏移时应保持窗口位于模组合法 GRAM 范围内，并同步核对仿真预期。

初始化表仅编辑 [nv3007_279_init.txt](nv3007_279_init.txt)，再生成并检查：

```sh
python3 generate_init.py
python3 generate_init.py --check
sh run_sim.sh
sh build.sh
```

生成器同时更新 `src/lcd_init_rom.v` 和 `sim/init_expected.mem`，ROM 不依赖运行目录或外部 `$readmemh` 文件。默认启动等待 250 ms；表内 Sleep Out 后等待 120 ms，表结束后再等待 150 ms，随后设置 MADCTL、反色和窗口并写入图案。

## 初始化来源与许可

初始化采用 Arduino_GFX 固定提交 [`33869265f21d1aaa8ecc61d2f43de40cf1fe31c8`](https://github.com/moononournation/Arduino_GFX/tree/33869265f21d1aaa8ecc61d2f43de40cf1fe31c8) 的 [`nv3007_279_init_operations`](https://github.com/moononournation/Arduino_GFX/blob/33869265f21d1aaa8ecc61d2f43de40cf1fe31c8/src/display/Arduino_NV3007.h)，共 119 条命令、250 个 SPI 字节。同提交配套的 142×428、rotation 0 示例采用列偏移 12、行偏移 0。完整 BSD 许可声明保留在 [THIRD_PARTY_LICENSE.txt](THIRD_PARTY_LICENSE.txt)。

当前只确认 NV3007 控制器与显示分辨率，具体实装模组型号尚未补齐。该初始化已在当前实板显示正常；用于其他模组时仍应核对厂家初始化表、电源和 Gamma 参数。
