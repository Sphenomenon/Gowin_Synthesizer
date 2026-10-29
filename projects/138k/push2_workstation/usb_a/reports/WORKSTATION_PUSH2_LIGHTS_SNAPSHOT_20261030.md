# Push灯光snapshot时序修复（2026-10-30）

只修改interaction-adapter owner `rtl/push2/push2_lights.sv`，将guide mode／mask完整寄存后用于显示，并把64bit变化判断拆成8个独立8bit比较寄存器。下一拍只对8个比较位及进入guide标记做OR。原F02 Path458的notes异步读→guide mask→64个COUT→LED CE长链因此在变化判断后有明确寄存边界；实际映射与48MHz routed timing仍需新综合／P&R，本轮未运行EDA或访问板卡。

已有的65bit mode／mask寄存器现在作为唯一显示快照；新增8bit变化结果和1bit进入标记。比较结果和快照在同一时钟采样同一输入，颜色／缓存／LED决定均不再读取raw guide信号。显示输入延后一拍，背压中的已生成命令仍保留原valid／kind／index／value，变化后仍清除旧灯并完整扫描85项。`push2_score_guide.sv`、played-note／cursor／score行为、音频及命令接受路径均未修改。

[机器记录](workstation_task_20261030/push2_lights_snapshot.json)包含源码hash、原物理失败、测试范围和PL guide完整源身份。测试从冻结对象`b686f65d6e3fd67237861da95624bc3685de8bb691533b73c82503ee431d955d`提取原模块，只在临时测试目录改模块名进行同场对照；冻结对象及baseline未改。

验证结果：

- 26组稳定输入的全部85灯最终颜色与原版本及独立颜色规则相等，原5条启动命令顺序和值相等。
- 3000clocks连续mode／mask更新、300clocks真实未接受payload长停顿、任意有限背压、8次背压中reset及最后target收敛通过；所有stall payload稳定，观测到9次完整guide清灯扫描。
- 原`tb_guidance`通过CNN list→排他灯光→错误／held／零力度音符处理；原`run_pl_guide.py`通过真实FIFO背压、完整feedback、Push guide／force和GW25K所有权等回归，产生85个audio events。
- `test_current_workstation_sources.py`的10项输入策略检查与`git diff --check`通过。

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_push2_lights_snapshot.py
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
python3 projects/138k/push2_workstation/usb_a/sim/run_pl_guide.py
git diff --check
```

对照共运行58403clocks，原／新分别接受2119／2162个命令。验证承诺是稳定后的最终灯光与启动序列；连续变化期间的中间packet顺序和数量可以改变，不能宣称逐packet等价。F03仍使用其锁定原输入，本次修复需要另一个显式source／候选身份及完整物理门禁；没有继承原失败候选的硬件接受结论。
