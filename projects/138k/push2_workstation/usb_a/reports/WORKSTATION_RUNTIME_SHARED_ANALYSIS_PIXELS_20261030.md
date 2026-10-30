# Native HDMI 共享分析页修复与像素回归（2026-10-30）

native HDMI 原先以 `ENABLE_ANALYSIS=0` 关闭重复本地 FFT，却也将 0 传给两个 dashboard，导致真实频谱、XY／Lissajous 和左右电平没有进入可视像素。本次将计算与渲染参数分离，**真实 minor1 writer→功能 DDR→reader→dashboard 的离线像素回归已通过**。新候选综合、物理资源／布线时序和板上 HDMI 尚未验证。

修复前 v2 事实保留在 [功能保留审计](WORKSTATION_RUNTIME_FEATURE_PRESERVATION_V2_20261030.md)，其候选身份及 VG 均未被本次修复覆盖。新机器证据为 [runtime_shared_analysis_pixels.json](workstation_task_20261030/runtime_shared_analysis_pixels.json)，包含当前源哈希与原始运行证据哈希。

## 原生修改

- `feedback_renderer.v` 追加 `RENDER_ANALYSIS=ENABLE_ANALYSIS`，只用于两路 dashboard 的 analysis-page 参数。追加在原参数表末尾，保持既有位置参数顺序；默认继续继承原 `ENABLE_ANALYSIS` 行为。
- native `workstation_hdmi_display.sv` 显式选择 `ENABLE_ANALYSIS=0, RENDER_ANALYSIS=1, SHARED_EXPORT=0, SHARED_RENDER=1`。本地 FFT 关闭，由独立 `producer/analysis` 提供结果；共享波形、频谱、XY、左右 peak 和元数据进入原有 dashboard。
- reader 源码与 minor1 数据格式没有改动。恢复的可视消费者使其已有 image/spectrum 双银行重新可达。
- HDMI provenance 追加一条可逆 exact edit 并更新当前源哈希。反向恢复仍重现原始父级字节，macro-disabled HDL tokens 仍相等。

## 验证结果

新增 `sim/display/run_workstation_shared_analysis_pixels.py` 使用固定 v2 综合闭包中的原 renderer，仅在临时输出中重命名 module 标识作对照；全部支持输入与 560 项综合来源在运行前后重新校验。当前 renderer 的改动反向还原后必须与该原始 renderer 完全相等。

fixture 向实际 minor1 writer 提供两列已知频谱（左右 224/112 和 32/200）、XY 点 `(40,40)` 与左右 peaks `0x4000/0x2000`。writer 生成真实描述符／payload／提交，功能 DDR 接受 368 次写、365 次读，实际 reader 完成加载。没有直接填充 reader 数组，也没有强制像素或绕过 dashboard。

五路像素比较均使用 `SHARED_RENDER=1, SHARED_EXPORT=0`，隔离已完成快照的可视消费。下表的两种默认比较专指 `RENDER_ANALYSIS` 未显式赋值时对 `ENABLE_ANALYSIS=0/1` 的继承；默认 HDMI provider 的 `SHARED_EXPORT=1` 另外完成 source/token 兼容和完整 elaboration 检查。

| 检查 | 结果 |
|---|---|
| 完整 reader 谱缓存读回 | 512 列全部符合 fixture |
| 完整 reader XY 缓存读回 | 65536 点全部符合 fixture |
| 完整 1920×1080 raster | 1036800 beats／2073600 pixels |
| 修复后的 native 页 vs 原开启页 | 全帧逐像素相等 |
| 新版默认 `ENABLE_ANALYSIS=1` vs 原开启页 | 全帧逐像素相等 |
| 新版默认 `ENABLE_ANALYSIS=0` vs 原关闭页 | 全帧逐像素相等 |
| 频谱左／右／交叠、XY 命中／背景、左右电平与边界的已知色点 | 10 点全部正确 |
| 原关闭配置负对照 | 同样 10 点全部不符，能够暴露原回归 |
| 输出 backpressure | 174960 次 stall，像素及 valid 保持；DDR 另有写／读随机停顿 |

继承的旧 renderer 宽度／timescale 警告按相同 kind 与诊断文字和原版对照记录；没有新增 fixture／renderer 警告，没有组合环。像素 fixture 本身不冒充 FFT 算法验收：实际 2048 点双声道 FFT、两种采样率、波形及 XY 在原 runtime 回归中另行运行。

更新后的 `run_workstation_display_runtime.py` 通过：48 kHz epoch1 与 44.1 kHz epoch2 的峰值 bin 分别左32／右64，6 次发布、9 次提交、128702 次原子 tuple、1024 波形样本、131072 XY 点、1024 谱列、60 次 CDC drop，覆盖 stalled commit tail、partial reader、same-epoch loss、error/zero-epoch 撤销及 raster cache lease。

HDMI 的 Icarus elaboration 现在从当前源根目录执行。旧 cwd 为冻结支持工程时，相对 include 会先命中旧 HDMI 文件，无法证明本次 live HDMI 选择；本次新增 VVP 结果检查拒绝该遮蔽。实际 elaboration 已核对：

| 配置 | local FFT / render / export | 唯一 FFT owner | 两 dashboard | reader banks |
|---|---|---|---|---|
| native | 0 / 1 / 0 | 独立 `producer/analysis` | analysis 均为 1 | 2 |
| 默认 | 1 / 1 / 1 | 本地 `u_analysis` | analysis 均为 1 | 1 |

因此没有为修复显示而复制 FFT。这里是正式 GW5A 原语支持下的源级 elaboration，仍不代替 Gowin 综合后的 feature-preservation 检查。

## 资源与剩余门禁

恢复 minor1 reader 的 image 双银行为 `2*2048*32=131072` logical bits，spectrum 双银行为 `2*512*16=16384` logical bits，共 `147456` bits（18 KiB）。这是已有逻辑缓存重新可观测的预算；实际 BSRAM 数、LUT／寄存器增量、长路径以及 DDR deadline 需要新候选综合和 P&R，不能由逻辑位数直接宣称物理通过。

本阶段没有新综合、P&R、板测、SRAM／Flash 操作或位流。候选 profile 必须重新绑定改变后的源哈希，不能沿用 `custom138k-workstation-v1-41e653fe462e5ea3` 的旧接受身份。回退可撤销显式 runtime provider 选择，保留默认继承行为；不能将修复源码作为旧候选输入静默烧录。

## 复验命令

```sh
python3 projects/138k/push2_workstation/usb_a/sim/display/run_workstation_shared_analysis_pixels.py \
  --project /Users/sphenicidition/.cache/gw138k-task-20261030/runtime-rev4-synthesis-41e653fe/workstation/Prj1 \
  --output /absolute/new/pixel-evidence-directory
python3 projects/138k/push2_workstation/usb_a/sim/display/run_workstation_display_runtime.py \
  --project /Users/sphenicidition/.cache/gw138k-task-20261030/runtime-rev4-synthesis-41e653fe/workstation/Prj1 \
  --output /absolute/new/runtime-evidence-directory
```

本次最终运行目录分别为 `~/.cache/gw138k-task-20261030/runtime-shared-pixels-fix-v3/` 与 `~/.cache/gw138k-task-20261030/runtime-display-render-fix-regression-v3/`，命令与所有输入哈希在各自 `verification.json` 中。实验目录里的编译产物不进入版本控制。

## 独立复验

父级另目录重编译并运行两项回归，全部输入内容哈希、像素与双率指标和子代理证据一致；10 项 accepted／pinned 来源测试通过。记录见 [独立复验证据](workstation_task_20261030/runtime_shared_analysis_pixels_parent.json)。像素回归的身份还包含临时重命名 reference 文件的输出路径，因此父级与子代理 run identity 不同；仅规范化该生成文件路径后，全部输入内容哈希逐项相等。物理门禁与硬件状态仍未提升。
