# 138K 原生资源候选：源码优化与本地综合

日期：2026-11-02，UTC+08:00。范围是主线 `4e636f37` 上的原生新板装配；候选身份 `custom138k-native-integration-20261102-a27`，1080p60，完整 231 项编译输入。工作分支 `codex/138k-resource-optimization`，本轮未提交、未创建 PR。

## 修改范围

| 项目 | 原生候选选择 | 保留的行为 |
|---|---|---|
| BLE 请求重放 | 32 条缩为最近 1 条，关闭 60 秒过期计时；浅缓存用分布式 RAM | nonce、high-water、同 ID 请求内容冲突检查；最近请求重试不重复执行，已淘汰的旧请求仍返回既有错误 |
| GATT 回复复制 | 回复槽到发送缓冲逐时钟复制一个字节 | 两个回复槽和独立 active TX，完整复制后才释放槽和启动发送 |
| BLE PCM 存储 | 16,384 帧、64 KiB PCM 放入 DDR；片内保留 8 KiB 下载缓存 | 录音容量、立体声字节序、CRC、无损编码、下载窗口和失败语义 |
| USB CPU RAM | 64 KiB 缩为三个 16 KiB bank，共 48 KiB；相应生成 startup、linker 和分 bank ROM | RV32I、字节写、取指、MMIO、错误返回；vendor 原始字节不改 |
| DDR 启动 BIST | 原生候选显式旁路 | DDR 校准与就绪屏障；独立 BIST 默认完整测试 |
| 模型加载 | 关闭写入 DDR 后的重复回读 CRC | Flash 输入 header/payload CRC、UART 输入 CRC、错误时 UART 恢复 |
| 静态 cue ROM | prepare 时核对合法性和时间单调，播放时不重复检查 | 同一份 ROM 和事件输出 |
| 计数器 | GATT 毫秒分频和采样年龄按实际上界缩位；仅判非零的 PC CDC 丢失统计改为 sticky | 原 CDC 握手和音频不背压；其它需要计数的实例保留计数 |

GATT 的实际准备路径原本已裁成 32 字节缓冲，本轮没有把旧 raw 源的 80 字节容量重复计算为节省。独立 25K 协议默认仍为 32 条／60 秒、本地存储；原生 138K wrapper 才选择上述简化参数。

新 DDR 分区由 `rtl/ddr_address_map.vh` 单一分配：字节地址 `0x30100000–0x3010FFFF`，native word base `0x0C040000`。占 bulk pool 的第二个 1 MiB granule 中首 64 KiB，不覆盖已有 delay 区。编译期地址换算、容量与重叠检查保留。

`workstation_ble_pcm_store` 用 16 项命令 FIFO 保持采集写入和下载读取顺序；返回队列为 4×256 bit，显式用分布式 RAM，避免 128 字节内容映射为 8 个 BSRAM。`workstation_ddr_pair` 在原 music owner 后公平合并 CNN/BLE，背压时固定当前选择，读响应保持归属。音频不等待 DDR；采集队列满进入录音失败，取消下载先排空旧预取，DDR 单独复位立即撤销存储就绪。仍是约 0.341 秒短录音，未扩成长期录音后端。

## 构建来源

使用现有 `build.py --prepare-custom-board --logic-only`，不另建编号生产构建器，不切换 accepted full83、pinned timing85 或普通 resource-timing 的来源策略。对活动 cue ROM、地址表和小 FIFO 的覆盖记录覆盖前后哈希；冻结基线、vendor 和历史证据不修改。720p 准备身份增加 a27 后缀区分新输入，本轮只综合 1080p60。

用户给出的 `reports/workstation_task_20261030/F6_netlist/` 位于远端开发分支；其 manifest 表明它是 `C21031F6` 综合后逻辑网表，来源 checkpoint `ba2ba0273f4fc68532240844d9207859f1c4ce25`。它不是底板／功放／BLE 的 PCB `.tel` 接线网表，也不是本轮主线 RTL 输入，未用来替代接线核对或混入 F6 分支业务代码。

Windows checkout 的 `core.autocrlf=true` 会改变锁定文件字节，因此从 `git -c core.autocrlf=false archive HEAD` 导出 Git 原始字节，在忽略的 `results/resource_opt_20261102/optimized` 快照上覆盖本轮修改并准备。源码快照 657 项，完整 staged 输入 513 项；原始清单位于 `results/resource_opt_20261102/a27_final/integration_inputs.json`，版本化证据另存 `resource_optimization_20261102/verification.json`。后续复现也须保留基线规定的字节格式，不能关掉哈希检查来处理换行。

Gowin 工具为本地 `Gowin_V1.9.12.03_x64/IDE/bin/gw_sh.exe`。USB 固件使用 Espressif RISC-V GCC 15.2.0，实际业务固件 21,312 字节，静态 RAM 末端 27,160，48 KiB 布局剩余 21,992 字节供栈使用；此值是静态余量，不是已测出的最坏栈峰值。

```powershell
python <canonical-source>/build.py --prepare-custom-board --logic-only --custom-board-output <new-output>
# cwd: <new-output>/workstation/Prj1
& C:/Gowin/Gowin_V1.9.12.03_x64/IDE/bin/gw_sh.exe scripts/custom_board_synthesis.tcl
# 将完整 stdout/stderr 保存到 <new-output>/synthesis.log 后，在同一源码快照执行：
python -m tools.workstation_custom_board_audit <new-output>
```

## 验证

- 新增资源回归 10/10：单条无过期重放、实际准备后的 GATT 缓冲复制、DDR 采集下载及 CRC／失败、最大窗口与取消、满容量地址、FIFO overflow／DDR 单独复位、DDR 仲裁背压／公平／响应归属、48 KiB RAM bank 端点／byte mask／越界、BIST 旁路、模型 CRC／fallback、静态 ROM 检查。
- accepted/full85 来源回归 10/10，未把活动 CNN 或资源候选输入混入已接受构建。
- 既有兼容回归 5/5：BIST 对冻结参考 548 次逐拍比较、两种缓存元数据存储的重放／淘汰／过期、原协议录音重放与断连、完整 HCI completion／畸形长度拒绝、默认 CPU RAM 顺序和 fault。
- 原生 UART/H5 patch／GATT／PCM wrapper 回归 1/1。该传输回归显式选择本地存储，DDR 路径由上面的专门回归验证。
- 另外五项构建边界分别通过：默认旧板 token 保持、完整新板 prepare 的端口／闭包／禁止发布路径、CLI 混用拒绝、固件失败时保留非部署状态、缺少源码时拒绝生成候选。完整 prepare 用本次 Windows GCC 已实际生成并核对的固件作为 fixture，未把 WSL GCC 10.2 的编译失败算作通过；此组跨两次执行核对，NTFS 下重复基线还原较慢，第二次在已通过完整 prepare／CLI 后中断重复的失败注入项，后者及缺源项已在第一次通过。
- 48 KiB 实际 RV32I 执行另外通过 HS／FS 两组：USB 枚举、512／64 字节回环、复位和错误恢复。复用原 `cpu_enumeration.c` 探针固件与原 testbench，仅为仿真设置 RAM 参数；不能将它当作完整工作站固件的最坏栈覆盖或实物 HS 验收。脚本与原始日志在忽略的 `results/resource_opt_20261102/cpu48*`。
- CPU 综合网表全部 12,288 个初始化字与业务固件 ROM 逐字核对；保留功能层次、vector geometry ROM、USB packet RAM、delay FIFO、时钟／PLL 来源、157 条共享 CDC 约束、USB CDC／复位、反馈源时钟和公共主音量路径审计。新存储 FIFO 另检查 Gray 同步器和定向 10 ns 最大延迟约束。

综合和最终审计的数值见下面的最终结果。未安装 Yosys，本轮未重新宣称形式验证通过。

## 最终综合结果

最终 Gowin 综合从 **13:06:40 至 13:16:44**，约 **10 分 4 秒**，退出码 0。修正后的独立网表审计通过。

| 综合资源 | 最终统计 |
|---|---:|
| LUT | 74,259 |
| Register | 54,428 |
| ALU | 15,270 |
| BSRAM（综合统计口径） | **233** |
| SSRAM | 479 |

子树 BSRAM：原生 USB 31（CPU bus 24、CPU register file 2、USB packet RAM 4、输入事件 FIFO 1），音频工作站 66、TF 5、识别 23、BLE 32、DDR controller 16、视频 44、AE350 boot 16。BLE 外部存储适配本身只用 4 个 BSRAM 下载缓存；两个跨域队列合用 76 个 SSRAM，返回队列没有再占 8 个 BSRAM。以上子树互不重叠，合计 233。

历史 a26/C1 的综合报告为 LUT 73,630、ALU 15,292、BSRAM 272，本轮 BSRAM 数值低 39；本轮 LUT 高 629。两轮来源／固件工具链不同，本轮未重综合完全相同环境的未优化版本，因此它们仅作历史规模参照，不能把差值认作严格 A/B 净收益。C1 的 318 是含 GAO 的物理 BSRAM 数量，不能与本轮综合 233 混为同一口径或据此计算物理余量。

保留 **354 条综合警告**；其中包含 LCD 与其它时钟的 CK3000 关系提示。音频域综合估计最高频率 **67.210 MHz**，低于 76.8 MHz 目标；这既不表示路由后已通过，也不能因综合退出 0 而宣称时序闭合。原生时钟计划未放宽。

最终网表 SHA256：`743b87eeec59477583db47842cbc8df6d9f4dfc455355b9b53fa2c1393a2d686`。业务 ROM SHA256：`5b027d7b590e1d2d720e5160df4fdb64850332d22cc99792722278635ef784f6`。

最终审计修正了分层向量端口的解析：逐 bit 展开后比较连接，而不是把局部向量名称当作全局标量。为绑定修正后的审计器，重新 prepare 到 `a27_checked`；**513 个 staged 文件中 512 个逐字节相同**，唯一差异是补丁 ROM 的绝对路径重定位，两端 ROM 字节相同，所有 RTL、固件、工程和约束均相同。独立比较证据允许复用本轮刚生成的同一个网表／综合报告；原始清单未改写，详情保存在 `verification.json` 的 `synthesis_reuse`。

版本化完整证据：[verification.json](resource_optimization_20261102/verification.json)。本地网表位于 `results/resource_opt_20261102/a27_checked/workstation/Prj1/impl/gwsynthesis/custom_138k_integration.vg`，实现数据库没有加入源码变更。

## 限制与回退

本轮明确选择 logic-only，未提供 PCB 原始接线文件，因此没有选择 CST、没有完成板级引脚／电气核对。保留完整原生时钟计划及定向 CDC 约束，没有降频、扩大 false path 或删去工作站音源、识别、TF、USB、LCD、HDMI 功能来降低资源。

未做 P&R；物理 BSRAM／CLS、拥塞、路由后 setup/hold/recovery/removal、DDR 不透明 IP 内部时钟及新增存储 CDC 的物理路径仍待验证。未产生位流，未操作 SRAM、Flash 或实体板卡，不改变现有部署记录。BLE 实际非静音音频、取消／复位和并发下载行为仍需板上验收。

源码回退基准是 `4e636f37`：恢复本轮原生参数／DDR 适配即可回到原 64 KiB CPU、片内 PCM、BIST 和模型回读策略；不要只混回其中某个 RAM 参数而沿用另一容量的固件 ROM。历史已部署位流及其回退信息仍以架构文档链接的日期记录为准，本轮不推断当前板上身份。
