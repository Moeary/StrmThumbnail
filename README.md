# StrmThumbnail (Desktop)

Windows 桌面版 STRM 缩略图工具，专注于为 Emby/Jellyfin 生成 `poster/fanart/nfo`，并通过卡片化配置管理多个目录。

## 当前实现

- GUI：PySide6（QWidget）
- 调度：APScheduler（每卡片 Cron）
- 存储：SQLite（卡片配置与运行记录）
- 引擎：ffprobe/ffmpeg 抽帧 + NFO 生成
- 模式：全量 / 增量
- 限流：GUI 可选启用 `STRM_QPS`（建议风控场景设为 `0.3`）
- 输入源：`*.strm`，以及可选本地 `*.mp4/*.mkv`
- 设置：新增「设置」页，可配置允许处理的媒体格式（默认 `mp4,mkv`）

## 目录结构

```text
app/
	main.py
	core/
		network_guard.py
		runner.py
		scraper.py
		storage.py
	ui/
		main_window.py
		dialogs/
			profile_editor.py
config/
	strmthumbnail/
pixi.toml
plan.md
```

## 使用 Pixi 运行

1. 安装依赖

```bash
pixi install
```

2. 启动桌面应用

```bash
pixi run run
```

3. 快速语法检查

```bash
pixi run lint
```

## 说明

- 数据库路径：`config/strmthumbnail/app.db`
- 抽帧依赖 `ffmpeg/ffprobe`（已在 `pixi.toml` 声明）
- 全量模式会覆盖历史生成文件，切换时有确认
- 顶部 `限流QPS` 默认不启用（使用内置默认值 `0.5`）；启用后会设置进程内 `STRM_QPS`
- 新增/编辑卡片时可勾选 `包含本地媒体(按设置格式)`，用于直接刮削本机媒体文件
- `STRM` 文件会按其 URL 路径后缀参与过滤；例如设置仅 `mp4,mkv` 时，`.m4a` 链接会被自动跳过

## Git 忽略 DB 说明

- `.gitignore` 只对未跟踪文件生效；如果 `app.db` 曾被提交，后续仅补规则不会自动移出跟踪
- 可使用以下命令移除已跟踪数据库并保留本地文件：

```bash
git rm --cached config/strmthumbnail/app.db
```
