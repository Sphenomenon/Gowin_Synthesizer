# 2026-10-20 内置音频录音验收

最终结果见 [summary.json](summary.json)。已固化 UserCode 7379；0.2.0 APK 位于 `../../artifacts/`。完整 1 秒 WAV 在 SRAM 实测，Flash 重载后再次验证 100 ms 对象、续传、STOP 与旧身份失效。Android 手机验收由用户安装 APK 进行。

`kotlin_credits_sram.json` 是 APP 原始 Kotlin 完整下载记录；`complete_wav_check.json` 验证 WAV 与参考逐字节一致；`flash_recording.json` 与 `protocol_flash.json` 为固化后复验。日志、JUnit、源码哈希、相对 37c8913 的 Android 补丁均在本目录。

早期 slow/fast/final 文件保留为性能诊断，不作为通过证据。`credits_sram_short.json` 为主机检查器把异步 ACCEPTED 误当 OK 的失败记录，修正后 v2 完整通过。此前无录音固件索引保留在 `previous_ready_build.json`。
