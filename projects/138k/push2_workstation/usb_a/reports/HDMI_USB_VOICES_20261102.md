# HDMI 右侧 USB 与声部占用显示（2026-11-02）

## 实现范围

USB＋HDMI 组合诊断新增显式 `--usb2-hdmi-status` 配置。右下区域显示 USB 连接状态、已识别设备分类、HS／FS，以及 `VOICES nn / 32` 和声部占用进度条。满载使用黄色，其余占用使用蓝色。USB 状态区分断开、枚举中、连接、错误、无有效状态；断开、错误、过期后清除旧设备名称。

USB 状态来自原输入 owner 的只读 `{gw25k,generic_midi,connected}` 投影及既有链路快照，不以 PHY ready 冒充枚举完成。新增输出不改变 MMIO、18-bit 事件、生命周期、PANIC 或参数权威点。声部数为渲染快照 `shared_render_meta[159:128]` 的置位数，上限 32；不是 held 键数或累计事件数。USB 状态和声部数每帧固定，背压期间双像素流保持不变，变化下一帧显示。

**本配置没有 DSP，声部输入仍来自 D5 的确定性演示快照。** 已实现的是显示消费及进度条，未声称实际演奏声部已在完整工作站或实板验收。完整工作站后续接入须绑定实际活动声部快照，包括释放尾音，不能用诊断事件计数替代。USB 名称是 Push 2／25K／通用 MIDI 分类，未实现任意产品字符串显示。

## 构建来源与回退

入口为原 `build.py --prepare-usb2-soc --usb2-component workstation-hotplug --usb2-hdmi-baseline <已核验D5> --usb2-hdmi-status ...`，参数说明见 [配置文档](../rtl/workstation/USB2_HDMI_DIAGNOSTIC.md)。本次没有生成可部署位流，因此没有新的硬件候选或位流哈希，未复用旧验收身份。

先核验原 D5 manifest／位流／全部输入，再在新候选 `status/` 中生成两份接线适配，原 `hdmi/` 子清单和字节保留。绘制、CDC、超时和帧快照实现位于版本化 `workstation_usb_status_panel.sv`，不由 Python 生成。适配逐项检查唯一锚点，缺失或重复直接失败；根清单记录 before／after 哈希和实际来源，并标记 `hdmi_implementation_byte_identical=false`。退出条件是把 D5 锁定显示装配迁为原生版本化来源。

新增 mailbox 采用原有受约束握手机制，运行时不向 USB／音频反压；源停更 100,000,000 个 100 MHz UI 周期后失效。像素仍经现有 writer 写入同一背缓冲，再由原有发布与 scanout 显示，不增加 DDR 区域、客户端或扫描层。未改变时钟、现有资源、PLL／CDC／STA 门禁。关闭新增选项可恢复原 D5 显示组合来源策略；历史 D5／E5 实物身份及部署记录保持。

## 离线验证

- `sim/test_usb_status_panel.py`：通过。使用锁定字体及实际组合采用的锁定 mailbox，验证设备分类切换、FS 标签、断开／错误清名、源停钟／复位、帧内固定、全 1920×1080 双像素坐标、背压稳定、面板外像素不变、声部 0／1／16／31／32 与半满边界。导出仿真像素预览，16／32 数字与进度条一致。
- `sim/test_workstation_usb2_hdmi.py`：16 项中 15 项通过，桌面 Tk 用例按无显示环境跳过。真实 prepare 覆盖默认与状态栏配置、固件交叉编译、来源哈希、D5 子输入保留、显式适配、约束再生成及锚点漂移拒绝。随后增加并单独复验了实际所选第一方组合的 Icarus 展开，检查通过；加密 vendor／IP 在该展开中作为黑盒，不代表 Gowin 综合通过。
- `sim/test_current_workstation_sources.py`：10 项通过。
- `sim/test_workstation_hdmi_isolation.py`：10 项通过，`test_shared_ddr_ui_pixels` 因本机 Verilator 4.x 不支持 `--binary` 未运行成功。该未完成项保留，未改测试或门禁。
- 原服务适配回归通过 129 个检查。原 native input lint 因同一 Verilator 不支持 `--timing` 未运行成功，未将其计为通过。
- `git diff --check`：通过。

原 Windows 检出的部分冻结输入受换行转换影响，直接运行 baseline 校验会拒绝。验证采用 Git archive 的原始字节临时检出，仅叠加本轮源文件；未修改冻结输入、来源哈希或当前工作区的历史文件。测试工具链使用 WSL Ubuntu 22.04、Icarus Verilog、bare-metal RISC-V GCC 和 newlib 头文件。

未执行 Gowin 综合／P&R、路由后时序／CDC／PLL／资源验收或完整工作站真实声部验收；未访问板卡，未下载 SRAM 或写 Flash。
