# StrmThumbnail (Desktop)

Windows 桌面版 STRM 缩略图工具，专注于为 Emby/Jellyfin 生成 `poster/fanart/nfo`，并通过卡片化配置管理多个目录。

## 当前实现

- GUI：PySide6（QWidget）
- 调度：APScheduler（每卡片 Cron）
- 存储：SQLite（卡片配置与运行记录）
- 引擎：ffprobe/ffmpeg 抽帧 + NFO 生成
- 模式：全量 / 增量

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
