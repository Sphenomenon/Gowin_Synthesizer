# 两个音频晶振的相对频率测量

主板晶振输入：K18（标称 12.288MHz）、J19（标称 16.9344MHz），参考时钟为核心板 V22（标称 50MHz）。V13 拨码低有效复位，正常置 OFF。此诊断仅有输入端口，不输出音频。

每个晶振分别驱动自由运行的 32 位计数器，同域寄存 Gray 编码，通过两级同步送入参考域。预热 128 个参考周期后建立起始快照，每隔 **500,000,000 个参考周期**计算计数差并原子保存。每窗口名义 10 秒，单计数对应 0.1Hz；默认读取六个连续窗口，累计名义 60 秒，平均单计数分辨率约 0.0167Hz。差分按模 2³² 计算，单窗口不能超过源计数器的一次完整回绕。

`f_audio = 源边沿数 × f_reference / 参考周期数`。主机休眠时间、USB 延迟和 GAO 捕获间隔不作为测频时间基准。Gray 总线第一级施加小于最短源周期的传播上限，并仅取消该级异步 hold 关系；第二级及后续路径保留 setup/hold 检查。

这些结果以参考时钟为基准。未用外部频标校准 50MHz 的实际频率，因此不能将小数位数或计数量化分辨率当作绝对准确度，也不测量相位噪声或周期抖动。若今后测得参考时钟为 F，则将当前结果乘以 `F/50,000,000`。

## 离线验证与构建

从工作区根目录执行：

```sh
iverilog -g2012 -s tb_clock_measure -o /tmp/clock_measure.vvp example/CLOCK_MEASURE/rtl/clock_measure.v example/CLOCK_MEASURE/tests/tb_clock_measure.v
vvp /tmp/clock_measure.vvp
python3 example/RTL8723DS/tools/gowin_build.py example/CLOCK_MEASURE/build_gao.tcl
python3 example/RTL8723DS/program_sram.py --manifest example/CLOCK_MEASURE/reports/last_build.json --allow-gao --check-only
```

测试使用独立异步时钟，核对实际边沿计数与精确参考窗口；缩窄计数器覆盖回绕，并覆盖一颗晶振停振、重新启动及复位。构建 UserCode `0x13802420`；保留 JTAG。工具依赖与默认路径同其他独立例程。

## 实板采集

用户授权上板后，先保存当前设备身份，核对 manifest，再仅写 SRAM：

```sh
python3 example/RTL8723DS/program_sram.py --manifest example/CLOCK_MEASURE/reports/last_build.json --allow-gao
python3 example/CLOCK_MEASURE/tools/measure.py --windows 6 --output example/CLOCK_MEASURE/reports/measurement.json
```

采集脚本先核对实板 UserCode，随后读取六个连续有效窗口；签名、窗口长度、窗口连续性或捕获异常都会失败。报告保存原始边沿数、频率比值、以 50MHz 折算的 Hz/ppm 及窗口变化。GAO CSV 是原始捕获，留在本地。

本次测量前设备为左右交替音频 `0x13802401`，测量后从既有 Flash 重新加载并核对身份。未写 Flash。部署和恢复过程记录于 `reports/deployment.json`，测量结果在 `reports/measurement.json`；当前板卡运行状态以相应实测记录为准。

## 本次实测结果（2026-10-24）

六个连续 10 秒窗口，总计 3,000,000,000 个参考周期。以 V22 为 50,000,000Hz 折算：

| 输入 | 标称频率 | 实测折算频率 | 对标称偏差 |
| --- | ---: | ---: | ---: |
| K18 | 12,288,000Hz | 12,287,945.73333Hz | -4.416ppm |
| J19 | 16,934,400Hz | 16,934,270.15000Hz | -7.668ppm |

两个输入各自的六窗口读数跨度均为 0.1Hz；相邻窗口的累计计数端点与窗口边沿数全部一致。B/A 实测比值为 1.3781205189，相对标称比值 1.378125 偏低 3.252ppm；该比值消除了参考频率的共同标度误差，但仍包含计数量化和源频率变化。

参考晶振未外部校准，因此以上 Hz 和对标称 ppm 均为相对 50MHz 假定的结果，不代表绝对频率标定。

测量 SRAM 镜像 UserCode `0x13802420`，SHA256 `0b2b5f9dcde24f8513febe69c1ffb9fe4b36be81545c54afffd0594282814ef5`，setup/hold 违规均为 0；保留参考输入通用时钟布线 PR1014 警告。完成后已从原 Flash 恢复 `0x13802401`，读回 Status `0x00022020`，未写 Flash。报告见 [measurement.json](reports/measurement.json) 与 [deployment.json](reports/deployment.json)。
