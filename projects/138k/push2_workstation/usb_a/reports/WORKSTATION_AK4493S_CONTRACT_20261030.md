# AK4493S 双率接口：正确型号手册复核

日期：2026-10-30。已读取本机 `Downloads/ak4493seq-en-datasheet-myakm.pdf`，其正文为 **AK4493S，211100143-E-02，2022/03，104 页**，SHA256 为 `a8957fd0a955d30d5d80bce1bedb5ecdd27693e8ccb1572f37920888dcb734c7`。它补充了历史 AK4493 2017 手册的型号缺口，不改写历史记录，也不证明实体芯片、排线或模拟电路已验收。原 PDF 留在本机，不把第三方全文加入源码。

机器记录：[ak4493s_contract.json](workstation_task_20261030/ak4493s_contract.json)。下列页码同时是 PDF 页序与正文页码；关键表格另经 PNG 渲染复核。

## 时钟与数据格式

| 边界 | 手册依据 | 当前独立 serializer／probe 的含义 |
|---|---|---|
| 两路 MCLK | p.39 Table 6；p.40 Table 9 | 48 kHz／12.288 MHz／256fs，以及 44.1 kHz／16.9344 MHz／384fs，均在 pin-control 支持表内 |
| 自动检测的性能限制 | p.40 Table 10 | ACKS=H、44.1 kHz、384fs 时 DR/SNR 约 120 dB，比该表 manual 或 512/768fs 的 123 dB 低约 3 dB；不能称两模式模拟性能完全相同 |
| I2S 格式 | p.45；p.46 Table 22 Mode 7 | DIF2:0=111 是 32-bit I2S，LRCK=L 为左、H 为右，BICK 至少 64fs；按 BICK 上升沿收数。当前 PCM16 位于每个 32-bit slot 的高位，其余低位补零，保留一个 I2S 延迟位 |
| 同步与占空比 | p.26、p.27、p.39 | MCLK/BICK/LRCK 同源同步，MCLK 相位无严格要求。MCLK duty 40–60%、高低至少 9.05 ns；LRCK duty 45–55%；BICK 高低至少 9 ns |
| 引脚建立／保持 | p.27 Note 37；p.31 Fig.14 | LRCK 边沿距 BICK 上升沿两侧至少 5 ns，SDATA setup/hold 各 5 ns；不能同沿改变 LRCK。当前 RTL 在 BICK 下降沿更新 LRCK/SDATA，布线后 IO 偏斜及子板端电气仍需另测 |

当前名义 BICK 为 48k 的 3.072 MHz 与 44.1k 的 2.8224 MHz（均 64fs），半周期分别为 162.7604 ns／177.1542 ns。MCLK 半周期分别为 40.6901 ns／29.5257 ns。这些是 RTL 分频预算，不冒充 DAC 焊盘实测。

## DAC 复位和静音

**p.26 Note 36 要求改变 MCLK 频率时先保持 PDN=L，或在 register 模式令 RSTN=0。** 目前采用 pin-control，故必须使用实体 PDN。`workstation_sample_rate_switch` 在完整帧 quiescence 后同时请求本地域复位和 DCS 停止；停止低电平由常开域确认，再选择新源、完成资格窗口，最后释放本地三边沿复位。serializer 的 `pdn_no` 由本地域复位直接门控，整个停钟／换源／资格阶段均低，不能用 SMUTE 替代这条复位要求。

p.29、p.74 要求可靠复位的 PDN 低脉宽超过 150 ns。serializer 默认 PDN 保持 **4 个完整帧**，即约 83.333 µs／90.703 µs；这里的参数单位不是 MCLK cycles。PDN 释放后继续零数据至 startup=1028 帧，至少另等 1024 帧，即约 21.333 ms／23.220 ms。p.74 Fig.58 的 LDOE=H 内部启动最坏 2 ms，名义等待有余量；电源上电顺序和实体 PDN/MCLK 关系仍须物理核实。

p.72 Fig.57 明确 **SMUTE 是数字软静音**，衰减有过渡时间，不能把 pin=H 视作即时模拟隔离。p.74 Fig.58 Note 5 还指出 PDN 边沿即使输入零数据也可能出现 click；Note 6 建议在有影响时外部静音模拟输出。独立探针固定 SMUTE=H、SDATA=0，仅作数字实验，**不据此承诺模拟无声、无爆音、模拟音质或功放正常**。完整产品的无 click 策略和模拟路径验收仍未完成。

## 锁定功放网表交叉核对

`功放.tel` SHA256 `b0ae6b2be4b59a60244a98ea870fc701bb4e8186123b7cb54cf79e22ea628b75`，由已有严格 `Netlist` 解析器读取，原始字节未修改。U1 的封装条目未声明具体型号，因此型号来源仍是正确手册及既有电路资料，不能由此网表单独证明实装 AK4493S。

| U1 pin | 网表连接 | p.7–8／p.46／p.55 对应设置 |
|---|---|---|
| 10／11／12 | 直接接 DVDD_3V3 | DIF0／1／2 全高，Mode 7 |
| 13 | DVDD_3V3 | PSN=H，pin-control |
| 14 | GND | INV=L，左右声道不反相 |
| 15 | DVDD_3V3 | DEM0=H，去加重关闭 |
| 16 | DVDD_3V3 | LDOE=H；U1.1 单独接 C28/C29，未误接 3.3 V |
| 17 | R10=0Ω 接 DVDD_3V3，另经 R9=1MΩ 接 GND | ACKS=H，自动时钟检测；因此应保留上述 44.1k 性能限制 |
| 44／48 | AVDD_3V3／DVDD_3V3，经 R6=0Ω 相连 | 名义 MCLK 与其他数字接口均属 3.3 V 供电；没有实测电压结论 |

该复核不重新采用独立 pinout-only 的同序排线假设；原生装配和探针继续使用已核对的主板 FPC2.n→子板 FPC1.(25−n) 位置证据。子板网名中的历史球位不是 FPGA 当前约束。SSLOW/SD/SLOW 选择由 p.55 Table 25 定义，探针没有新增驱动这三个脚，也不据此报告滤波器状态已确认。

本阶段只完成型号正确的文献与源码约束复核。F03／A06／A07 整项仍未完成；两路参考的当前实测、DCS 事务实板记录、DAC 焊盘时序、模拟输出和最终工作站集成须分别提供证据。没有新增 SRAM 或 Flash 操作。
