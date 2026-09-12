# 日语为什么这样读 · 226字完整理解版

[下载完整版 EPUB](日语为什么这样读_226字完整理解版.epub?raw=true)

本版围绕“为什么这样读、怎样从一个词想起一组词”展开，覆盖原学习清单的 226 个汉字及全部 742 项读音记录，另补上、入、起、落、照、雨 6 章，共 232 章、824 项读音导航、850 组日文／假名／中文例句、948 道练习与答案。

每章从具体场景解释意义、词干、构词和读音的联系。导读讲清自动词与他动词中的 r／s 等词形关系；连接方法篇继续讲名词结合形、连浊、促音、长音、字音分层与整词读法。每项读音都可跳转到相应讲解与例句。

## 阅读预览

下载仓库后，在本目录运行：

```bash
python -m http.server 32872 --bind 127.0.0.1
```

在浏览器打开 `http://127.0.0.1:32872/阅读预览.html`。目录支持按汉字、读音和例词检索，正文支持调整字号、遮住假名、章节与答案跳转。GitHub 的文件浏览页面显示 HTML 源码，本地服务器提供实际阅读页面。

## 从源码重新生成

需要 Python 3.10 或更新版本。以下命令在仓库根目录执行：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r outputs/kanji-full-understanding-v3/requirements.txt
python outputs/kanji-full-understanding-v3/prepare.py
python outputs/kanji-full-understanding-v3/build.py
python outputs/kanji-full-understanding-v3/audit_official.py
python outputs/kanji-full-understanding-v3/validate_book.py
```

封面生成使用 Noto Sans CJK 的 Regular 和 Bold 字体，默认路径是 `/usr/share/fonts/opentype/noto/`；Debian／Ubuntu 可安装 `fonts-noto-cjk`。重新构建会生成 EPUB、封面、阅读预览和构建报告；EPUB 标识、构建时间及校验值会随构建更新。

- `editorial/`、`extra-readings/`：逐章讲解、扩展读音与回想练习的手写稿。
- `trial-chapters.md`、`trial-answers.md`、`trial-readings.json`：十字试读版中沿用并完善的章节和导航。
- `corpus.json`：原学习清单与生成所用的数据快照。`prepare.py` 中的校订覆盖原始数据里发现的误读和不合适例词。
- `intro.md`、`patterns.md`、`practice.md`、`practice-answers.md`：导读、连接方法与二十个混合练习。
- `prepare.py`：组装正文和章节答案；`build.py`：生成 EPUB 与网页；`layout.py`：提供共用排版与读音导航函数。
- `assembled.json`、`chapters.md`：本次组装结果；`reading-coverage.json`、`build-report.json`：覆盖情况、数量与文件校验值。

## 校验记录

本次交付通过 EPUBCheck 5.3.0，错误与警告均为 0。结构检查验证了 5,793 个 EPUB 内部引用及 470 个网页的 114,345 个内部引用；手机检查覆盖 237 个页面，在 320px 宽度和 26px 字号下逐个点击全部 824 项读音导航，同时验证检索与假名开关。结果保存在 `qa/`。

如需复跑手机检查，先启动上述预览服务器，再运行：

```bash
pip install playwright
python -m playwright install chromium
python outputs/kanji-full-understanding-v3/qa_layout.py
```

`qa_layout.py` 支持用 `--base-url` 更换服务器地址、用 `--chromium-path` 指定已有浏览器。EPUB 格式复查可使用 EPUBCheck 5.3.0：

```bash
java -jar /path/to/epubcheck.jar \
  outputs/kanji-full-understanding-v3/日语为什么这样读_226字完整理解版.epub \
  --json outputs/kanji-full-understanding-v3/qa/epubcheck.json
```
