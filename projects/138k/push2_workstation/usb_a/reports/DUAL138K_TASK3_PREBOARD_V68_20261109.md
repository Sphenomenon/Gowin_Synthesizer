# 双 138K v68：reader 结构修复及可复现综合检查点

两板完整综合审计通过，独立 prepare 逐文件复现；最终配对位流仍未放行。M 保留普通 32／矢量 8 声部、唯一参数应用点、本地混响和最终输出，W 保留实际 CNN、手机接收解码与唯一录音对象。没有操作板卡、SRAM 或 Flash；task2、单板和冻结回退保留。完整身份与证据哈希见同名 [JSON](DUAL138K_TASK3_PREBOARD_V68_20261109.json)。

| 项目 | M | W |
| --- | --- | --- |
| 显式配置 | `custom138k-workstation-task3-m-preboard-v1` | `custom138k-workstation-task3-w-preboard-v1` |
| 候选身份后缀 | `a62c33bbe455c4a1` | `a19f80a4e14a6b0b` |
| 配置 SHA-256 | `eec71ccb0f28aa1d5524c9f5425e28db6fe5639aa69662098b718288f49e8bf3` | `66c7e48866a76abc5b46aff1893f81aa6e5b905c104e8a7c7378fc88f8855ed5` |
| 来源锁／实际暂存文件 | 1097／740 | 1151／726 |
| 完整综合审计 | **29/29** | **27/27** |
| 综合 Register／LUT／ALU | 58446／70767／18339 | 46793／59031／15869 |
| 综合 BSRAM 等效值 | 212，非物理计数 | 253，非物理计数 |
| 独立 prepare | 全部暂存文件与候选身份一致 | 全部暂存文件与候选身份一致 |

## 本次修复及验证

M 的显示 reader 在 `STORE_PAYLOAD` 期间复用已经保持的 256 位 DDR 响应，去掉冗余 payload 暂存，不改变请求、响应、seqlock、取消或对外输出边沿。只在显式 M preboard 配置选择，历史 reader 原字节保留；适配清单有父／子哈希、唯一锚点、严格逆变换及退出条件。

实际 legacy／minor1 reader 两套回归的全部 **23 个输出逐拍相等**。完整 M 网表打包变化影响的 **119 个逻辑状态**通过条件对应检查，**23 项归纳不变量、28 个 RAM 地址位方程**通过，14 个相关源码 owner 字节一致，遗漏位等反例被拒绝。这包含显式命名状态及 RAM 输出对应条件，未声称整机顺序等价或 RAM 状态归纳证明。

新综合把 TF release 提升为顶层网络别名，旧物理准备因此拒绝。准备器现在按实际连线解析别名，同时严格要求原 owner 的唯一发布寄存器及原时钟；891 个 CLEAR、选定 PRESET 和四个 RAM RESET 的检查保留。新旧实际 M 网表均通过针对性回归，错误时钟、替换 owner、断开输入和重复约束被拒绝。新增负例夹具第一次因缺少其 scope 映射报错，补齐后通过；两份日志均保留。

`test_current_workstation_sources.py` **17/17** 通过。相对 v65，M 的全部编译输入只改变 reader，另加两份非编译适配文件；W 的全部暂存字节未变。复用本轮 M v66 与未变 W 的有效综合，没有编辑 VG；v68 对两板重新执行完整审计。滑音／效果、TF、识别、录音和下载既有回归按未变输入复用，原验证范围不扩大。W 的目录相关固件诊断元数据字节不同，实际安装输入、固件及候选身份均一致。

## 物理状态与未完成门禁

W v21 `D21108D5` 已完成 P2R0：BSRAM **287/340**、CLS **56175/69120**；setup／hold／recovery／removal 为 **−7.651／+0.139／+1.457／+0.293 ns**。失败位流 SHA-256 为 `bf7b06eca333f3899401e434fb317754a74b4e40c7591cd74483f5908e042c89`，**不得加载**。详细路径显示 DMA state 到数据 mux 的单段线延迟 10.718 ns、FIFO 返回线 4.788 ns，部分控制布局未改善完整数据路径。

M v19 `D21108C5` 在路由阶段达到 1800 秒监督上限，原输入不变，无最终 STA 或有效位流；保留为超时证据。M v21 `D21109C7` 使用新 reader 网表进行完整 P2R0。W v22 `D21109D6` 对完整 delay DMA／FIFO 的 2241 个实际对象作一次有界局部布局实验。报告封存时两次运行仍在路由；W 对三块 FIFO RAM 报 CT1094 区域约束告警，必须核对最终位置和时序。两次运行的原始开始回执均复制成不可变快照，结束回执另行保存。

这些物理实验尚未形成最终配对候选。仍须完成 M 布通及 STA、W setup、两板完整资源／PLL／CDC 检查，并将实际有效的布局接入维护的物理准备入口。不能把缓存实验脚本作为唯一生产来源。DDR hold 在 W v19／v21 的完整 STA 中已转正，M 及最终两板仍以各自最终报告为准。

## 复现与后续

缓存根为 `/Users/sphenicidition/.cache/gw138k-task3-20261108`；准备目录 `{m,w}-preboard-prepare-v68{,-repro}`，完整审计 `diagnosis/{m,w}-audit-v68.json`，逐文件比较 `diagnosis/reproduction-v68.json`。继续使用现有入口，例如在 `usb_a/` 下：

```sh
python3 build.py --prepare-custom-board \
  --workstation-profile custom138k-workstation-task3-m-preboard-v1 \
  --custom-board-output /absolute/new/m-output \
  --netlist-dir /Users/sphenicidition/.cache/gw138k-task3-20261103/locked-netlists \
  --riscv-prefix /Users/sphenicidition/.local/opt/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf
```

W 使用其显式 profile 和独立新目录。原 v65 JSON 保持提交时原字节；其中运行中回执的旧哈希与字节相同的开始快照之间的定位修正在本次 JSON 独立登记，不刷新历史哈希。

[SRAM 清单](DUAL138K_TASK3_SRAM_CHECKLIST_20261108.md)继续准备正确目标板、连接、逐板加载与读回、回退及功能验证。当前没有可加载的最终配对位流。真实 LCD 吞吐、DAC 延迟和整机演示留待上板验收。
