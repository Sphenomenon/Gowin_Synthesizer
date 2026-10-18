# TF 音频与 workstation DDR 整合

本阶段把 `Mega_138K/Dev/Prj1` 中已经验证的 TF/FAT、DDR 环形双 bank、WAV、MP3 和 FLAC RTL 作为自包含源码移入 USB-A workstation。构建和发布不再依赖另一个 Git 工作区；第三方来源、GPL-3.0 文本和 MP3 ROM 表均随源码保存。

## 运行边界

- TF 通过 NEO Dock 31005 的 J31 micro-SD，以 SPI 模式读取 FAT16/FAT32 根目录中的 8.3 文件。
- `python3 build.py --tf-audio-kind wav|mp3|flac` 每次只展开一种 decoder，默认 WAV，避免三套 decoder 同时占用紧张的 BSRAM。
- 文件字节是 8 bit，计数、长度、逻辑偏移和 bank 指针均为 32 bit；PCM 是左右各 16 bit，工作站/DAC 边界扩展成现有的 32 bit Q1.31。没有新增 64/128/256 bit 音频业务数据通路。
- Gowin DDR 用户口的 256 bit 只表示 32-bit DQ × BL8，即一个 32-byte beat。`app_addr` 是 native 32-bit word 地址，每 beat 增加 8，低三位必须为 0。
- TF PCM 第一次有效后才接管 PT8211 引脚；文件结束或断流约 4096 帧后自动回到原 workstation 合成器。没有卡、没有匹配文件或 decoder 拒绝格式时，原工作站音频保持工作。
- restart 或 track 变化会重置 byte FIFO、DDR 读写 epoch、decoder、PCM CDC FIFO 和输出选择，旧曲数据不会进入新曲。

## 统一 DDR 地址表

物理 DDR 为 1 GiB。表内 byte 地址是物理字节偏移；native 地址是 Gowin `app_addr` 的 32-bit DQ word 单位。

| 用途 | byte 起始 | byte 结束 | native 起始 | native 结束 | 状态 |
|---|---:|---:|---:|---:|---|
| 视频 frame 0 / BIST 前半 | `0x00000000` | `0x003fffff` | `0x00000000` | `0x000fffff` | 活跃 |
| 视频 frame 1 / BIST 后半 | `0x00400000` | `0x007fffff` | `0x00100000` | `0x001fffff` | 活跃 |
| 显示扩展保留区 | `0x00800000` | `0x00ffffff` | `0x00200000` | `0x003fffff` | 活跃+预留 |
| AE350 UI page 0 | `0x01000000` | `0x013fffff` | `0x00400000` | `0x004fffff` | 活跃 |
| AE350 UI page 1 | `0x01400000` | `0x017fffff` | `0x00500000` | `0x005fffff` | 活跃 |
| 音频 bank 0 | `0x01800000` | `0x057fffff` | `0x00600000` | `0x015fffff` | 活跃，64 MiB |
| 音频 bank 1 | `0x05800000` | `0x097fffff` | `0x01600000` | `0x025fffff` | 活跃，64 MiB |
| 低地址增长池 | `0x09800000` | `0x0fffffff` | `0x02600000` | `0x03ffffff` | 预留，104 MiB |
| 神经网络模型/权重/激活池 | `0x10000000` | `0x2fffffff` | `0x04000000` | `0x0bffffff` | 预留，512 MiB |
| BSRAM 迁移与 bulk state 池 | `0x30000000` | `0x3fffffff` | `0x0c000000` | `0x0fffffff` | 预留，256 MiB |

显示扩展区内当前 DSP2 ABI 使用 byte `0x00800000..0x008bffff`：control native `0x00200008`，两个 payload native base 分别为 `0x00210000`、`0x00220000`。AE350 软件仍使用 CPU 地址 `0x10000000/0x10400000`，`gw138k_ahb_ddr` 把它们映射到表中的物理 UI page。

音频 bank 的最后一个合法 BL8 起始地址分别是 native `0x015ffff8` 和 `0x025ffff8`。bank 大小是 `0x04000000` bytes = 16,777,216 native words = 2,097,152 BL8 beats。

地址宏的唯一来源是 `rtl/ddr_address_map.vh`。构建时 BIST、视频 frame stride/metadata、display-data package、UI page、AE350 AHB bridge 和 TF DMA 都绑定到该表；`ddr_address_map_guard` 在 elaboration 时检查容量、换算、顺序、对齐和重叠。

## 动态双 bank 状态机

DDR DMA 是生产者/消费者环，而不是 128 MiB 文件上限：

1. SD/FAT reader 通过异步 byte FIFO 向 DDR 域送字节。
2. DMA 聚合成 32-byte BL8，按 bank 0、bank 1 的逻辑连续顺序写入。
3. 累积到启动水位或短文件 EOF 后，DMA从相同逻辑顺序读回，复制到 playback FIFO 后立即释放对应 DDR beat。
4. 文件超过 128 MiB 时，写指针只能在读指针已经释放空间后回绕；因此旧 beat 不会在 decoder 读取前被覆盖。流可以多次循环两个 bank。
5. 最后不足 32 bytes 的 beat 在 DDR 中补零，但只向 decoder 发出真实字节数。
6. 32-bit 总字节计数到 `0xffffffff` 后明确置 `capacity_error` 并结束，不发生静默 4 GiB 回绕。

DDR arbiter 的优先级为 startup BIST（未完成时）→ 视频 scanout → TF audio → display reload → CPU/writer 公平选择。所有 read response 通过 FIFO tag 按发出顺序返回；audio read 不会误收 scan/display/CPU 的数据。

## Decoder 完成度

- WAV：RIFF chunk 遍历，支持 PCM 8/16/24/32-bit、mono/stereo，未知 chunk 与奇数 padding 可跳过。
- MP3：纯 RTL MPEG-1 Layer III 路径，真实 128 kbit/s 文件回归产生 48 kHz stereo PCM。
- FLAC：支持 native FLAC metadata、fixed-block、mono/independent stereo、constant/verbatim/fixed predictor 0..4、Rice 0/1，最大 block 8192。LPC、variable-block、side/mid stereo、wasted bits、Rice escape 明确报 unsupported；CRC 字段目前解析但未校验。

## 验证入口

```sh
cd migration/gw138k_audio/push2_workstation/usb_a
python3 sim/tf_audio/run.py
python3 build.py --prepare-only --no-update-latest
python3 sim/run.py results/<本次 build>
python3 sim/p11/run.py results/<本次 build> --write-path
```

专项回归覆盖空/小文件、整 beat、bank 尾、跨 bank、整 128 MiB 窗口的缩放模型、超过窗口的动态回收、多次回绕、restart 隔离、byte/native 地址换算、`app_addr[2:0]==0`、每 beat `+8`、DDR audio tag，以及 WAV/MP3/FLAC decoder。

## 后续扩展规则

- 新的神经网络不能直接硬编码地址；在 512 MiB NN pool 内由 descriptor allocator 分配 1 MiB granule，并把 owner、长度、版本和校验记录进统一表。
- 大型 delay/reverb history、wavetable、FFT/analysis history、recorder 和非延迟关键 cache 优先迁入 256 MiB bulk pool；只把实时窗口留在 BSRAM。
- 任何新 DDR 客户端必须增加地址 guard、仲裁 tag、带宽/饥饿测试和 restart epoch；不能只在顶层写一个新 base 常量。
- 视频/显示格式增长优先使用 8–16 MiB 保留区；不得侵入 16–24 MiB UI 或 24–152 MiB 音频 ring。

本阶段只做离线源码、仿真和综合检查，不烧录 SRAM/Flash。
