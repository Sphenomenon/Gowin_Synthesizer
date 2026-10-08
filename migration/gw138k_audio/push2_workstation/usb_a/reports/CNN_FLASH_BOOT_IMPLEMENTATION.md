# CNN Flash 启动实现记录

模型分区已在实体板写入并逐字节验证。完整工作站自动装载验收尚在进行；当前板上和 LATEST 仍为已验证 full85。

| 项目 | 结果 |
|---|---|
| 模型 | 52,239×16 bit；载荷 104,478 字节；CRC32 AF01A61B |
| Flash 分区 | 0x600000；BPF1 头 32 字节；总长 104,510 字节 |
| direct 独立仿真 | 19 SPI/DDR + 7 主机拒绝用例 PASS |
| 兼容输入独立仿真 | 16 用例 PASS，含完整模型、实际115200时序、第二遍内容变化 |
| 原 CNN A/B | 3 帧、六层哈希和谱面结果 PASS |
| 0x96 临时 SRAM 探针 | 实际 Flash 全模型读取、本地 RAM CRC PASS；非 DDR 证明 |
| 0x98 临时 SRAM 探针 | 实际 Flash→内部115200→原解析器、本地 RAM CRC PASS；非 DDR 证明 |
| 完整 0x95 | 配置从 Flash 正常加载，clk50 PASS，DDR 模型回读停滞；已恢复 full85 |
| 完整 0x97 | CNN/解析器/DDR/固件源文件与 full85 相同；SYN BSRAM216；P&R 进行中 |
| 回退 full85 | CPU/audio/DDR/modelE、Push屏幕帧、三音并发、矢量立体声、静音、松键/Panic PASS |

默认 serial 传输由 HDL 从 Flash 读取，片内产生 BPN1 数据；无需 PC 上传、TF 模型文件或参数 ROM。模型先完整预校验，随后逐字读取并通过原模型装载器写入 DDR，原装载器完成独立 DDR 回读 CRC 才就绪。

完整工作站整体静态时序仍有原有音频/USB/跨域欠账；clk50 收敛不能代表全板时序收敛。没有执行物理断电/上电或模拟 DAC、HDMI、整曲 CNN 人工验收。

详细分区、重建、回退命令见 `docs/CNN_FLASH_BOOT.md`；原始证据路径、版本、失败尝试见 `reports/CNN_FLASH_BOOT_IMPLEMENTATION.json`。
