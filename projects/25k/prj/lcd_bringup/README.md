# LCD 首屏候选测试

本工程用于本板 NV3007 / 142×428 / 4 线 SPI 的首屏调试。初始化表有可追溯的开源来源，具体实装屏模组型号仍未补齐。2026-10-16 第三轮实板验证 **PASS**：用户对新校准图确认“正常了。都正常了”，底部杂色消失，上下白边及行号正常。最终采用配套上游示例的 **`COL_OFFSET=12`、`ROW_OFFSET=0`**，并保留每 32 行的十进制坐标标记。该版已完成隔离构建、时序检查、SRAM 编程验证及上述实板显示检查。

## 接线与限制

| 顶层端口 | FPGA 球号 | 底板连接 | 方向 |
| --- | --- | --- | --- |
| `clk` | E2 | 官方 52300 核心板 50 MHz | 输入 |
| `lcd_mosi` | H8 | FPC1.1 SDA | 输出 |
| `lcd_sck` | K5 | FPC1.2 SCL | 输出 |
| `lcd_dc` | L5 | FPC1.3 DC | 输出 |
| `lcd_ncs` | J5 | FPC1.5 CS | 输出，低有效 |
| `lcd_te` | H5 | FPC1.6 TE | 输入，本测试不等待 TE |

LCD 信号所在 BANK1 按 3.3V、LVCMOS33 约束；用户已确认全部 BANK 当前均为 3.3V。底板 FPC1.4 RST 固定接 3.3V，没有 FPGA 复位端口。LEDA 直供 3.3V，LEDK 经 56Ω 接地，没有独立背光 PWM。不能用 FPGA 重新配置代替屏幕断电复位。

SCK 空闲低，SPI mode 0，MSB first，默认 1 MHz（50 MHz / 2 / 25），输出驱动为 4 mA。CST 请求 `SLEW_RATE=SLOW`，但本次工具对该器件报告四条 `CT1146: ignore SlewRate setting`，因此不能把慢沿设置记为已生效。启动等待与帧间等待期间 CS 高，SCK 低；每字节 8 个完整时钟，DC/MOSI 在上升沿前已稳定。`ENABLE_PANEL_INIT=0` 时持续保持 CS=1、DC=0、SCK=0、MOSI=0。

## 候选初始化依据

2026-10-15 通过浏览器读取以下固定提交的公开源码：

- [Arduino_NV3007.h](https://github.com/moononournation/Arduino_GFX/blob/33869265f21d1aaa8ecc61d2f43de40cf1fe31c8/src/display/Arduino_NV3007.h)：采用其中 `nv3007_279_init_operations`，119 条命令、250 个 SPI 字节以及 Sleep Out 后 120 ms 等待。
- [Arduino_NV3007.cpp](https://github.com/moononournation/Arduino_GFX/blob/33869265f21d1aaa8ecc61d2f43de40cf1fe31c8/src/display/Arduino_NV3007.cpp)：明确强制 `SPI_MODE0`，以 `2A/2B/2C` 设置窗口并写 GRAM，以 `36` 设置 MADCTL。
- 同提交的 [PDQgraphicstest/Arduino_GFX_display.h 第 102–103 行](https://github.com/moononournation/Arduino_GFX/blob/33869265f21d1aaa8ecc61d2f43de40cf1fe31c8/examples/PDQgraphicstest/Arduino_GFX_display.h#L102)：2.79 寸候选表的配套示例明确使用 142×428、rotation 0、IPS false、列偏移 12/14、行偏移 0/0。当前 rotation 0 对应列偏移 12。
- 同提交的 [license.txt](https://github.com/moononournation/Arduino_GFX/blob/33869265f21d1aaa8ecc61d2f43de40cf1fe31c8/license.txt)：BSD，完整声明保存在 `THIRD_PARTY_LICENSE.txt`。

上游还有默认 168×428 初始化表，其电源、Gamma 和扫描设置与 2.79 寸表不同。本工程没有混用这些数值，也没有添加猜测的模拟寄存器。现有项目只给出了控制器和分辨率；实际模组型号、尺寸、采购链接、厂家初始化表与 GRAM 偏移仍需补齐。**分辨率相同不能证明候选模拟参数完全适用。**

`nv3007_279_init.txt` 是候选表的逐命令转录。`generate_init.py` 将其生成可综合的 `src/lcd_init_rom.v` 和仿真预期文件。ROM 不依赖工具工作目录或 `$readmemh` 路径。替换为厂家表时只编辑文本表再运行生成器。

候选表本身没有硬件/软件复位命令，本工程也未杜撰软复位步骤。FPGA 配置完成后先等待 250 ms，再发送候选表、等待额外 150 ms，设置 MADCTL / inversion / 窗口并输出 RGB565 图案。若模组需要特定硬复位脉冲，本板固定高的 RST 连接将成为进一步排查项。

## 显示内容与可调参数

逻辑图案为 142×428，当前候选 GRAM 窗口为 x=12…153、y=0…427，RGB565 高字节先发。显示八条竖色条，从左至右为白、黄、青、绿、品红、红、蓝、黑，外加 1 像素白边。完整帧为 60,776 像素 / 121,552 字节；1 MHz 下刷新约 1 秒，随后暂停 500 ms 再发一帧。首帧全部发送约需 1.5 秒。

`ENABLE_ROW_LABELS=1` 时，逻辑 x=2…25 区域每 32 行显示 `000`、`032`、`064`、…、`416` 及短横线，用于判断实际画面方向和缺失区域。每个标签表示所在 32 行块的起始 y；白底占该块第 +1…+10 行，5×7 数字占 +2…+8 行，横线在 +5 行。外围白边优先于标签。设置 `ENABLE_ROW_LABELS=0` 可恢复纯彩条图案。RTL 用常量 BCD 表转换行号，没有运行时十进制除法。

2026-10-16 的首次坐标版综合成功，但后续读取综合网表时 `gw_sh` 发生内存损坏崩溃。该版的 `glyph[34-glyph_y*5-glyph_x]` 被综合为一个新增 `MULT12X12`；旧 ROW+10 成功产物仅有原来的延时 `MULTALU27X18`。当前字体实现改为按 `glyph_y` 选择固定 5 位切片，再按 `glyph_x` 选择固定像素位，消除字体地址中的乘法表达式和动态位索引，保留完整图案。新网表已确认不再包含 `MULT12X12` 实例，并与全新英文临时目录、独立综合/PnR 进程、串行构建及成功产物隔离组合完成了本轮构建。此结果不能证明新增 DSP 就是崩溃根因；当前规避流程与限制见 [构建工具说明](../tools/README.md)。

当前参数为 `COL_OFFSET=12`、`ROW_OFFSET=0`、`MADCTL=0x00`、`INVERT_DISPLAY=0`。偏移与本工程采用的同一固定提交、同一 2.79 寸初始化表的配套示例一致；本轮保留初始化表、MADCTL 和反色。之前 ROW+10 来自另一个 [TFT_eSPI 社区配置](https://github.com/Bodmer/TFT_eSPI/issues/3851)，实板效果基本不变，已停止采用。NV3007 V1.0（2024-06-19）数据手册 §5.2（印刷 45 页 / PDF 52 页）明确 GRAM 合法范围 X=0…167、Y=0…427，禁止超界；ROW10、HEIGHT428 的末行 437 不满足这版手册。手册公开副本见 [NV3007_Datasheet_V1.0_20240619-2.pdf](https://github.com/Hack-a-Day/2025-Communicator_Badge/blob/main/documentation/datasheets/NV3007_Datasheet_V1.0_20240619-2.pdf)。这些证据支持当前候选，仍需核对实际模组。`MS_TICKS` 是仿真加速入口，实板必须保留默认 `CLK_HZ/1000`。

## 文件与验证

Gowin 顶层为 `lcd_bringup_top`。添加 `src/lcd_bringup_top.v`、`src/lcd_spi_byte.v`、`src/lcd_init_rom.v`，使用同目录的 CST 和 SDC。不要套用官方 PMOD LCD 的引脚表：本底板球号不同。

主工程统一执行 Gowin 构建，入口为 `sh prj/tools/gowin.sh prj/lcd_bringup/build.tcl`（从工作区根目录执行）。包装器自动将本项目复制到全新英文临时目录，串行使用独立进程完成综合和仅加载 `.vg` 的 PnR，成功后才保存产物；详见 [构建工具说明](../tools/README.md)。本板实际器件选择为 `set_device -name GW5A-25A GW5A-LV25MG121NC1/I0`，综合工具名使用小写 `gowinsynthesis`。E2 是 CPU / SSPI 复用脚，已开启 `set_option -use_cpu_as_gpio 1` 和 `set_option -use_sspi_as_gpio 1`，JTAG 保留专用功能。

2026-10-16 独立复核了主流程完成的首轮（列/行偏移均为 0）Gowin 全流程构建产物；报告生成时间为 2026-10-15 23:56:59。`impl/pnr/lcd_bringup.fs` 已生成，综合、布局布线和 bitstream 生成均成功。`lcd_bringup.tr` 报告 50 MHz 时钟约束、实际 Fmax 78.876 MHz，setup / hold 违规端点均为 0，最差 setup slack 7.322 ns、hold slack 0.247 ns。`lcd_bringup.rpt.txt` 的最终引脚表与本节球号、输入/输出方向、3.3V 和输出 4 mA 一致。主流程随后完成 ROW+10 版的构建与下载，但已有 `.fs` 不应当作本轮 COL12/ROW0 加坐标版的产物。

当前 COL12/ROW0 加坐标版由完整包装入口构建成功，清单为 [reports/last_build.json](reports/last_build.json)，本次固定记录为 [build_20261016_003736_574229.json](reports/build_20261016_003736_574229.json)。新镜像为 [builds/20261016_003736_574229/impl/pnr/lcd_bringup.fs](builds/20261016_003736_574229/impl/pnr/lcd_bringup.fs)，SHA256 为 `54577ddec2d4a9d1003c77a43fa9b199a1ff7f91b2b72ae251e17784d5fa7923`；下载须从成功清单取路径并核对哈希，不使用旧 `impl` 目录推断当前镜像。综合与 PnR 独立进程均返回 0，PnR 日志明确跳过综合。新 [时序报告](builds/20261016_003736_574229/impl/pnr/lcd_bringup.tr) 在 50 MHz 约束下 Fmax 为 68.714 MHz，setup / hold 违规端点均为 0，最差 setup slack 5.447 ns、hold slack 0.247 ns。

主流程核对清单 SHA256 后以操作 4（SRAMProgramVerify）下载本镜像并通过，读回 UserCode `294D`、状态 `0x70022020`；记录见 [sram_col12_program_20261016.log](sram_col12_program_20261016.log) 和对应 JSON。第三轮实板检查中，用户确认校准图“正常了。都正常了”：底部杂色消失，上下白边及行号正常，当前 COL12/ROW0 首屏显示验证通过。

首轮镜像启用了默认 Security Bit，Programmer 在编程完成后报告 SRAM readback verify 地址 0 失败。主流程读回 UserCode 与镜像一致，状态 `0x70026020` 的 wakeup、done_final、security_final 置位，CRC / ID / Bad Command / Timeout 错误位均为 0；用户也实际看到图案。本机官方 `UG714-1.0.4E` §4.3/4.4（印刷 54/55 页，PDF 62/63 页）明确说明安全位会禁止配置后 SRAM 数据读回。当前 `build.tcl` 设置 `set_option -bit_security 0`，用于本地测试镜像的 readback/verify；主流程已使用 ROW+10 版完成 SRAMProgramVerify，UserCode B244、状态 `0x70022020`，安全位清除且读回验证成功。A 版 25K 的 JTAG 配置 TCK 最低 15 MHz（同手册 §3.4），因此 Programmer 自动把低速请求调整为 15 MHz 有器件依据。

未用引脚采用 `set_option -unused_pin default`。本机官方 `SUG1220-2.0E` §3.3.20、印刷第 66 页（PDF 第 73 页）明确说明该值将未用 GPIO 配置为 **input tri-state with weak pull-up**；另一合法值 `open_drain` 才是开漏输出。本次最终引脚报告也确认 BLE 的 J8/K8/K9/L9 和 USB1 的 L6/K6 均为 `in / Drive OFF / Pull UP`，没有主动驱动这些外设。弱上拉仍可能影响悬空输入的默认电平，应与主动输出区分。

SDC 约束真实的 50 MHz 内部时钟。屏幕 AC 时序和 PCB 延迟尚无完整资料，当前没有编造输出延迟；内部时序通过不代表已经完成 LCD 外部时序签核。

运行 `sh run_sim.sh`。字节引擎单测使用实板默认分频，覆盖 256 种字节、1 MHz / 500 ns 半周期、忙时额外启动请求被忽略以及完整收尾下降沿。整屏测试从真实 SPI 引脚按上升沿解码，核对候选表所有 DC/数据、Sleep Out 与帧间等待、SCK/MOSI/DC 时序、完整默认分辨率每一个像素字节、下一帧窗口重新发送，以及禁用初始化时的静态安全电平。整屏测试只加速延时和 SPI 分频，不缩小默认像素窗口；独立预期 CASET 为 `00 0C 00 99`，RASET 为 `00 00 01 AB`。坐标参考模型使用十进制算术和逐行字体，与 RTL 的 BCD 表分开；另有手工指定的 `000`、`128`、`416` 数字像素、白底、横线、纯彩条、白边和关闭标签的坐标断言。仿真通过只验证 RTL 发出了预期序列，不能证明物理屏幕接受它。

2026-10-16 已执行 `sh run_sim.sh`，两项测试均通过当前 COL12/ROW0 加行坐标版，也在固定切片字体改写后重新通过。当前修改涉及默认列/行偏移、行坐标图案及对应测试，没有修改候选初始化表、MADCTL 或反色设置。主流程已完成本版构建与 SRAMProgramVerify，用户已确认第三轮实板白边、行号及显示区域正常，底部杂色消失；最终保留 COL12/ROW0。
