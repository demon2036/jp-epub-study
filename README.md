# 日文 EPUB 学习项目（汉字/词汇详解生成）

这个仓库主要用来抓取/整理日语常用汉字数据，并用脚本生成解释内容与 EPUB，便于离线学习。

## 目录结构

- `jp/`: 抓取与数据处理逻辑
- `scripts/`: 生成/渲染/导出脚本
- `data/`: 原始与中间数据（不提交 `*.pdf` / `*.epub` / `*.log` 等产物）

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 抓取数据

```bash
python scripts/fetch_joyo_kanji.py
python scripts/fetch_kyoiku_kanji.py
```

### 生成解释与 EPUB

部分脚本会调用 `claude` CLI 生成内容，请先确保本机已安装并可用。

```bash
python scripts/batch_generate_v3.py
python scripts/make_epub_v2.py
```

