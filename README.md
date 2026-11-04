# Gowin Synthesizer

基于 Gowin FPGA 的音频工作站工程，包含 138K 主机、25K 交互面板和 Android 客户端源码。

主机代码按音频合成与效果处理、MIDI／USB 输入、TF 音频、DDR 存储、识别、显示和蓝牙通信划分模块。交互面板包含触摸、编码器、屏幕和 USB 设备接口；Android 客户端包含控制界面、BLE 协议和录音文件传输代码。

## 工程目录

| 目录 | 内容 |
| --- | --- |
| `projects/138k/push2_workstation/usb_a/` | 138K 工作站 RTL、固件、约束、板级配置和构建入口 |
| `projects/138k/ae350/` | AE350 处理器相关工程 |
| `projects/25k/example/MIDI_KEYBOARD/` | 25K MIDI 与屏幕交互面板工程 |
| `projects/25k/example/RTL8723DS_PROTOCOL/` | BLE 业务协议与录音传输工程 |
| `projects/25k/prj/` | 25K 板级工程与外设代码 |
| `clients/android/` | Android Kotlin／Compose 客户端 |
| `example/` | 独立外设工程 |

## 构建入口

Gowin 工程使用其对应的项目文件、器件配置和约束。138K 工作站的构建入口是 `projects/138k/push2_workstation/usb_a/build.py`，输入配置位于同目录的 `boards/` 和 `baselines/`。

Android 客户端使用 `clients/android/` 下的 Gradle 工程。第三方代码的版权声明和许可证保留在对应源码目录。
