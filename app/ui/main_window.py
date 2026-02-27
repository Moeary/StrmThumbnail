from __future__ import annotations

import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CheckBox,
    FluentIcon as FIF,
    FluentWindow,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    SearchLineEdit,
    SimpleCardWidget,
    SpinBox,
    TableWidget,
    TextEdit,
    Theme,
    TransparentToolButton,
    isDarkTheme,
    setTheme,
)

from core.runner import Runner
from core.storage import Profile, Storage
from ui.dialogs.profile_editor import ProfileEditorDialog


class UISignals(QObject):
    log = Signal(str)
    progress = Signal(dict)
    finished = Signal(dict)


class MainWindow(FluentWindow):
    def __init__(self, db_path: Path):
        setTheme(Theme.DARK)
        super().__init__()
        self.setWindowTitle("StrmThumbnail Desktop")

        self.storage = Storage(db_path)
        self.runner = Runner(self.storage)
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()

        self.signals = UISignals()
        self.signals.log.connect(self.append_log)
        self.signals.progress.connect(self.update_stats)
        self.signals.finished.connect(self.on_run_finished)

        self._current_mode = "incremental"
        self._running = False
        self._project_name = "test"

        self.dashboard = QWidget(self)
        self.dashboard.setObjectName("dashboard")
        self.addSubInterface(self.dashboard, FIF.APPLICATION, "任务计划")

        self.root_layout = QVBoxLayout(self.dashboard)
        self.root_layout.setContentsMargins(12, 12, 12, 12)
        self.root_layout.setSpacing(10)

        self._build_top_bar()
        self._build_body()
        self.refresh_profiles()
        self._apply_theme()

    def _build_top_bar(self) -> None:
        row = QHBoxLayout()
        title = QLabel("任务计划")
        title.setStyleSheet("font-size:22px;font-weight:700;")
        row.addWidget(title)
        row.addStretch(1)

        row.addWidget(BodyLabel("项目名"))
        self.project_name_input = LineEdit()
        self.project_name_input.setText(self._project_name)
        self.project_name_input.setFixedWidth(180)
        row.addWidget(self.project_name_input)

        github_btn = TransparentToolButton(FIF.GITHUB)
        github_btn.setToolTip("GitHub")
        github_btn.clicked.connect(lambda: webbrowser.open("https://github.com"))
        row.addWidget(github_btn)

        self.theme_btn = PushButton("浅色/深色")
        self.theme_btn.clicked.connect(self.toggle_theme)
        row.addWidget(self.theme_btn)

        self.mode_btn = PushButton("模式：增量")
        self.mode_btn.clicked.connect(self.toggle_mode)
        row.addWidget(self.mode_btn)

        run_all_btn = PrimaryPushButton("运行全部卡片")
        run_all_btn.clicked.connect(self.run_all_profiles)
        row.addWidget(run_all_btn)

        self.root_layout.addLayout(row)

    def _build_body(self) -> None:
        main = QHBoxLayout()
        self.root_layout.addLayout(main)

        left = QVBoxLayout()
        right = QVBoxLayout()
        main.addLayout(left, 1)
        main.addLayout(right, 2)

        status_box = SimpleCardWidget()
        status_layout = QHBoxLayout()
        status_title = QLabel("任务状态")
        status_title.setStyleSheet("font-size:14px;font-weight:600;")
        status_layout.addWidget(status_title)
        self.progress_label = QLabel("进度 0/0")
        self.success_label = QLabel("成功 0")
        self.failed_label = QLabel("失败 0")
        self.skipped_label = QLabel("跳过 0")
        self.elapsed_label = QLabel("耗时 0.0s")
        for widget in [
            self.progress_label,
            self.success_label,
            self.failed_label,
            self.skipped_label,
            self.elapsed_label,
        ]:
            status_layout.addWidget(widget)
        status_layout.addStretch(1)
        status_box.setLayout(status_layout)
        left.addWidget(status_box)

        log_box = SimpleCardWidget()
        log_layout = QVBoxLayout()
        log_layout.addWidget(QLabel("实时日志"))
        self.log_text = TextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        log_box.setLayout(log_layout)
        left.addWidget(log_box)

        add_box = SimpleCardWidget()
        add_form = QFormLayout()
        self.name_input = LineEdit()
        self.path_input = LineEdit()
        self.threads_input = SpinBox()
        self.threads_input.setRange(1, 32)
        self.threads_input.setValue(4)
        self.cron_input = LineEdit()
        self.cron_input.setText("0 2 * * *")

        path_row = QHBoxLayout()
        path_row.addWidget(self.path_input)
        browse_btn = PushButton("浏览")
        browse_btn.clicked.connect(self.pick_directory)
        path_row.addWidget(browse_btn)

        add_form.addRow(QLabel("新增卡片"))
        add_form.addRow("卡片名称", self.name_input)
        add_form.addRow("目录路径", path_row)
        add_form.addRow("线程数", self.threads_input)
        add_form.addRow("定时任务", self.cron_input)

        self.new_enable_check = CheckBox("启用卡片")
        self.new_enable_check.setChecked(True)
        self.new_schedule_check = CheckBox("启用定时任务")
        self.new_schedule_check.setChecked(True)
        add_form.addRow("", self.new_enable_check)
        add_form.addRow("", self.new_schedule_check)

        add_btn = PrimaryPushButton("新增卡片")
        add_btn.clicked.connect(self.create_profile)
        add_form.addRow("", add_btn)
        add_box.setLayout(add_form)
        right.addWidget(add_box)

        search_row = QHBoxLayout()
        self.search_input = SearchLineEdit()
        self.search_input.setPlaceholderText("搜索卡片名称/路径")
        self.search_input.textChanged.connect(self.refresh_profiles)
        search_row.addWidget(self.search_input)
        right.addLayout(search_row)

        table_card = SimpleCardWidget()
        table_layout = QVBoxLayout(table_card)
        self.table = TableWidget()
        self.table.setRowCount(0)
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["ID", "名称", "目录", "线程", "Cron", "启用", "定时", "操作"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 260)
        self.table.setColumnWidth(3, 80)
        self.table.setColumnWidth(4, 120)
        self.table.setColumnWidth(5, 70)
        self.table.setColumnWidth(6, 70)
        self.table.setColumnWidth(7, 260)
        table_layout.addWidget(self.table)
        right.addWidget(table_card)

    def append_log(self, message: str) -> None:
        now = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{now}] {message}")

    def toggle_theme(self) -> None:
        setTheme(Theme.LIGHT if isDarkTheme() else Theme.DARK)
        self._apply_theme()

    def _apply_theme(self) -> None:
        self.theme_btn.setText("切换浅色" if isDarkTheme() else "切换深色")

    def toggle_mode(self) -> None:
        if self._current_mode == "incremental":
            confirm = QMessageBox.question(self, "切换模式", "全量模式将覆盖已有文件，确认切换？")
            if confirm != QMessageBox.StandardButton.Yes:
                return
            self._current_mode = "full"
            self.mode_btn.setText("模式：全量")
        else:
            self._current_mode = "incremental"
            self.mode_btn.setText("模式：增量")

    def pick_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择目录", self.path_input.text() or str(Path.home()))
        if selected:
            self.path_input.setText(selected)

    def create_profile(self) -> None:
        name = self.name_input.text().strip()
        directory = self.path_input.text().strip()
        if not name or not directory:
            QMessageBox.warning(self, "参数不完整", "请填写卡片名称和目录路径")
            return

        profile = Profile(
            id=None,
            name=name,
            directory=directory,
            threads=self.threads_input.value(),
            cron=self.cron_input.text().strip() or "0 2 * * *",
            enabled=self.new_enable_check.isChecked(),
            scheduled=self.new_schedule_check.isChecked(),
        )
        self.storage.create_profile(profile)
        self.name_input.clear()
        self.path_input.clear()
        self.append_log(f"[create] {name}")
        self.refresh_profiles()

    def refresh_profiles(self) -> None:
        profiles = self.storage.list_profiles(self.search_input.text().strip() if hasattr(self, "search_input") else "")
        self.table.setRowCount(len(profiles))

        for row, profile in enumerate(profiles):
            self.table.setItem(row, 0, QTableWidgetItem(str(profile.id)))
            self.table.setItem(row, 1, QTableWidgetItem(profile.name))
            self.table.setItem(row, 2, QTableWidgetItem(profile.directory))
            self.table.setItem(row, 3, QTableWidgetItem(str(profile.threads)))
            self.table.setItem(row, 4, QTableWidgetItem(profile.cron))
            self.table.setItem(row, 5, QTableWidgetItem("是" if profile.enabled else "否"))
            self.table.setItem(row, 6, QTableWidgetItem("是" if profile.scheduled else "否"))

            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(2, 2, 2, 2)
            actions_layout.setSpacing(6)

            edit_btn = PushButton("修改")
            edit_btn.clicked.connect(lambda _, pid=profile.id: self.edit_profile(pid))
            toggle_btn = PushButton("停用" if profile.enabled else "启用")
            toggle_btn.clicked.connect(lambda _, pid=profile.id: self.toggle_profile(pid))
            run_btn = PushButton("运行")
            run_btn.clicked.connect(lambda _, pid=profile.id: self.run_single_profile(pid))
            del_btn = PushButton("删除")
            del_btn.clicked.connect(lambda _, pid=profile.id: self.delete_profile(pid))

            for btn in [edit_btn, toggle_btn, run_btn, del_btn]:
                btn.setMinimumWidth(54)
                btn.setFixedHeight(32)
                actions_layout.addWidget(btn)

            self.table.setCellWidget(row, 7, actions)

        self._sync_scheduler()

    def edit_profile(self, profile_id: int | None) -> None:
        if profile_id is None:
            return
        profile = self.storage.get_profile(profile_id)
        if not profile:
            return

        dialog = ProfileEditorDialog(profile, self)
        if dialog.exec():
            updated = dialog.build_profile()
            if not updated.name or not updated.directory:
                QMessageBox.warning(self, "参数不完整", "卡片名称和目录路径不能为空")
                return
            self.storage.update_profile(updated)
            self.append_log(f"[update] {updated.name}")
            self.refresh_profiles()

    def toggle_profile(self, profile_id: int | None) -> None:
        if profile_id is None:
            return
        profile = self.storage.get_profile(profile_id)
        if not profile:
            return
        profile.enabled = not profile.enabled
        self.storage.update_profile(profile)
        self.append_log(f"[toggle] {profile.name} -> {'on' if profile.enabled else 'off'}")
        self.refresh_profiles()

    def delete_profile(self, profile_id: int | None) -> None:
        if profile_id is None:
            return
        profile = self.storage.get_profile(profile_id)
        if not profile:
            return
        confirm = QMessageBox.question(self, "删除确认", f"确认删除卡片：{profile.name}？")
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.storage.delete_profile(profile_id)
        self.append_log(f"[delete] {profile.name}")
        self.refresh_profiles()

    def run_all_profiles(self) -> None:
        if self._running:
            QMessageBox.information(self, "任务运行中", "当前已有任务在运行")
            return
        profiles = self.storage.list_profiles()
        self._start_run(profiles)

    def run_single_profile(self, profile_id: int | None) -> None:
        if self._running:
            QMessageBox.information(self, "任务运行中", "当前已有任务在运行")
            return
        if profile_id is None:
            return
        profile = self.storage.get_profile(profile_id)
        if not profile:
            return
        self._start_run([profile])

    def _start_run(self, profiles: list[Profile]) -> None:
        self._running = True
        self.append_log(f"[start] profiles={len(profiles)} mode={self._current_mode}")

        def worker() -> None:
            start = time.time()
            stats = self.runner.run_profiles(
                profiles,
                mode=self._current_mode,
                on_log=lambda msg: self.signals.log.emit(msg),
                on_progress=lambda payload: self.signals.progress.emit(payload),
            )
            self.signals.finished.emit(stats.to_dict() | {"elapsed": time.time() - start})

        threading.Thread(target=worker, daemon=True).start()

    def update_stats(self, payload: dict) -> None:
        done = payload.get("done", 0)
        total = payload.get("total", 0)
        self.progress_label.setText(f"进度 {done}/{total}")
        self.success_label.setText(f"成功 {payload.get('success', 0)}")
        self.failed_label.setText(f"失败 {payload.get('failed', 0)}")
        self.skipped_label.setText(f"跳过 {payload.get('skipped', 0)}")
        self.elapsed_label.setText(f"耗时 {payload.get('elapsed', 0):.1f}s")

    def on_run_finished(self, payload: dict) -> None:
        self._running = False
        self.update_stats(payload)
        self.append_log(
            "[done] success={success} failed={failed} skipped={skipped} elapsed={elapsed:.1f}s".format(
                success=payload.get("success", 0),
                failed=payload.get("failed", 0),
                skipped=payload.get("skipped", 0),
                elapsed=payload.get("elapsed", 0.0),
            )
        )

    def _sync_scheduler(self) -> None:
        expected_ids: set[str] = set()
        for profile in self.storage.list_profiles():
            job_id = f"profile-{profile.id}"
            if profile.enabled and profile.scheduled:
                expected_ids.add(job_id)
                if self.scheduler.get_job(job_id) is None:
                    try:
                        trigger = CronTrigger.from_crontab(profile.cron)
                    except ValueError:
                        self.append_log(f"[cron-invalid] {profile.name}: {profile.cron}")
                        continue
                    self.scheduler.add_job(
                        lambda pid=profile.id: self._run_scheduled(pid),
                        trigger=trigger,
                        id=job_id,
                        replace_existing=True,
                    )
            else:
                job = self.scheduler.get_job(job_id)
                if job is not None:
                    self.scheduler.remove_job(job_id)

        for job in self.scheduler.get_jobs():
            if job.id.startswith("profile-") and job.id not in expected_ids:
                self.scheduler.remove_job(job.id)

    def _run_scheduled(self, profile_id: int | None) -> None:
        if self._running or profile_id is None:
            return
        profile = self.storage.get_profile(profile_id)
        if not profile:
            return
        self.signals.log.emit(f"[schedule] start profile={profile.name}")
        self._start_run([profile])

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.scheduler.shutdown(wait=False)
        super().closeEvent(event)
