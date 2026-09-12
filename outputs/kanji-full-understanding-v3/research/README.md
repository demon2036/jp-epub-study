# 常用音训覆盖核对

`official-readings.json` 保存本书 232 个汉字在文化厅《常用漢字表》（2010 年 11 月 30 日内阁告示）中的 724 项音训，供 `audit_official.py` 与读音导航逐项比较。`official-reading-gaps.json` 是本次比较结果，空列表表示这些音训均已覆盖。

原文：[文化厅《常用漢字表》页面](https://www.bunka.go.jp/kokugo_nihongo/sisaku/joho/joho/kijun/naikaku/kanji/) · [官方 PDF](https://www.bunka.go.jp/kokugo_nihongo/sisaku/joho/joho/kijun/naikaku/pdf/joyokanjihyo_20101130.pdf)

如需重新提取，下载官方 PDF 后使用 Poppler 保留表格布局，再将文本传给脚本：

```bash
pdftotext -layout joyokanjihyo_20101130.pdf joyokanjihyo-layout.txt
python outputs/kanji-full-understanding-v3/audit_official.py \
  --source-text joyokanjihyo-layout.txt
```

默认运行无需联网，直接使用已保存的音训快照。表内音训用于核对常用读法；本书总计 824 项导航还包含原学习清单的其他读法及整词学习项。
