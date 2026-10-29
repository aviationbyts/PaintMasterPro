import os, sys, logging
if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))
from pm.config import LOG_FILE

logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")


def main():
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtGui import QIcon
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PaintMasterPro.App")
        except Exception:
            pass
    app = QApplication(sys.argv)
    from pm.ui import MainWindow, STYLE
    app.setStyleSheet(STYLE)
    try:
        w = MainWindow()
    except Exception as e:
        logging.exception("start mislukt")
        QMessageBox.critical(None, "PaintMaster Pro", f"Het programma kon niet starten:\n{e}")
        return 1
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.excepthook = lambda *a: logging.error("Onverwachte fout", exc_info=a)
    sys.exit(main())
