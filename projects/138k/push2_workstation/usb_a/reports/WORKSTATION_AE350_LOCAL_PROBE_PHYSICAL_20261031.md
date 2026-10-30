# C06 本地存储探针物理阶段

独立探针 `custom138k-ae350-local-memory-probe-C21031C7` 已实际完成综合、P&R 和 routed timing，113.072 秒，原始输入保持。位流 `ao_0.fs` SHA256 为 `80761cdbb39980e313f830f955ef54c17335bead5a77fd3e32db7795cb4e307b`；头部器件、UserCode、SecurityBit=OFF 与 GAOCRC 经重新核对。它不含完整工作站、DDR 控制器、USB、HDMI 或 BLE。

前四次结果保留：v1 include 目录格式错误；v2 未使用的 GAO wire 别名被优化；v3／v4 均有一条 GAO 未布通网络。维护源码修正 include 为工程根目录、保留实际顶层 512-bit FF，并采用 B7 已使用的 GAO Bus／core Expressions／二进制 GAO_ID 格式，采集深度为 128。v5 同时修改了这几项 GAO 配置，不把路由成功归因于其中单一字段；没有放宽标称时钟、修改 frozen IP 或新增时序例外。

报告的最小 setup／hold／recovery／removal 裕量分别为 +5.988／+0.240／+6.769／+0.395 ns；最小已报告脉宽裕量 +3.932 ns，setup／hold 违规端点均为零。保留 `clk_50m_d` generic-routing 警告，并按实际布线报告评估。可见 PLL 仍为 100 MHz core／50 MHz bus；UART 请求／应答、四个 flags、upper／unmapped 两级同步链及四级 core reset 连接在实际 VG 中复核。硬核内部不可见路径不据此宣称完整独立验证。

主设计表为 CLS 5,646／69,120、BSRAM 40／340；独立 GAO 表另列 Logic 877、Register 2,264、BSRAM 30。该探针的表项不能用作完整工作站资源预算。厂商输出初始化及 frozen PLL 截位警告保留；UART 具有显式复位，未依赖被忽略的输出声明初始化。

主树七项实际回归通过，含正式 loader、32 KiB 非零 payload／CRC、ILM/DLM pattern、别名负控、可选 CSR trap、UART 异步快照／超时、DAC 固定安全输出与 GAO 配置结构。冷镜像／ILM 仍为 36,368／35,760 B，保守栈 96 B，固件 ELF／BIN／ROM 与准备阶段相同。Cache 仍关闭；PMA 配置读数缺少地址范围时不能当作 APB／DMA 属性证明。

机器记录见 [ae350_local_probe_physical_v5.json](workstation_task_20261030/ae350_local_probe_physical_v5.json)。父级包 `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-local-probe-main-physical-parent-v5` 保存源码快照、五次输入／产物及七项回归引用，绑定 332 项外部文件，seal SHA256 `b6a5c29058751e7c672cf8a72c2ac98b61899c9196a850424151773f27074f16`，`verify.py` 可只读复核。

本记录截至物理产物校验，不包含 SRAM／硬件验收。用户已授权后续探针操作；执行前仍须独立读当前板卡身份、核对该位流并记录 Program/Verify、UART／GAO 和原 Flash 重载读回。Flash 不写入，旧 C11028E5 回退身份需重新实读确认。
