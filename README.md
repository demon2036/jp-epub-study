# 日文 EPUB 学习项目（汉字/词汇详解生成）

这个仓库主要用来抓取/整理日语常用汉字数据，并用脚本生成解释内容与 EPUB，便于离线学习。

## 目录结构

- `jp/`: 抓取与数据处理逻辑
- `scripts/`: 生成/渲染/导出脚本
- `data/`: 原始与中间数据，以及已选定提交的 EPUB 成果；临时产物按 `.gitignore` 排除
- `outputs/kanji-full-understanding-v3/`: 最新完整理解版、阅读预览、生成源码与校验记录

## 最新成果：日语为什么这样读 · 完整理解版

[下载最新完整版 EPUB](outputs/kanji-full-understanding-v3/日语为什么这样读_226字完整理解版.epub?raw=true) · [阅读预览与生成说明](outputs/kanji-full-understanding-v3/README.md)

覆盖原学习清单的 226 个汉字及全部 742 项读音记录，补充上、入、起、落、照、雨 6 章，共 **232 章、824 项读音讲解、850 组日文／假名／中文例句、948 道练习与答案**。从场景、意义、词干和构词解释“为什么这样读”，保留深入的自动词／他动词讲解，并扩展名词结合形、连浊、字音与整词读法。每项读音都能直接跳转到对应讲解。

已通过 EPUBCheck 5.3.0（错误、警告均为 0），完成全书内部链接、读音覆盖及手机大字号阅读检查。网页预览支持检索、调整字号和隐藏假名；源码、构建结果与校验记录一同保存。

## 前一版：日语为什么这样读 · 226 个难点精讲

[下载 EPUB《日语为什么这样读：226 个难点精讲》](data/kanji-understanding/日语为什么这样读_226个难点精讲.epub?raw=true)

依据 2026 年 9 月 7 日的学习记录整理，覆盖 226 个标记为“至少一项不会”的汉字及其 742 项读音卡片，逐字解释词干、活用、构词、字音和历史音变，附 11 篇机制讲解、“照”的完整示范、索引与参考来源。标记以汉字为单位，不表示 742 项读音全部不会。

本版已通过 EPUBCheck 5.3.0 校验，错误与警告均为 0。

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 常用汉字 2136 字成果

`data/joyo_gpt56terra_max_300/` 保存了完整的 2136 字结构化数据库和可直接阅读的 EPUB：

- `joyo_gpt56terra_max_300_db.json`：2136/2136 条完整数据
- `joyo_terra823_sol1313_max_2136.epub`：Terra Max 823 字与 Sol Max 1313 字合订版
- `joyo_gpt56sol_max_1313.epub`：只包含 Sol Max 完成的 1313 字
- `joyo_terra823_sol1313_max_2136_pronunciation_audit.json`：发音审计结果
- `joyo_terra823_sol1313_max_2136_manifest.json`：模型分段、并发记录与文件校验值

Terra Max 的前 823 字由 Git 标签 `joyo-terra-max-823` 固定。续跑脚本会逐项验证该检查点未被改动，密钥只从环境变量读取：

```bash
CRS_OAI_KEY=... CONCURRENCY=60 \
  bash data/joyo_gpt56terra_max_300/run_remaining_sol_max.sh
```

### 抓取数据

```bash
python scripts/fetch_joyo_kanji.py
python scripts/fetch_kyoiku_kanji.py
```

### 生成解释与 EPUB

脚本支持 `claude` 与 `codex` CLI 生成内容，使用 `-b/--backend` 或 `KANJI_BACKEND`/`AGENT_TYPE` 选择。
当前仓库默认的 Codex 配置文件是 `codex.cliproxy.config.txt`，对应本地 `cliproxyapi`：

```bash
export CLI_PROXY_KEY=...
python scripts/batch_generate_v3.py -b codex
```

```bash
python scripts/batch_generate_v3.py
python scripts/make_epub_v2.py
```

- backend 示例：`python scripts/batch_generate_v3.py -b codex`
- 生成过程是“完成一个汉字就写回一次 `data/kanji_db_v2.json`”，中断后可直接续跑未完成项
- 若某些字因校验失败或请求失败被标成 `failed`，可用 `python scripts/batch_generate_v3.py -b codex --retry-failed` 继续补跑
- `python scripts/make_epub_v2.py` 会按数据库中的原始顺序拼接已完成内容，而不是重新按字面排序

### Codex `exec` 与 `@文件`

`codex exec` 原生命令不会在 CLI 侧自动展开 `@README.md` 这类文件引用。  
在这个仓库里，如果你需要用非交互 `exec` 并引用本地文件，请用：

```bash
python scripts/codex_exec_with_refs.py 'Write tests for @README.md'
```

这个 wrapper 会：

- 默认把工作目录设为 `~/jp`
- 先把 `@文件路径` 展开成真实文件内容
- 再调用底层 `codex exec`

### 释义与词源要求（JSON 输出）

- summary 必须包含核心含义与来源线索，并逐一说明各读音的典型场景
- 需要给出词源/词根/词缀或古语词形；禁止仅写“中古日语/古日语/汉语”
- 无法考证时写“资料不足/不确定”
- etymology 字段已移除，词源信息写入 summary 或 readings.origin
