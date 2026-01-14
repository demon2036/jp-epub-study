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

脚本支持 `claude` 与 `codex` CLI 生成内容，使用 `-b/--backend` 或 `KANJI_BACKEND`/`AGENT_TYPE` 选择。

```bash
python scripts/batch_generate_v3.py
python scripts/make_epub_v2.py
```

- backend 示例：`python scripts/batch_generate_v3.py -b codex`

### 释义与词源要求（JSON 输出）

- summary 必须包含核心含义与来源线索，并逐一说明各读音的典型场景
- 需要给出词源/词根/词缀或古语词形；禁止仅写“中古日语/古日语/汉语”
- 无法考证时写“资料不足/不确定”
- etymology 字段已移除，词源信息写入 summary 或 readings.origin

