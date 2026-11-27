# SPDX-License-Identifier: LicenseRef-Volnist
"""Launch the WSM preview-only PySide6/Kirigami interface."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from .controller import PreviewController


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wsm-installer")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="load QML offscreen and exit without collecting hardware information",
    )
    args = parser.parse_args(argv)

    app = QGuiApplication(sys.argv[:1])
    app.setApplicationName("WSM Installer")
    app.setApplicationVersion("0.1.0")
    controller = PreviewController()
    engine = QQmlApplicationEngine()
    for path in os.environ.get("QML_IMPORT_PATH", "").split(os.pathsep):
        if path:
            engine.addImportPath(path)
    engine.rootContext().setContextProperty("wsmController", controller)

    qml_path = Path(__file__).resolve().parent / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    if not engine.rootObjects():
        return 1

    if args.smoke_test:
        QTimer.singleShot(0, app.quit)
    else:
        controller.refresh()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
