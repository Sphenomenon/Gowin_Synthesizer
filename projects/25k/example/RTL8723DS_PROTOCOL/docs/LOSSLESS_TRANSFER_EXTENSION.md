# 可选无损 PCM 下载协议 / OPEN_LOSSLESS

OPEN_LOSSLESS3d uses the same request/24-byte response and PCM max as3c.
Only explicit success authorizes READ_LOSSLESS3e and ACK_READ_LOSSLESS3f.
Requests/positive receipt/error/atomic ACK semantics match31/35;3f carries
the preceding decoded PCM CRC. Successful DATA remains opcodeD0, max8160.
The DATA PCM length stays the original requested PCM length; reserved16 is
now codec:u8 + zero:u8 for these two reads only.0 means original PCM and10
means stereo signed16 modular delta + Rice k9. Logical payload size may
therefore be smaller than28+PCM length. Logical CRC covers encoded bytes;
PCM CRC, all offsets, acknowledgements/checkpoints/object CRC refer to exact
decoded PCM. Predictors reset to0 for both channels at every block.

Rice: zigzag(delta16), q=value>>9. q<15 emits q one bits,0,9 remainder
bits MSB-first. q>=15 emits15 ones then the16-bit zigzag value MSB-first,
with no extra delimiter. Final byte zero-padded. Only canonical escapes,
exact decoded sample count, no trailing whole byte, zero padding accepted.
Encoder uses codec10 only if strictly shorter than PCM, otherwise codec0.
Mode is in the old reserved field, so RAW adds no bytes and max stays8160.

Raw31/35 remain RAW even within a3d transfer. Cached3e/3f replay requires
an active lossless profile and sufficient PCM chunk limit; otherwise8d,
noDATA and no mutation of the cached successful result. A sufficiently
large reopened3d reconstructs identical deterministic DATA. Distinct read
opcodes preserve exact wire replay across encoding changes. Current mode
is never inferred from a DATA marker or a compressed length alone.

App negotiates3d→3c→3b→39→38→37→36→30, only on explicitUNSUPPORTED80.
DefaultCapability, other responses/status, UART921600, H5window1, ACL27/8,
businesswindow1 remain. Decode/validate before publishing a success receipt;
save exact PCM and durable checkpoint before ACK. Old apps never request3d.

## 实现与复现

FPGA 模块 `ble_rice_encoder` 在 `rtl/ble_recording.v`，以独立的两路预测器对任意 stereo PCM16 做模16位差分；先计算编码长度，再决定写入原有四个2KiB缓冲或使用RAW，不增加负载RAM。不会引用内置音频字典或在APP根据音源重建。当前测试源仍是内置1秒音频，尚未接入麦克风。

APP `PcmRice` 严格限制输入与输出，拒绝未知模式、截断、非规范转义、额外整字节及非零填充。只有明确成功3d、对应3e/3f待处理请求、逻辑CRC/PCM CRC和完整身份范围验证成功后，ProtocolSession才发布成功回执及归一化PCM。落盘、检查点及ACK仍使用原始PCM字节。

电脑实测使用 `tools/speed_check.py --lossless --write-command --ack-read --chunk 8112 --pcm-bytes 32768 --observe --output reports/lossless_speed.json`；完整录音使用 `tools/recording_check.py --lossless --write-command --ack-read --frames 48000 --output reports/lossless_recording.json`。详细时序、相同镜像对照、错误输入、重放与断线续传证据见第十七轮报告。手机原生GATT实际速率需要手机测试。
