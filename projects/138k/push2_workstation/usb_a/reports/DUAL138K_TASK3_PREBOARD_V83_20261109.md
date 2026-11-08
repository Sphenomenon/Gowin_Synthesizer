# 双138K上板前收尾：v83检查点

2026-11-09。两板完整来源、综合与消费者审计通过，**尚未达到上板前放行条件**。未操作板卡、SRAM或Flash。完整配置、来源和产物哈希见[JSON记录](DUAL138K_TASK3_PREBOARD_V83_20261109.json)。

| 项目 | M | W |
| --- | --- | --- |
| 完整候选 | `custom138k-workstation-task3-m-preboard-v1-ddb85221f917bdde` | `custom138k-workstation-task3-w-preboard-v1-07ac5ca62eeecf5b` |
| 来源锁／暂存文件／编译输入 | 1124／746／289 | 1178／732／202 |
| 完整综合审计 | 29/29通过 | 27/27通过 |
| 综合 Register／LUT／BSRAM等效 | 58439／70274／212 | 46799／60009／253 |
| 最新物理实现 | v27，`D21109CD` | v28，`D21109DC` |
| 物理 Logic／Register／CLS | 90811／58439／60684 | 81132／46799／56521 |
| 物理 BSRAM／DSP | 253/340／120.5/298 | 287/340／122/298 |
| 结果 | PR0004，2398条未布通网络；无完整STA或位流 | 736.01秒完整布通；PLL／DDR／启动检查通过；setup失败 |

M的TF空槽补充策略消除最终输出router状态对108个实际payload CE的反馈，保留采样和参数边沿。W的三个寄存器只提供普通TX类别偏好，消费者仍复查当前valid/live及紧急优先级；大FIFO改为先比较候选指针、再按write-fire选择，未增加状态、周期或改变容量／CDC。两项均显式选择，只修改当前两个preboard描述符，历史默认和回退保留。

W原消费者失败现已解决：根据本次完整网表定位endpoint `n10383_7`，展开420个任意命名状态位，精确Boolean miter为UNSAT；window与flush的62／487状态函数也通过对应证明。错误active、flight D、CLEAR和watchdog反例被拒绝。M/W共3项实际网表回归、17项当前来源检查通过；两板独立prepare的全部暂存文件与身份一致。综合明确复用逐字相同的编译闭包，审计工具变更单独核对。

W v28全局setup／hold／recovery／removal为 **−2.231／+0.036／+2.371／+0.284 ns**。最差setup为delay DMA `wait_cycles[5]→[30]`，另有generation→completion −2.192 ns、context→BLE result −1.450 ns及raw-store等负路径。显式compute-release setup另有−0.134 ns，不能被全局表掩盖。DDR hold为正不表示整板时序通过。位流仅留作失败候选证据，`.fs` SHA-256为`4e92b5bf53436bb4c4faf97eacdbce97d1a986998e02344de74e06091d699eb6`，**禁止加载**。

下一步围绕实际网络修复。M取消状态的1359扇出已用一条综合属性作离线诊断：12份FF、最大128扇出、增加11寄存器，其D/CE/CLEAR/CLK/INIT逐项相同，五类反例被拒绝；尚未纳入正式候选或P&R。W generation后继值预存的32位归纳证明及六种完整raw-store异步组合通过，也尚未选择。FFT复位初探无寄存器收益，未采用。这些诊断均不能当作最终物理收益。

保持M交互、唯一参数、普通32／矢量8、本地混响与最终输出；W实际CNN、手机接收解码及唯一录音对象。输入未变的滑音／效果、TF、识别、手机及录音证据按哈希复用；手机协同仿真仅覆盖有限注入容量，生产持续音频能力仍关闭。task2、单板、冻结输入和全部失败证据保留。[SRAM清单](DUAL138K_TASK3_SRAM_CHECKLIST_20261108.md)已准备正确目标、连接、加载读回、回退与功能步骤；真实LCD吞吐、DAC延迟和整机演示留待上板阶段。
