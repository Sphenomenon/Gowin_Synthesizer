# 138K 独立板级例程

## 当前自制板：已跑通、待装配

**统一入口为 [CUSTOM_138K/](../projects/138k/example/README.md)**，按 USB HS、HDMI、蓝牙、AK4493／功放四类整理源码、已验证候选、构建／检查命令及装配边界。

`CUSTOM_138K` 是仓库内相对链接，实际目录为 `projects/138k/example/`；各模块的源码入口也使用相对链接，指向唯一受版本管理的实现，不复制另一套驱动。克隆仓库即可使用，不依赖本机缓存。

## 原始板级例程与历史证据

适用于 Mega_138K 本版主板及其子板，独立于 `projects/138k/` 的完整工作站构建；管脚和验收结果以各例程文档为准。

- [RGB LCD 显示测试](LCD_RGB/README.md)：正点原子 4.3 inch /800×480，含图案、固定白场、接线表与仿真。SRAM 校验通过；实体仅见微弱灰绿画面，RGB 位权转接待完成。
- [RTL8723DS：BLE 与 Wi-Fi 扫描](RTL8723DS/README.md)：BLE 广播、GATT 读/通知及 SDIO 识别已实板验证；板上 Wi-Fi 被动扫描已收到信标。尚未实现连接路由器或网络通信。
- [AK4493 音频与功放测试](AK4493_AMP/README.md)：48kHz /32 位 I²S、左右测试音及 JTAG 数字检查；修焊后 CN 扬声器已发声。左右交替镜像已固化，3.5mm 仅右耳有声、噗嗤与断音仍待定位。

- [双音频晶振测频](CLOCK_MEASURE/README.md)：以核心板 50MHz 为参考，六个 10 秒窗口实测 K18 / J19 的频率比值及折算频率；测后恢复左右交替音频，未写 Flash。
- [主板与子板原理图说明](../Hardware/原理图解析.md)：本版底板、音频板、无线板的信号与电源关系，含双晶振实测数据。

## 克隆后使用

从仓库根目录按各例程 README 构建和仿真。依赖 Python 3、Icarus Verilog、Gowin EDA；默认 EDA 路径针对本机 macOS，移植到其他安装位置时需核对脚本内的工具/IP 路径。构建与仿真不会授权上板或写 Flash。

历史报告中的绝对路径、构建目录、位流 SHA256 与 UserCode 保留原始证据。`builds/`、自动生成的适配 RTL、仿真产物和 JTAG/UART 原始捕获不入库，新克隆需要重新构建并使用新 manifest；不能直接依赖历史报告中的本机位流路径。BLE/Wi-Fi 厂商输入及原始许可证、清单按字节保留。

导入范围与文件哈希见 [SOURCE_IMPORT.json](SOURCE_IMPORT.json)。
