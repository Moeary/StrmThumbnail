from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QVBoxLayout
from qfluentwidgets import CheckBox, DoubleSpinBox, LineEdit, PrimaryPushButton, PushButton, SpinBox, isDarkTheme

from core.storage import Profile


class ProfileEditorDialog(QDialog):
    def __init__(self, profile: Profile, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑卡片")
        self.setMinimumWidth(520)
        self._profile = profile

        self.name_edit = LineEdit()
        self.name_edit.setText(profile.name)
        self.path_edit = LineEdit()
        self.path_edit.setText(profile.directory)
        self.threads_spin = SpinBox()
        self.threads_spin.setRange(1, 32)
        self.threads_spin.setValue(profile.threads)

        self.cron_edit = LineEdit()
        self.cron_edit.setText(profile.cron)

        self.enabled_check = CheckBox("启用卡片")
        self.enabled_check.setChecked(profile.enabled)

        self.scheduled_check = CheckBox("启用定时任务")
        self.scheduled_check.setChecked(profile.scheduled)

        self.nfo_check = CheckBox("生成 NFO")
        self.nfo_check.setChecked(profile.generate_nfo)

        self.overwrite_check = CheckBox("覆盖已存在文件")
        self.overwrite_check.setChecked(profile.overwrite_existing)

        self.poster_check = CheckBox("生成海报")
        self.poster_check.setChecked(profile.generate_poster)

        self.fanart_check = CheckBox("生成横图")
        self.fanart_check.setChecked(profile.generate_fanart)

        self.poster_pct_spin = DoubleSpinBox()
        self.poster_pct_spin.setDecimals(2)
        self.poster_pct_spin.setRange(0.01, 0.99)
        self.poster_pct_spin.setSingleStep(0.01)
        self.poster_pct_spin.setValue(profile.poster_pct)

        self.fanart_pct_spin = DoubleSpinBox()
        self.fanart_pct_spin.setDecimals(2)
        self.fanart_pct_spin.setRange(0.01, 0.99)
        self.fanart_pct_spin.setSingleStep(0.01)
        self.fanart_pct_spin.setValue(profile.fanart_pct)

        browse_button = PushButton("浏览")
        browse_button.clicked.connect(self._browse_directory)

        path_layout = QHBoxLayout()
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(browse_button)

        form = QFormLayout()
        form.setContentsMargins(8, 8, 8, 8)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        title = QLabel("编辑卡片")
        title.setStyleSheet("font-size:16px;font-weight:700;")
        form.addRow(title)
        form.addRow("卡片名称", self.name_edit)
        form.addRow("目录路径", path_layout)
        form.addRow("线程数", self.threads_spin)
        form.addRow("定时任务", self.cron_edit)
        form.addRow("", self.enabled_check)
        form.addRow("", self.scheduled_check)
        form.addRow("", self.nfo_check)
        form.addRow("", self.overwrite_check)
        form.addRow("", self.poster_check)
        form.addRow("海报抽帧百分比", self.poster_pct_spin)
        form.addRow("", self.fanart_check)
        form.addRow("横图抽帧百分比", self.fanart_pct_spin)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        cancel_btn = PushButton("取消")
        ok_btn = PrimaryPushButton("保存")
        cancel_btn.clicked.connect(self.reject)
        ok_btn.clicked.connect(self.accept)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(ok_btn)

        root = QVBoxLayout()
        root.setContentsMargins(12, 12, 12, 12)
        root.addLayout(form)
        root.addLayout(button_row)
        self.setLayout(root)
        self._apply_dialog_theme()

    def _apply_dialog_theme(self) -> None:
        if isDarkTheme():
            self.setStyleSheet(
                """
                QDialog { background-color: #202124; color: #f3f3f3; }
                QLabel { color: #f3f3f3; }
                """
            )
        else:
            self.setStyleSheet(
                """
                QDialog { background-color: #ffffff; color: #202124; }
                QLabel { color: #202124; }
                """
            )

    def _browse_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择目录", self.path_edit.text() or str(Path.home()))
        if selected:
            self.path_edit.setText(selected)

    def build_profile(self) -> Profile:
        return Profile(
            id=self._profile.id,
            name=self.name_edit.text().strip(),
            directory=self.path_edit.text().strip(),
            threads=self.threads_spin.value(),
            cron=self.cron_edit.text().strip() or "0 2 * * *",
            enabled=self.enabled_check.isChecked(),
            scheduled=self.scheduled_check.isChecked(),
            generate_nfo=self.nfo_check.isChecked(),
            overwrite_existing=self.overwrite_check.isChecked(),
            generate_poster=self.poster_check.isChecked(),
            generate_fanart=self.fanart_check.isChecked(),
            poster_pct=self.poster_pct_spin.value(),
            fanart_pct=self.fanart_pct_spin.value(),
        )
