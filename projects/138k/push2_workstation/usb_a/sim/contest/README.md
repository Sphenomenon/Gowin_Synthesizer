# 实时合成评分离线证据

本测试使用当前工作区音源RTL、功能full83暂存的依赖和ROM、现有PT8211串行发送器及其独立接收观察器。它从内部18bit CPU事件口发送32个不同Note On，逐声部检查频率步长、相位槽、包络与增益，并在串行输出端重建32768个PCM16样本。离线FFT必须发现MIDI60–91的32个不同谱峰，随后检查单独Note Off不释放其他声部。

在`projects/138k/push2_workstation/usb_a`执行，先查看参数：

```sh
python3 sim/contest/run.py --help
python3 tools/build_current_workstation.py --prepare-only
python3 sim/contest/run.py --baseline PREPARE/Prj1 --output results/contest_synth_new
```

把PREPARE替换为本次准备目录。只接受`accepted_full83`准备输入，沿用冻结依赖，不使用`--cnn-timing85`。依赖Verilator、C++编译器、Python numpy／scipy／matplotlib；输出含输入SHA256、编译／运行日志、频谱图、原始串行重建数据及verification.json。对象和PCM只放忽略的results目录，报告只归档小型证据。

A模式使用每声部1分量，以32个完整独立声部作为保守计数。名义48kHz下吞吐为1536000振荡器采样／秒；1024个存储槽不能自动等同于1024个可闻独立振荡器。本测试检查固定1600周期帧间隔、渲染在帧内完成和采集阶段欠载不增长，但不验证布线后的时序，也没有测量传感器、USB、排队与模拟DAC端到端延迟。

现有输出为PT8211右对齐串行格式，不能据此声称已经满足标准I2S。此测试是仿真测试入口，并未增加板上测试菜单或现场32音触发入口。D／TF素材路径另行测试；本测试的干声合成输入不用于否定其按用户补充口径保留的用途。
