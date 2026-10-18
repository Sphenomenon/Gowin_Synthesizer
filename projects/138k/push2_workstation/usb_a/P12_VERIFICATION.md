# P12 共享 DDR 显示数据：阶段 3

状态：阶段 3 的 HDMI DDR reader 已完成 RTL、仿真、综合/布局布线和 SRAM 下载；实体 HDMI、Push、耳机和交互回归等待用户对当前 SRAM 版本验收。Push 屏幕仍使用原 USB-A 协议和快照路径，阶段 4 尚未开始。

本阶段在 P11 的版本化双 bank 数据布局上增加 HDMI reader。HDMI 仍保留原 RGB565 framebuffer 和 scanout，只把 waveform、李萨如位图、频谱列和效果元数据的来源切换为共享 DDR 紧凑块。没有复制 framebuffer，也没有修改音频采样、FFT、P10 串联效果链、P2 低音或 Push USB-A 协议。

## 构建与接口

构建目录：`results/build_20260915_000749_501731`。overlay 仍只来自 `rtl/display_data/` 和 `display_data_layout_pkg.svh`；P10/P11 结果目录及冻结输入未改。受保护的 P10 位流 SHA256 仍为 `dd80b9009241836b3266b6407aa1a36cf8973d0b660d239e2e0f1fe8e0e4f793`。

`u_video/u_data_reader` 在 DDR UI 100 MHz 域运行，一次只保留一个读请求。它读取全局提交记录、目标 bank 头、四个 64 B 描述符、waveform/bitmap/spectrum/metadata payload，最后再次读取 bank 头；任何 magic、版本、bank、sequence、偶数 generation、地址或长度不符都会丢弃本次加载并保留上一帧缓存。payload 进入三个自然宽度缓存：512×32 位 waveform、2048×32 位 bitmap、512×16 位 spectrum，合计约 90 Kbit，综合映射为 6 个 BSRAM。

HDMI renderer 的 `SHARED_RENDER=1` 路径只从上述缓存取得三种图和 metadata；本地 analysis RAM 仍由同一 renderer 保留用于共享 DDR 导出。提交前后的 seqlock 校验保证 HDMI 不读取半帧新数据和半帧旧数据。共享读请求复用原 DDR 仲裁器的 BIST owner 编码，但只在 BIST 完成后启用，因此没有扩大原有 read-tag 位宽；scanout 仍拥有更高优先级，writer/CPU 轮转保持原接口。

## 仿真

以下结果均为 Verilator/稀疏 DDR 模型，不是实体 HDMI 或实体 DDR 读回：

- `results/build_20260914_234733_721248/p11_shared_000712_696291`：reader 检查 descriptor 长度、版本、延迟响应、背压、故意破坏的末尾 bank 头重试，以及 waveform/image/spectrum/metadata 缓存一致性，通过。
- `results/build_20260914_234733_721248/p11_shared_000712_700712`：HDMI 共享读取连续 3 帧，覆盖 25 ms DDR 停顿和提交前后重载；与 P10 本地 renderer 的首 3 帧逐像素比较，1,036,800 对像素对完全一致；启动时无有效 analysis 时 bitmap/columns 为零且长度为零。
- `results/build_20260915_000749_501731/p11_shared_002340_187246`：reader、共享 writer、frame writer、显示仲裁和 framebuffer/P5 提交集成，通过 1,609,710 个 UI 周期（16.09710 ms）、365 次共享写、365 次一致读和 framebuffer/P5 写入检查；scan arbitration/tag 无错。

这些仿真证明协议字段、frame sequence、双 bank 提交和 HDMI/P11 读取路径一致；没有把它们写成实体屏幕验收，也没有声称 Push 已读取 DDR。

## 综合、布局布线与审计

最终 P&R 报告：`results/build_20260915_000749_501731/Prj1/impl/pnr/Prj1.tr`。

| 项目 | 结果 |
|---|---:|
| setup 违例端点 | 0 |
| hold 违例端点 | 0 |
| 最差已报告 slack | +0.002 ns |
| Logic | 33,502 |
| Register | 24,893 |
| BSRAM | 254 |
| DSP | 42.5 |

分项证据 `p12_routed_summary.json` 显示音频 48 kHz、原有音频/视频/USB 时钟和音频/USB 路由检查通过；`u_data_writer`、`u_write_bridge`、`u_data_reader` 的寄存器均在 ddr_ui100，异步复位连接与既有 frame writer 一致。`p12_usb_routed_summary.json` 的 USB PLL、事件 Gray CDC、held snapshot CDC、PHY 阶段、USB-A pad 和 setup/hold 检查通过。

完整旧审计仍不能记为通过：`check_existing.log` 保留了历史 DDR reset 证据引用路径缺失，以及 `u_managed/effect_mask_sync_[0..2]_s0/RESET` 三个 stopped-clock reset 覆盖缺口。新增 reader 的分项检查没有放宽、替代或伪造这个既有缺口。

## SRAM 与实体验收边界

P12 位流：

- 文件：`results/build_20260915_000749_501731/Prj1/impl/pnr/Prj1.fs`
- SHA256：`baa44a8e57072478d66847cdaef38dea7c754c47a5f45b3ebb43289c34f658e9`
- UserCode：`0x0000C8A1`
- SRAM 记录：`../results/sram_20260915_002533_851798/result.json`
- 写前 UserCode：`0x0000D767`（P11）
- 写后 UserCode：`0x0000C8A1`（P12）
- Flash：未写

当前板上运行的是 P12 SRAM 版本，尚未把以下项目记为通过：HDMI 三图实际画面、效果卡片顺序/箭头/动画、Push 屏幕和灯光、耳机声音、P10 串行效果链、P2 低音以及真实交互延迟。用户确认后再建立 P12 实体验收记录；若需回退，P11 位流仍在 `build_20260914_190033_599011`，P10 位流保持受保护。

阶段 4 将只增加 Push 对同一 descriptor 的摘要读取和低分辨率数据使用，不改变 USB-A 线协议；未来自制显示屏也可复用本阶段 ABI，暂不新增外部传输层。
