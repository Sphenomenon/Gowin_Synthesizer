# 赛事标识与 24px 字形

模块 `../workstation_contest_brand.sv` 只负责顶栏品牌覆盖，不含业务状态。输入 `pixel_x/pixel_y` 在 `enable=1` 的下一个上升沿对应到 `hit/pixel_rgb`；禁用周期全部流水状态（包含 valid）保持，随父 raster 一同停顿。首次启用之前无初始化保证，由父显示流水有效位屏蔽。logo 与两行文字的完整矩形（包括白色背景像素）均置 `hit=1`，其余位置 `hit=0`、白色。

官方原 PNG：`contest_fpga_logo_original.png`，283×80，RGBA。来自总官网 FPGA 入口直接指向的赛道官网 header。保留官方设计，生成过程只在白底合成 alpha 并量化为四种颜色，不缩放或裁剪。图内“国赛十周年”是官方原设计，不据此另行认定届次。原文字与出处、抓取时间、SHA、版权声明详见 `contest_brand_sources.json`。官方原文将“创意发挥、规范设计、突破自我、快乐竞赛”称为“竞赛原则”。

布局采用半开区间：logo x=[64,347), y=[24,104)；标题 x=400,y=24；原则 x=400,y=64；24×24 固定单元。标题 41 单元，原则 19 单元，共享 47 个唯一字形。ROM 数据身份与字符映射见 `contest_brand_layout.json`。

`contest_brand_logo_pairs.memh` 每行 142 个 4bit word，bit[1:0] 为偶数 x、bit[3:2] 为奇数 x，最后一个奇数像素补白且不显示。共 11360 word。`contest_brand_glyphs.memh` 按 glyph_id×24+row 排列，每 word 24bit，bit23 为最左像素，共1128 word。两 ROM 都采用同步 enable 读；palette 和字形行内位选在读出后完成。此处只陈述存储布局，不预报综合或物理资源用量。

再生成：从 sources.json 中 Google Fonts 原 URL 取得固定 SHA 的 Noto Sans SC 字体（SIL OFL1.1，许可证原文为 contest_brand_font_OFL.txt），执行：

```sh
python3 tools/generate_workstation_contest_brand.py --font /path/to/NotoSansSC-wght.ttf --check
```

去掉 `--check` 可更新 ROM 与映射；`--preview /outside/source/preview.png` 可额外保存视觉审阅图。字体 24px，wght=500，baseline=21，灰度阈值128。字体二进制不随构建复制；生成后的 ROM 是编译输入。默认 readmemh 与 include 路径均相对 Prj1 根目录 `rtl/display_data/assets/...`。
