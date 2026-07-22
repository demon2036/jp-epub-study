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
