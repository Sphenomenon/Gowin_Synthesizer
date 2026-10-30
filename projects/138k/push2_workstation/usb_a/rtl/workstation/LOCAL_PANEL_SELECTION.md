# R00 本地面板选择

`workstation_profile_r00_no_local_panel.sv` 显式包裹既有 R00 provider，在同一宏作用域内定义 `WORKSTATION_NO_LOCAL_PANEL`。HDMI、Push／25K 显示、公共参数和音频组合不变；原 R00、no-CNN、运行时和未指定 profile 的 provider 继续保留本地 LCD。

关闭时不实例化 `workstation_lcd`，其 31.5 MHz PLL、像素复位链、800×480 扫描器和 290-bit 反馈 mailbox 随所属实例一起退役。21 个 LCD 输出位保持低电平，背光关闭；引脚位置和电气约束继续来自已核对的远端 LCD 依据。共享 `push2_surface_pixels` 等 USB 显示源码继续保留。触摸仍未选择，既有 UI 服务的 `input_attached`／`input_valid` 为零。

准备和审计必须将同一个显式 `local_panel_enabled` 布尔值传给下列接口，默认值均为 `True`：

- `workstation_board_peripherals.local_panel_bundle(...)` 同时选择 LCD 源码与其 `LCD_SDC`；关闭时两者均为空，列出唯一退役源和时钟。
- `workstation_board_peripherals.prepare(..., local_panel_enabled=...)` 保留 LCD 引脚约束；返回的 reviewed peripheral provenance 仅表示来源经过核对，实际选择由上述 bundle 单独记录。
- `workstation_custom_clocks.clock_bundle(..., local_panel_enabled=...)` 先验证完整 `clocks.json`，再仅移除 `lcd_pixel31m5` 声明。三种 HDMI 模式的其余时钟不变。
- `workstation_custom_clocks.audit_clocks(..., local_panel_enabled=...)` 使用同一选择核对 SDC；关闭时拒绝残留的 `u_lcd` 层次。
- `workstation_board_peripherals.audit_local_panel(..., local_panel_enabled=...)` 启用时要求 LCD owner、PLL 和反馈 mailbox；关闭时要求层次完全消失且全部 21 位由单个 GND 驱动的 OBUF 输出。

`sim/test_workstation_local_panel.py` 检查四个原 provider 的预处理 token 身份、新 provider 仅替换 LCD 实例、宏作用域、时钟／CDC 精确退役及审计负例。它不执行综合、P&R 或硬件验收；新增 profile、输入锁、完整 prepare、物理时序和板测证据由整机配置接入阶段分别记录。
