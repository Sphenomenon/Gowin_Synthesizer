# Android／25K蓝牙分支合入main（2026-10-20）

用户授权将`codex/android-bluetooth-control`合并进main。本次以main的`fb7e302e4d87cf7ae739666b2666a5200afbda5e`和分支`f2bae2dab3fbeb0ce5f55bbd555a3a29c76bb9c8`为输入，保留两个分支的提交历史，执行普通merge；不squash、不重置、不强推。分支的两笔业务提交为`37c8913`与`f2bae2d`。

## 合并内容与处理

新增`clients/android`共享Android工程，以及`projects/25k/example/RTL8723DS_PROTOCOL`独立业务GATT／录音／一阶和二阶无损下载工程、原始依赖、测试与历史验收记录。Android版本0.2.10，包含设置、录音、作品管理、CRC校验、可靠检查点、恢复下载、PCM／WAV保存和导出；25K侧保留RAW及旧传输协商兼容。具体协议与历史实测范围沿用导入文档。

唯一文本冲突是`.gitattributes`两边都在末尾追加规则，现同时保留main的138K原始证据字节／空白规则和分支的25K冻结输入／日志规则。`projects/25k/README.md`自动合并，保留此前MIDI键盘控件／回退边界和新增蓝牙例程入口。除这些合并保留的文件外，分支文件的Git内容与远端完全一致；`gradlew.bat`按既有属性在工作区检出为CRLF，索引仍与远端相同。

原main的2075项138K及MIDI键盘文件在合并业务源码后哈希一致。新合并记录及主机README／根规划的状态文字随后单独更新，不改写既有候选、冻结输入或历史验收JSON。其他人的根目录《工程架构报告.md》保持原字节且继续未跟踪。

## 本机重新验证

汇总：[verification.json](android_ble_merge_20261020/verification.json)。

| 验证 | 本次结果 |
|---|---|
| 导入源码／证据清单 | 672项通过；共享Android符号链接及冻结vendor原件校验通过 |
| 蓝牙RTL与codec | 50组通过，含多档MTU、第二阶／一阶无损、旧协议回放、GATT／ACL、UART系统、错误ROM／随机数失败关闭与独立PCM解码核对 |
| Android单元测试 | 63项通过，0失败、0错误、2项实板无线用例按现有条件跳过 |
| Android应用 | `assembleDebug`与`lintDebug`通过；lint无错误，1条依赖版本更新提示；APK保留在本机忽略目录 |
| 138K来源边界 | 10项通过；原有138K业务／T24候选输入未改变，未重新运行综合或P&R |

Android按仓库固定Gradle8.10.2、AGP8.7.3、Kotlin2.0.21，配合本机结果目录中的JDK17、SDK35及BuildTools35.0.0验证；没有改动项目依赖版本、Gradle脚本或业务源码。命令与环境摘要、测试XML及lint报告均在配套证据中。此次APK SHA256为`beb540889ac02d9fd82dc648019fe22ffcfc9a61a1b3a24da60b43050a7eb9ed`，来自本机调试签名，不要求与原验收机器的调试APK哈希相同。

蓝牙原测试脚本和四个codec测试台写死macOS的`/private/tmp`，本机Linux不能写该目录。本次复制到忽略的`results/`测试运行目录，仅把测试临时路径替换为独立scratch目录；生产RTL、导入源码、测试断言和数据不改。变换涉及的文件、替换次数及前后SHA256见[ble_runtime_transforms.json](android_ble_merge_20261020/ble_runtime_transforms.json)。实际RTL和未变换测试输入仍与原导入验收哈希一致；测试通过后再次执行原清单验证，原仓库保持原样。没有把原脚本直接在Linux运行失败写成通过。

本轮原始结果位于`results/merge_android_ble_20261020_195027`。可跟踪证据只存JSON／日志／XML，不包含SDK、JDK、APK、仿真可执行文件或实现数据库。

## 验收边界

本次完成代码分支合并和本机离线验证。25K独立蓝牙工程及其历史A25D／吞吐证据保留原归属；没有把其板级约束、器件或测试音录音替换到138K顶层。138K业务GATT、真实DDR录音接入、手机原生BLE／后台／实际速率、设备重启身份与未完成下载处理仍需各自验收。独立蓝牙例程不表示现有MIDI键盘已拥有全部蓝牙业务。

T24离线闭合及最小setup0.022ns结论保持；本轮未板测、未烧录、未修改硬件或引脚、未启动新的综合／布局布线／时序实验。25K专有效果、D整机和Push专有CNN／谱面引导的既定边界保持。
