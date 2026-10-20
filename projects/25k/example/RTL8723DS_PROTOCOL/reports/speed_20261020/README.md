# 2026-10-20 下载提速验收

最终结果见 [summary.json](summary.json)。固化 UserCode 4096，配套 APK 0.2.1。旧确认写入保持兼容，新增可选无响应写入；实板纯 PCM 吞吐为原版约 1.9–2.1 倍。完整 192000 字节下载约 196 秒，WAV 与参考完全一致。

`baseline.json` / `fast_salted_sram.json` / `speed_flash.json` 为对比测速；`kotlin_fast_sram.json` 为 APP 原始 Kotlin 完整实板下载、主动丢片重试、取消与断线续传；`flash_recording.json` / `protocol_flash.json` 为固化后复验。

源码输入哈希、Android 补丁、JUnit、Lint 与独立日志留档。`source_before/` 和 `previous_ready_build.json` 保留优化前源码/镜像索引。早期 fast_sram / fast_sram_v2 因旧 GATT 属性缓存失败，保留诊断，不作为通过证据。详见 `../../docs/SPEED_OPTIMIZATION.md`。
