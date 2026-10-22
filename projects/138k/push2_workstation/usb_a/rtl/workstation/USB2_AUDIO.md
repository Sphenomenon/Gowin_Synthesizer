# 原生 USB2 到工作站音频组件

`workstation_usb2_audio.sv` 是显式的待集成组件，不是新板顶层或可下载候选。它组合真实 USB2 CPU／输入 owner、现有会话／公共参数／DSP／串行帧交接，以及原 DDR delay DMA；不复制参数权威点，不替换 accepted full83、timing85 或完整 resource-timing 配置。

## 来源与构建

```sh
python3 projects/138k/push2_workstation/usb_a/build.py \
  --prepare-usb2-soc --usb2-firmware-profile workstation \
  --usb2-component workstation-audio --usb2-soc-output /tmp/usb2_audio_new
```

输出目录必须尚不存在。缺少显式业务固件或混用完整工作站 profile 时拒绝准备；`--usb2-full-speed-only` 只选择独立 FS 诊断策略，不更改默认 HS 策略。准备阶段既不综合，也不生成可部署位流。

- 来源策略为 `native_audio_with_selected_locked_resource_dependencies`：14 项 SoC 源、11 项活动 input 源、18 项活动 audio 源、4 项锁定 input 支持源、19 项锁定 audio 支持源，共 66 项编译输入，包文件置首。
- 锁定依赖只从 `baselines/resource_rework_route0` 的受检描述重建；9 项锁定 ROM 数据、8 项活动头文件／scope 数据单独计入 staged 哈希，不当作 RTL 编译。
- 四项锁定音频适配沿用现有 `workstation_resource_timing` 的受检变换：声部计数、services、APB CDC、生命周期合并。变换前后身份与退出计划写入 provenance；没有另写会话、参数或播放实现。输入 FIFO 保留已验证的 input 组件版本，不能声称整套来源与完整资源候选完全相同。
- `component_inputs.json` 绑定源、配置、时钟、固件和全部 staged 数据。缺源、支持包或 ROM 漂移均失败，不回退私有历史暂存。实际选用的音频源／数据另与真实 `--resource-rework --resource-timing --prepare-only` 输出逐字比较。

## 组合接口

| 域 | 频率 | 边界 |
|---|---:|---|
| `clk_cpu` | 48 MHz | 真实业务 CPU、输入 owner、服务／曲谱／播放列表接口、telemetry；外部输入须属于本域或先跨域 |
| `clk_ref` | 50 MHz | APB 主机侧、串口接收、显示观察、已同步的效果投影及 coherent performance 快照 |
| `clk_ulpi` | 60 MHz | 原生 USB3300 Host；不能直接复用旧 FS Host 的时序／管脚 |
| `clk_audio` | 76.8 MHz | 唯一公共参数应用、会话、DSP、PCM、健康统计；每 1,600 拍一个采样周期 |
| `clk_memory` | 100 MHz | delay FIFO 与实际 DMA 的 DDR owner-6 通道 |

组合根必须提供上述真实时钟、对应复位及启动就绪条件。音频复位不重启 USB CPU；`control_reset_n` 是 APB／services 的独立复位输入。DDR 必须具备可服务条件后才启动需要它的音频路径，不能用此组件的端口存在冒充 PLL／CDC／DDR 初始化通过。现有 FIFO 同时使用同步／异步 memory reset 的 lint 警告单列保留，尚无整板恢复／移除时序证明。

`performance_words_o` 从音频域经 448-bit mailbox 整体交到参考域，再由原 input owner 的参考→CPU mailbox 消费；不是将音频总线直接接为 50 MHz 信号。每 4,096 音频拍发送一次；`feedback_drop_o` 是音频域统计。显示、USB PL 和 APB 都只读现有已提交状态，不引入并行参数副本。

delay 采用原 16,384 样本立体声环和 9,600 样本延迟。地址由 `rtl/ddr_address_map.vh` 决定：字节区间 `0x30000000..0x3001ffff`，native 32-bit word 区间 `0x0c000000..0x0c007fff`，每个 256-bit burst 地址步进 8。这里只导出已有 owner-6 通道，不另分配 DDR 区域；最终需接真实仲裁器／控制器并复核其他客户端。取消、旧响应丢弃与 generation marker 沿用原 FIFO／DMA 契约，不让显示或 USB 事务停止采样节拍。

`reference_bck_o/ws_o/din_o/pa_en_o` 是旧 PT8211 参考串行链，不是未知新功放／DAC 的驱动保证。它不产生新板所需 MCLK，不映射 D17／C17，也不将 ULPI DATA7 的 B17 误作功放管脚。必须先确认实际器件、数据格式、时钟、上电／PDN 时序和排线，再接专用输出适配；这些信号目前没有板级 CST。

## 验证与边界

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_audio_sources.py -v
GW138K_USB2_AUDIO_EVIDENCE=/tmp/usb2_audio_evidence_new \
  python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_audio.py -v
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_audio_synthesis.py -v
```

真实 CPU／25K MIDI／PL、会话初始化、参数提交、APB、DSP、参考串行输出与 delay DMA 均进入执行仿真；USB3300 仍是数字模型，DDR 是带背压／延迟的环存储模型，LCD 只有 tile 完成模型。仿真输入先复制并做哈希绑定，执行后核对原件、复制件及组件输入；支持源、头文件、ROM 漂移不得发布 manifest。

音频组件使用独立综合审计 `tools/workstation_usb2_audio_audit.py`：逐字重建 16,384 个 CPU ROM word、检查 top／源策略／输入闭包、交叉核对 XML 和 75 SDPB＋1 SDPX9B＋21 pROM（综合等效 BSRAM 97）、1,194 SSRAM，寄存器预算严格小于 18,432。默认 SoC／input 的原门禁不放宽，旧审计器故意拒绝 audio 身份。上述数字不是 P&R 物理 BSRAM／整板资源或时序通过证明。

详见[本阶段执行与缺口](../../reports/CUSTOM_BOARD_USB2_AUDIO_20261022.md)。真正上板前仍需新板组合根、PLL／IO／完整 CDC、全外设资源与 P&R、USB 电气整改、实际功放和 BLE 排线确认、真实 DDR／LCD／HDMI／TF 等验收。回退保持原显式配置；本组件没有 SRAM／Flash 下载权限，不变更任何部署指针。
