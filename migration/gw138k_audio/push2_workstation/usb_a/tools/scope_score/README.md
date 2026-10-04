# 几何与控制场景编译器

`compile_scope.py` 将 SVG、顶点路径或参数方程编译为几何相位坐标 ROM，同时验证控制场景并输出 256×64 cue 初始化表。依赖 Python 3 和 NumPy；独立仿真绘图另需 Matplotlib、Verilator、C++ 编译器。

```sh
python3 tools/scope_score/compile_scope.py tools/scope_score/geometry.json \
  --scene tools/scope_score/demo_scene.json --out rtl/audio/scope_vec/data
```

`geometry.json` 的 schema 为 `scope-geometry-v1`。每个 shape 只能选择一种来源：

```json
{"schema":"scope-geometry-v1","shapes":[
  {"name":"circle","x":"cos(t)","y":"sin(t)"},
  {"name":"outline","svg":"outline.svg"},
  {"name":"triangle","vertices":[[-1,-1],[1,-1],[0,1]]}
]}
```

`t∈[0,2π)`；表达式通过 AST 白名单验证，支持数学运算与 `sin/cos/tan/sqrt/abs/exp/pi`，没有任意 Python 调用或文件读取。SVG 支持单一闭合 `path` 的 `M/L/H/V/C/Q/Z`（absolute/relative）、`polygon/circle/ellipse`。曲线先细分，再按闭合轮廓弧长采样。多轮廓、未闭合 path、arc/S/T、transform、image、未知元素均明确报错；不能悄悄忽略。带 transform 的 SVG 必须先展平为坐标。

路径统一去 DC、保留最多 8 次谐波，再归一化至峰值 30000。可选 `--points 128/256/512`，最多 8 shape，几何数据总量不超过 16384 byte。数据超限、零长度或平滑后退化、非有限坐标、未知字段、非法表达式均失败；不会截断点表或 cue。

场景 schema 为 `scope-control-v1`，`duration_samples` 必须为 30…60 秒的整数 48 kHz 样本数。`events` 按非递减绝对样本时间排列；同时间戳保持输入次序。支持 `note_on/note_off/cc/bend`，note 0…95，力度 1…127，bend unsigned14。`note_on` 可带 shape id，会展开成“同时间戳 CC97 选图形 + note-on”。展开后也必须 ≤256 cue。

```json
{"schema":"scope-control-v1","duration_samples":2160000,"events":[
  {"sample":0,"op":"cc","cc":90,"value":127},
  {"sample":0,"op":"note_on","note":69,"velocity":100,"shape":0},
  {"sample":48000,"op":"bend","value":9000},
  {"sample":72000,"op":"note_off","note":69}
]}
```

输出：`paths.mem`、`rotation.mem`、`note_steps.mem`、`scene.json`、`scene_controls.mem`、`manifest.json`。前者是相位几何点，后二个控制表分别是旋转数学系数与 MIDI 扫描步进。cue 高 32 bit 为 timestamp，低 18 bit 为现有 MIDI `{kind,a,b}`，中间 14 bit 恒零。原 `score_led_player` 的低 32 bit 是 LED mask，本工具的 cue 由新 `scope_control_player` 使用，不能混用。

## 不含 PCM 的可审计自证

本工具不接受音频输入、不调用音频解码库、不创建录音或播放流。输入 schema 只允许几何定义和控制事件，每个字段和事件类型都验证；`audio/samples/buffer` 等载荷字段拒绝。输入目录和输出目录扫描音频扩展名及 RIFF/FORM/FLAC/Ogg/ID3/AU 容器头。生成物由确定的几何函数和控制编码得到，manifest 保存生成器、输入（含 SVG）与输出的 SHA256，标记 `audio_payloads=0`。

“任何 PCM 字节”在字节层面不能与任意 signed16 坐标严格区分：任何坐标字也可被错误解释成音频采样。可验证的界线是**数据语义、来源和 HDL 读取方式**。`paths.mem` 的地址仅是 shape id 和环形相位，不含播放时间；场景只包含时间与 MIDI 控制字；每次 note-on 的音高、力度、包络和相位在 HDL 实时决定输出。这里的禁止项指 PCM 音频文件、时域音频素材和采样推流，而不是禁止合规几何坐标本身的二进制数值。只有扩展名检查不足以证明这一点，因此同时检查 schema、来源 hash、预算和合成读取路径。

仿真过程在进程 RAM 中接收实时 HDL 样本，用于 FFT 和数值断言；不会把这些样本保存为音频文件、文本样本 dump 或波形捕获。失败时也滤除样本行、禁止 core dump，仅写指标和断言日志。12 组编译器负向测试以及 SVG cubic/quadratic 测试位于 `sim/scope_vec/run.py`。

现场映射、控制播放器、默认干声策略、频率边界及演示步骤见 [矢量引擎说明](../../rtl/audio/scope_vec/README.md)。
