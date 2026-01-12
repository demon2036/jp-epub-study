# iOS 日语单词 PWA 实施方案（N5-N1 词库）

面向通勤场景的 iPhone 日语单词学习 PWA，不上架 App Store，不需要提醒、统计和算法，只提供分级词库与便捷浏览/记忆。

## 目标与边界
- 目标：通勤碎片化学习，最快进入单词浏览与记忆
- 设备：iPhone（无 Mac）
- 形态：PWA（可添加到主屏幕、可离线）
- 功能边界：只做 N5–N1 词库与浏览/搜索/收藏，不做提醒、统计、算法

## 词库准备
- 词库范围：N5、N4、N3、N2、N1
- 数据字段（最小集）：
  - `kanji`：汉字（无汉字则为空或与 `kana` 一致）
  - `kana`：假名
  - `meaning_zh`：中文释义
  - `level`：N1–N5
  - 可选：`example`（例句）
- 数据来源：
  - 选择可公开使用或授权的数据源
  - 保留来源与授权说明（放在 About/数据来源页）
- 数据格式：
  - 每个等级一个 JSON 文件：`/data/n5.json` ... `/data/n1.json`
  - 纯 UTF-8 文本，无二进制依赖

## 功能清单
### 必要功能
- 等级选择页：N5 → N1
- 单词卡片页：
  - 显示单词（kanji/kana）
  - 点击显示释义
  - 上一张/下一张
- 列表页：
  - 按等级分页浏览
  - 关键词搜索（kanji/kana/中文）
- 收藏：
  - 可标记/取消收藏
  - 仅本地保存

### 非必要功能（本期不做）
- 提醒/通知
- 统计/打卡
- 记忆算法/复习计划

## 页面与交互
- 首页
  - 等级按钮（N5–N1）
  - 最近浏览入口（本地记录当前位置）
- 卡片页
  - 轻触显示释义
  - 左右滑或按钮切换
  - 收藏按钮
- 列表页
  - 搜索框
  - 单词列表
  - 点击进入卡片页当前位置
- 关于页
  - 数据来源与授权说明

## 技术方案（PWA）
### 前端技术
- 任意前端栈（原生 JS/React/Vue）均可
- 建议：原生 JS + 简单模板，减少依赖，提升加载速度

### 离线能力
- Service Worker：
  - 缓存静态资源（HTML/CSS/JS/图标）
  - 缓存词库 JSON
  - 首次加载后可离线打开

### 本地存储
- 收藏与当前位置：
  - `localStorage` 或 `IndexedDB`
  - 简单场景优先 `localStorage`

### PWA 配置
- `manifest.json`：
  - `name`、`short_name`、`icons`、`start_url`、`display: standalone`
- 图标：
  - 至少 180x180 和 512x512

## 项目结构建议
```
/ (项目根目录)
  index.html
  /css
    app.css
  /js
    app.js
    db.js
  /data
    n5.json
    n4.json
    n3.json
    n2.json
    n1.json
  /assets
    icons/
      icon-180.png
      icon-512.png
  manifest.json
  service-worker.js
```

## 关键实现说明
- 单词加载：
  - 进入等级后加载对应 JSON
  - 列表与卡片共用同一份数据
- 搜索：
  - 基于本地数组过滤（kanji/kana/meaning_zh）
- 收藏：
  - 本地保存 word id（可用 `level + index` 作为 id）
- 当前位置记录：
  - 记住每个等级上次浏览索引

## 部署方案（无 Mac）
- 选择任意静态托管（需 HTTPS）：
  - GitHub Pages / Vercel / Netlify / Cloudflare Pages
- 部署步骤：
  1) 上传静态文件
  2) 开启 HTTPS
  3) 确认 `manifest.json` 与 `service-worker.js` 可访问

## iPhone 安装方式（PWA）
1) 用 Safari 打开你的 PWA 地址（必须是 HTTPS）
2) 点击分享按钮
3) 选择“添加到主屏幕”
4) 从主屏幕启动即可离线使用（首次加载完成后）

## 测试与验证清单
- iPhone Safari 首次打开可正常加载词库
- 断网后可正常打开
- 收藏与当前位置在刷新后仍保留
- 添加到主屏幕后图标与启动正常

## 交付物清单
- 前端静态代码（HTML/CSS/JS）
- N5–N1 词库 JSON
- PWA 配置与图标
- 说明文档（数据来源与使用说明）

## 风险与注意事项
- 词库版权与授权必须清晰
- iOS PWA 无法后台常驻，需前台打开
- iOS PWA 可能对存储容量有限制
