# 本机产物

APK和位流不进入Git。APP源码在仓库根`clients/android`，从该目录构建`:app:assembleDebug`，输出`app/build/outputs/apk/debug/app-debug.apk`。原交付0.2.10 APK的哈希与证书记录见`../reports/speed18_20261020/android_inputs.json`。板卡位流在本工程重新运行`sh build.sh`生成，必须使用新构建清单通过`program_sram.py --check-only`后再编程；历史A25D验收身份不因重新构建自动继承。
