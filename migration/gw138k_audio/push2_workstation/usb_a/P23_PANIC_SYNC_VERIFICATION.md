# P23 PANIC 同步清理验证

2026-09-16：源码审计、定向仿真、完整构建、路由分项审计及 SRAM 下载/读回已完成。P23 UserCode 为 `0x00000023`，Flash 未写。用户按本轮清单检查后回复“没问题。继续下一个项目”，确认 PANIC、电脑键盘、Push、连续压力、屏幕/灯光、HDMI、耳机和效果链均正常，P23 实体验收通过。

## 行为与定向验证

P23 将 CC120 定义为硬 PANIC，CC123 保留正常 RELEASE。正式构建上的 `p23_panic_143926_476411/verification.json` 通过：

- 音频：CC123 不改变 PANIC 世代；CC120 立即清 held、allocated、active、包络可达状态和效果尾音；效果 mask/order 不变；新 Note On 可重新启动；48 kHz sample 间隔保持 1600 个 76.8 MHz 周期。
- Push：本地 held、last note、last velocity、屏幕快照和 PANIC 前待发事件清零；CC27/29 与断开路径发送 CC120。
- AE350 UI：世代变化清 gate，仍按住的触摸必须先松开。
- 电脑窗口：世代变化取消长按重复和延迟松键，清本地 held，并保留物理键锁存直到真实 KeyRelease，防止操作系统重复 KeyPress 重新触发。

P22 Tk 长按回归在 P23 主机脚本修改后通过 11 项检查，记录为准备构建中的 `p22_keyboard_20260916_141041_742276`。P23 最终面积优化只修改 FPGA 声部内部不可达状态和效果控制清理，没有再改主机脚本。没有重复运行无关 HDMI/DDR 全量仿真。

## 最终构建

正式构建目录：`results/build_20260916_143026_789005`。

| 项目 | P22 | P23 |
|---|---:|---:|
| setup 违例 | 0 | 0 |
| hold 违例 | 0 | 0 |
| 最差 setup slack | +0.010 ns | +0.087 ns |
| Logic | 33830 | 34848 |
| Register | 25192 | 25381 |
| BSRAM | 253 | 253 |
| DSP | 43.5 | 43.5 |

Gowin 完整综合和布局布线返回 0，构建器报告生产输入未在运行中变化。位流 SHA256 为 `8bd54510c9e0637420a49c9e4235c27659a9e48417a97eec35137e322dda25b6`，header CheckSum 为 `0x8B81`，UserCode 为 `0x00000023`。

第一次完整 P23 构建 `build_20260916_141304_210349` 功能和时序均通过，但因逐位清空不可达的 32 声部包络数组，资源为 Logic 36508、Register 25623。该中间位流未下载。最终版以分配掩码隔离旧数组，新声部装载前重写对应项；Logic 回落 1660，BSRAM/DSP 不变。

完整 `usb_a_audit.json` **未通过**，原因仍且只记录为旧缺口：

```text
u_managed/effect_mask_sync_0_s0/RESET
u_managed/effect_mask_sync_1_s0/RESET
u_managed/effect_mask_sync_2_s0/RESET
```

该审计在旧 DDR/video 检查处提前结束，不能记为完整通过。独立音频 PLL/mailbox routed audit `p23_audio_routed_audit.json` 通过，PLL_INIT 最长传播 9.711 ns；这项局部结果不覆盖上述失败。

## SRAM 下载与当前边界

下载记录：`../results/sram_20260916_144151_621500/result.json`。实际写前读回 P22 `0x00000022`，随后只执行 SRAM 操作 2，再读回 P23 `0x00000023`；before/sram/after 均通过，`fpga_flash_written:false`。调试器为 `0403:6010`、序列号 `2025030317`、location 53、sysfs `/sys/bus/usb/devices/3-5`。

更新后的电脑键盘窗口由用户级 `fpga-p23-keyboard.service` 保持运行，PID 2221234，会话为 `../../results/keyboard_session_20260916_144707_929753`。排旧缓存两秒后仍未收到 C350/K138/E138，窗口进入单向演奏状态；这不能证明板端通过或失败，也不能验证由 Push 发起的 PANIC 是否已经回传到电脑窗口。USB IN error 诊断仍为 `null`。第一次普通后台启动的 `keyboard_session_20260916_144240_535718` 随启动会话退出且没有按键记录，不作为实体证据。

实体检查覆盖：效果打开并有尾音时，电脑窗口 PANIC 立即静音并清键盘/Push/UI 持键显示；保持物理键不松时不自动重触发，松开再按可正常发声；Push CC27/29 PANIC 的板内 Push/音频/UI 清理正常。电脑长按、Push pad/连续压力、Push 屏幕与灯光、HDMI、耳机和 P10 串行效果链回归均正常。

验收后再次只执行 `Read Device Codes`：ID Code `0x0001081B`、UserCode `0x00000023`、Status Code `0x00026230`，确认板上仍为 P23。本次只读核对没有执行下载或 Flash 操作。电脑窗口会话仍只有 `open` 和 `one_way_ready` 两条记录，没有收到板端遥测，也没有用数字日志替代用户实体结论。
