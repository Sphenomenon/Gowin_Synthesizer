# 独立 HDMI / 当前 UI 调试配置

这个配置只调试原生工作站的显示链路，不生成完整工作站，也不替换任何 accepted 配置。
显示内容仍是现有 1920×1080 UI：波形、频谱、立体声相位图、效果卡片、文字和运行状态，不是色块测试。

## 数据路径

```text
确定性 PCM / 状态入口（50 MHz，48 kHz sample_valid）
  → 原有采集、FFT、显示快照
  → 原有 display_data_writer
  → basic_pitch_ddr_client_queues / basic_pitch_ddr_arbiter_pipeline
  → 当前 DDR3 平台 / PHY / 外部 DDR
  → display_data_reader → 原有 feedback_renderer / dashboard
  → ddr_frame_writer → 同一个 DDR 管理 → 外部 DDR 帧缓存
  → video_ddr_scanout → 当前 TMDS 编码与板级极性 → HDMI
```

没有把测试图直接接到 TMDS，也没有用片上图像缓存绕过 DDR。
CPU、USB、BLE、CNN、TF、合成器、LCD 不实例化；这不代表从完整工作站删掉这些功能。
没有其他业务的 DDR 竞争，因此本配置通过不等于整机负载下不会闪屏。

## 构建

在仓库根目录运行；输出目录必须是新目录，UserCode 使用新的八位十六进制标识。

```sh
python3 projects/138k/push2_workstation/usb_a/build.py \
  --hdmi-isolation \
  --netlist-dir /home/sphenicidition/Documents/fpga补充文档 \
  --hdmi-output projects/138k/push2_workstation/usb_a/out/hdmi_ui_example \
  --user-code C11027E2 \
  --hdmi-input dynamic
```

默认执行综合和布局布线。加 `--prepare-only` 只准备输入；加 `--synthesis-only` 只综合。
不构建固件，不准备完整工作站，不更新整机 latest 指针，不自动烧写 SRAM 或 Flash。

- `dynamic`：固定、可复现的左右声道三角波；效果开关、顺序和声部状态每秒切换。
- `static`：同样保留周期波形 / FFT 输入，效果和状态固定；不是直流输入或纯色图。
- 输入频率为左 375 Hz、右 750 Hz；复位后相位和场景序列重放。
- `inputs.json` 保存基线、适配、配置和输入哈希；`build_result.json` 保存耗时、工具结果和输出哈希。
- 原生 UI / DDR 来自锁定 `resource_rework_route0` 基线及现有原生时序适配。不能拿 active RTL 中同名但不同版本的文件悄悄替换。
- 本配置独立使用 `boards/custom_138k/hdmi_isolation.cst` 管理 DDR 初始化两个 FF 的位置，不改整机布局约束或 vendor RTL。
- 扫描器 `fetch_busy` 期间暂停接受新的 UI/分析页后台写入，取行结束后恢复。`valid` 和返回 `ready` 同时门控，已进入队列的事务正常排空；仍为 8 额度，不增加扫描 BSRAM。此策略只在独立配置中启用，不隐式修改 accepted/full83 或整机仲裁。
- 写窗口由 `scanout_write_window` 对已校验的显示基线做唯一锚点适配；迁回原生显示组合后退役此适配。迁入整机前须验证音频及其他 DDR 客户端延迟。取行观测与候选证据见 `../../reports/WORKSTATION_HDMI_SCAN_WINDOW_20261028.md`。

## 保留的真实数据入口

`workstation_hdmi_demo.sv` 只是可替换的生产者。
可复用显示核心 `workstation_hdmi_isolation` 与板级探针 `workstation_hdmi_probe_top` 分开。

| 接口 | 时钟域与约定 |
|---|---|
| `sample_data` / `sample_valid` | `clk_50m`；32 bit 定点单声道观察数据，48 kHz 有效脉冲，无背压 |
| `output_pcm` | 同一次有效采样的 `{左 PCM16, 右 PCM16}` |
| `trigger_reference` | 与采样同时有效的 32 bit 波形触发参考 |
| `active_voices` / `status_data` / `effect_mask` / `effect_order` | `clk_50m`；沿用现有 UI 状态快照，不新增业务权威状态 |
| `cpu_req/write/address/data/mask`，`cpu_ready/response/client_rdata` | 输出的 `ui_clk` / `ui_reset_n` 域；原生 DDR 客户端，256 bit 数据、32 bit 字节掩码、29 bit **32-bit word 地址**，不是字节地址 |
| `ui_pending/visible/next_visible/front_base/next_base/frame_commit` | `ui_clk` 域；沿用原有 UI 页面提交协议，地址同为原生 word 地址 |

地址以 `rtl/ddr_address_map.vh` 为唯一分配依据；没有新增或挪动 DDR 分区。
板级探针默认将 CPU 页面客户端置闲，显示当前 RTL dashboard；不会伪造 AE350 软件页面或宣称软件业务已经运行。
要接真实数据，只需替换探针的 `u_input`，保留显示核心和 DDR 数据通路。

## 离线验证

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_hdmi_isolation.py
python3 projects/138k/push2_workstation/usb_a/sim/display/run_scanout.py \
  --project <准备目录> --output <新验证目录> --native-queues --scan-write-window
```

第一项覆盖输入节拍、复位重放、静态 / 动态状态、最小源集和真实 UI 的 DDR 导出 / 回读。
UI 回归逐像素比较 1,036,800 对像素，并覆盖三帧、25 ms 停顿、发布一致性和 FFT 尚未就绪的启动帧。
第二项使用实际队列仲裁器检查 1080p 行扫描、迟到行与迟到帧恢复。
默认采用 8 行缩短回归；追加 `--active-lines 1080 --case stable` 覆盖完整高度的四帧及换帧。
`--write-turnaround-cycles 100` 注入人工读写方向切换开销，不是 DDR 实测参数；用于检查写窗口下仍可连续扫描且后台写入推进。
追加 `--read-latency-cycles 128`，可复现较长响应延迟下的黑行压力场景；当前 8 额度实现会失败，
不是默认通过用例，也不是实板 DDR 延迟的测量。16 额度曾通过此用例，但未改善实板欠载，已撤回。
物理时序、CDC、PLL / serializer 启动检查和上板画面仍是独立阶段。

布局布线后的离线物理检查：

```sh
python3 projects/138k/push2_workstation/usb_a/reports/workstation_hdmi_isolation_20261027/check_physical.py <构建目录>
```

它复用锁定的 DDR reset / 配置、PLL_INIT 与 serializer 启动检查，核对实际时钟清单和 CDC 目标，
并保留全部时序失败。详细候选结果见 `reports/WORKSTATION_HDMI_ISOLATION_20261027.md`。

GAO 使用 `hdmi-isolation-memory-video-counters-64-v1`：`reset_n` 后跟 `debug_status[62:0]`。
探针将已同步到 50 MHz 的诊断值额外寄存一拍；采样深度 1024。

| `debug_status` 位 | 内容 |
|---|---|
| `[62:31]` | 完整 32-bit 欠载行计数，来自 `video_diagnostics[127:96]` |
| `[30:23]` | 已渲染帧计数低 8 bit，来自 `video_diagnostics[71:64]` |
| `[22:15]` | 垂直消隐帧计数低 8 bit，来自 `video_diagnostics[39:32]` |
| `[14:7]` | `memory_flags[7:0]` |
| `[6:1]` | `video_diagnostics[13:8]` |
| `[0]` | `video_diagnostics[64]` |

低 15 bit 保留原 D5 的状态顺序。比较间隔采样的计数增量，不能把启动时的历史欠载标志当成持续欠载。
