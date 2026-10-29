import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from pm.logo import make_logo
from PIL import Image

app = QApplication(sys.argv)
os.makedirs("assets", exist_ok=True)
make_logo(256).save("assets/icon.png")
Image.open("assets/icon.png").save("assets/icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("assets/icon.ico gemaakt")
