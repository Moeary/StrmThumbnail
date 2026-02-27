from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("StrmThumbnail")
    app.setOrganizationName("StrmThumbnail")

    db_path = Path("config") / "strmthumbnail" / "app.db"
    window = MainWindow(db_path=db_path)
    window.resize(1200, 760)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
