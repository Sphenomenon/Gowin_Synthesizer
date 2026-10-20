# 25K导入接续与已确认控件落地（2026-10-19）

本轮收尾fetch发现远程新提交`5a4bd71`（完整ID见证据），导入了完整25K源码、例程和硬件文档。此前“projects/25k只有说明”的状态已被该提交补齐；按用户原授权继续核对和修改真实设备代码。D采样器／TF PCM仍按用户补充口径保留，禁止直接播放预处理音乐冒充实时合成。未新增专有效果入口、16键效果表或整机D路由。

## 远程与本地内容保留

远程共1065个路径变化，与本地已修改文件唯一重叠为`projects/25k/README.md`，新增路径在本地均不存在。先保存该README完整副本、全体未提交受跟踪文件哈希及状态，再仅stash这一文件，随后`git merge --ff-only`快进到远程。其他138K脏文件与合并前哈希一致；根《工程架构报告.md》、历史PL规范、板端LATEST均未改。

远程README正文保留，本地已确认决定合并追加；原本地全文还保存在独立备份和stash，没有使用reset／clean或目录覆盖。本轮未创建新提交、未推送。原始导入来源清单`projects/25k/SOURCE_IMPORT.json`及其1060项哈希不改写；当前合法功能修改与原导入差异单列，不把源码哈希差异伪装成原件一致。

## 先核对到的实际差异

导入版`midi_performance.v`原用于六参数本地设置：E1选参数／切滑条模式，E2改参数／短按PANIC；滑条默认CC1；USB重连发送48条清理消息并重放持音。顶层还将E1长按接到本地设置切换，远端页面期间屏蔽旋转；原编码器每两个物理档发一次应用step。这些与已确认的138K面板约定不同。

保留原`midi_performance`及历史例程／测试；默认生产顶层和应用的`HOST_PANEL_CONTROLS=1`选择新`gw138k_panel_performance`。`HOST_PANEL_CONTROLS=0`仅为构建兼容分支，复现历史六参数／重连规则，不是新的用户菜单。验证旧行为的两项集成测试明确选择兼容分支；新测试使用默认生产应用，真实USB-MIDI编码及MK配置通道。

## 本轮代码落地

| 控件／职责 | 设备端行为 |
|---|---|
| 16键 | 默认48–63，按下一次On100，释放Off0；保存已发音符、通道和目标连接，释放使用保存值 |
| 持音移调 | 接收既有MK配置后先对本面板所有旧音发Off，再为仍按住的键发新On100；没有新物理入口，未确认产品移调范围／越界 |
| 滑条 | 固定Pitch Bend，左0、中央8192、右16383、释放8192；分段线性，中心死区参数默认3，沿用已有触摸滤波，实际调参待设备验证 |
| E1旋转／短按 | CC7绝对音量0–127，每物理档1，无加速；短按仅CC89=1，由138K维持模式实际提交条件 |
| E2旋转／短按 | Program按73、40、56、12、0循环，可反向；短按仅一次CC88=127，不产生释放消息或PANIC |
| 两编码器长按 | 复用既有短／长分类模块，长按不触发短按；面板分支不把长按接到设置或其他功能 |
| 本地状态初值 | USB新接入时本地音量127、Program73、弯音中心，与138K固定初值对齐；不从设备端重发整套默认或重复PANIC |
| 事件与会话 | 控制FIFO64项、稳定输出槽、既有路由FIFO背压；保存事件目标，新连接不继承旧控制；断开使原目标失效，不补播旧持音。其他仍在线目标保持其事件所有权 |
| 显示独立 | PL仍使用原端点／包／会话／序号／重试／心跳；PL/MK协议恢复不重置音源状态。远端页面期间旋转和短按继续工作 |
| 编码器底层 | 原去抖／方向／相位规则复用；新增DETENTS_PER_STEP参数，兼容默认2，面板顶层明确设1，保证物理每档一条应用step |
| 离线工具 | `run_checks.py --help/--output`；默认新结果在results，系统临时目录替代写死的/private/tmp；run_sim.sh透传参数，不覆盖导入历史报告 |

新控件模块是消息／状态映射，不复制音源、FFT或USB／SPI／触摸驱动，不增加DDR客户端。未修改硬件、管脚约束或触摸采集参数，未启动综合／P&R。

本地音量／音色初值对齐已实现；主机由其他入口改变参数后的完整双向同步仍受现有MMIO／PL缺少原始参数反馈的限制。Host基础页显示有效GAIN／profile，不足以直接反推出原始CC7。旧本地退回六卡诊断页也尚未改成25K专有页面，不能称为专有UI完成。

## 验证与证据

新定向测试通过：16键On/Off且持音不重复，256弯音位置单调及端点／中心死区／释放，音量每档和饱和、指定Program正反循环、短按仅一次、48条阻塞控制保持顺序、持音移调全部旧Off先于新On、PL/MK恢复独立、USB快重连不补播、BLE新接入不继承或丢弃排队USB控制。另有真实AB输入的一物理档一step、反向、回弹及非法相位测试。

138K生产Host加实际设备`panel_display_endpoint.v`闭环通过1019请求、2个完整帧，覆盖HELLO／TILE／END／DRAWN／manual／resume；同时Host场景26帧、6572tiles、225737次MIDI轮询及generic热插拔检查通过。这里的manual只验证既有PL端点能力，面板顶层未为长按分配manual入口。

完整25K回归最终`passed=true`：38个测试台、25个Python协议测试、Verilog-2005顶层展开、USB HS/FS和BLE错误ROM拒绝均通过，QT2160原件22项／PL参考11项校验通过，88项检查、152项输入哈希稳定、失败列表为空。结果见[汇总](gw25k_controls_20261019/verification.json)及[设备原始结果](gw25k_controls_20261019/device_validation.json)。首轮`results/host_panel_regression_20261019`为passed=false：旧控件集成测试最初未显式选择兼容分支，且期间仍有输入编辑；该记录保留，不当成最终验收，也不改写旧报告。最终回归单独使用`results/host_panel_final_20261019`。

复现：从仓库根目录执行，先查`--help`：

```sh
python3 projects/25k/example/MIDI_KEYBOARD/tools/run_checks.py --help
sh projects/25k/example/MIDI_KEYBOARD/run_sim.sh --output projects/25k/example/MIDI_KEYBOARD/results/checks_new
```

真实Host／端点闭环：在`projects/138k/push2_workstation/usb_a`执行：

```sh
python3 sim/run_gw25k_panel.py --endpoint-rtl /home/sphenicidition/Documents/fpga/projects/25k/example/MIDI_KEYBOARD/rtl/control/panel_display_endpoint.v --output results/gw25k_real_endpoint_new
```

## 当前完成边界

完整设备源码已到位，已接受的基础控件已进入真实顶层和应用；25K专有的演奏／效果上下文、16键效果表、作用路径和完整D整机仍待后续决定及接入，不把它们视为本轮完成。Push专有CNN扒谱／谱面引导、普通generic能力及138K初始化语义不变。

导入资料已说明GW5A-LV25MG121NC1/I0、50MHz、NV3007 142×428 SPI及键序，但真实触摸稳定性、引脚／屏幕实物对应性、完整板间联调没有新验收。现有QT2160配置包含16ms名义扫描间隔，与≤10ms／≤5ms端到端目标必须继续核对；本轮不改采集参数，不用固定帧周期或模型jitter0替代整机延迟。实际PT8211与标准I2S的格式差异见[赛题对照](CONTEST_REQUIREMENTS_20261019.md)。

未板测、未烧录、未改硬件或引脚、未SYN／P&R、未新增时序实验；时序未闭合。

`config/board.json`中的原六参数交互描述保留导入时独立例程口径，不生成当前RTL映射；当前面板策略以顶层参数和本报告为准。物理配置、约束与冻结依赖未改。

## 当前范围：保留本轮控件，撤回后续设备修复

用户随后要求138K优先、25K少动／以建议为主。后续连接与排队修复已撤回，生产模块及设备输入集恢复到本报告对应的152项；本报告中的基础控件保留。新增边界测试已移出活动设备工程，三处后来复现的边界缺口仍属于建议项。最近39测试台结果只保留为已撤回候选，当前状态见[回退记录](GW25K_ROLLBACK_20261019.md)。
