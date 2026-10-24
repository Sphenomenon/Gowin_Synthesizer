# 固定白场与 JTAG 扫描诊断

用于排查“背光已亮但黑屏”。独立工程，保留主工程的 31.5MHz、976×528 扫描和引脚约束，UserCode `0x13802412`。只下载 SRAM，不写 Flash。

RGB565 输出始终为 `16'hffff`（包括消隐和复位期间），DE 决定有效区域；HS/VS、背光和复位行为与主工程一致。固定颜色信号不需要随像素翻转。按当前同号直连，屏端最大值仍只有 RGB888 的 31/63/31，不能代替位权转接。

GAO 在 50MHz 域采集 192 位 `lcd_debug`：低字依次为 `LCD1` 签名、参考计数器、Gray 编码像素计数器、Gray 编码帧计数器、Gray 编码有效像素计数器、状态。像素域 Gray 计数器经过两级同步，主机解码；跨域首级最大延迟约束 25ns，小于 31.746ns 像素周期。状态低 8 位依次为 PLL 锁定、外部复位释放、扫描复位释放、背光、曾出现 DE、曾出现低 HS、曾出现低 VS、曾在 DE 期间输出白色。后三类观察为复位后粘滞状态。

两次捕获以 50MHz 参考计数差计算内部像素频率、帧频及有效像素速率。在线读取不能证明物理引脚、电源、排线、LCD 复位或实际显示正常，也不能检测固定白色 RGB 脚外部断线。

```sh
iverilog -g2012 -Wall -s tb_lcd_top -o /private/tmp/lcd-white-top.vvp example/LCD_RGB/diagnostic_white/rtl/lcd_rgb_top.v example/LCD_RGB/diagnostic_white/rtl/lcd_scan.v example/LCD_RGB/diagnostic_white/tests/tb_lcd_top.v
vvp /private/tmp/lcd-white-top.vvp
python3 example/RTL8723DS/tools/gowin_build.py example/LCD_RGB/diagnostic_white/build_gao.tcl
python3 example/RTL8723DS/program_sram.py --manifest example/LCD_RGB/diagnostic_white/reports/last_build.json --allow-gao --check-only
python3 example/RTL8723DS/program_sram.py --manifest example/LCD_RGB/diagnostic_white/reports/last_build.json --allow-gao
python3 example/LCD_RGB/diagnostic_white/tests/capture_status.py
```

构建必须 setup/hold 违例均为零，下载脚本核对位流哈希及 GAO CRC。`reports/last_capture.json` 保存最近一次内部诊断结果。顶层仿真覆盖三次完整首帧、PCLK 采样边沿、固定 RGB、DE/同步时序、外部复位和 PLL 失锁恢复；PLL 使用行为桩。

## 本次结果

2026-10-24 12:51：构建、三帧顶层仿真、SRAM 下载和读回校验均通过，UserCode `0x13802412`。GAO 捕获通过，内部像素频率 31.500000MHz、状态低字节 `0xff`。用户反馈固定白场能看到微弱灰绿画面，符合直连低位 RGB 的表现。下一步需要 RGB 位权转接，当前尚未通过正常亮度和颜色测试。详见 [verification.json](reports/verification.json)。
