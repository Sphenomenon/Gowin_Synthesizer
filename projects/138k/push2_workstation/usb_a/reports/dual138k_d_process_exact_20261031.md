# D 模式精确组合运算改写与原采样时刻验证（2026-10-31）

本阶段只改 `rtl/audio/gw138k_event_workstation.sv` 的 `d_process` 函数。原 `core_ce` 调用、PCM 保持、公共参数提交与取消时刻均未移动，没有新增音频流水级。

W9b 实际消费 `src/ae350/gw138k_event_workstation.sv`，候选身份 `custom138k-workstation-w-demo-v1-01aa047a4d25aaf1`。其原文件 SHA256 为 `238d1274e1ad5d724632607374f08a8f03a8fe9d4df26c69613f7dbb26de2646`；改写后维护文件 SHA256 为 `5771d9d60e2e150c27a72e9ad1bf031c7d1faf952bf474d8791237171cb886a2`。完整旧函数由 fixture 保留并在 runner 中锁定身份，未改 frozen baseline。

乘法恒等式为 `(x * (128 + 8*drive)) >>> 7 == (x * (16 + drive)) >>> 4`，两侧都保持 64 位乘积。饱和判断改成高位符号扩展检查；压碎的右移再左移改成12个准确阈值生成的位掩码，`crush==0` 保留全部位。没有近似阈值或新增运算延迟。

验证结果：

- 三个可组合的全域 SMT 证明均为 UNSAT：PCM32×drive7、clipped32×crush7，以及64位饱和判断。
- 实际完整旧／新 SV 函数对444064组合法输入逐项相等，另与独立 Python 整数实现比较；344064组定向（含重复）与100000组固定种子随机。原定向种子中越过PCM32的256次边界实例显式钳回合法域，所有提交输入均在声明域内。
- 四种真实 SV 变异全部因运算结果不等而失败：最低保留位阈值偏1、删除crush0旁路、drive因子偏1、正饱和上限偏1。
- 实际 D-only 完整效果服务2294帧、23条控制事件、两采样率通过；每次真实 `core_ce` 取样都与完整旧函数一致。两例实际DDR配置围栏延迟期间更改CC20／CC21和输入PCM，证明仍使用原先接受的PCM及原 `core_ce` 前已提交的参数，未提前采样参数。
- 本地REC／cue退出检查27读＋27写通过，FFT128 bins保留。

独立复核确认W8／M10b／W9b原函数一致、64位上下文与全部阈值成立。最初 `arithmetic/` 尝试因变异锚点同时匹配10与105失败，已保留日志；`arithmetic-v2/` 精确锚点版本通过。后续真实I2S测试发现的新旧函数共同源切换计数缺陷，单独记录于 source-hold 修复报告，不归因于本次数值改写。

完整输入、工具、证明与结果身份见同名JSON。可重跑命令：

```sh
/Users/sphenicidition/miniforge3/bin/python3 projects/138k/push2_workstation/usb_a/sim/audio/prove_d_process.py --output <新的绝对输出目录>
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_demo_d_only.py --project /Users/sphenicidition/.cache/gw138k-dual-20261031/w-demo-d-v9b/workstation/Prj1 --output <新的绝对输出目录>
```

本阶段是源码与离线功能证明。尚未凭此声称新候选的综合、P&R、资源收益、真实蓝牙入口、HDMI画面或实板DAC验收。撤回时只恢复原 `d_process` 函数并重新生成候选，不能沿用改变后输入的候选身份。
