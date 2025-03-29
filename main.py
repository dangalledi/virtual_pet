import sys
from PyQt5.QtWidgets import QApplication
from penguin import PenguinCharacter

if __name__ == "__main__":
    app = QApplication(sys.argv)
    penguin = PenguinCharacter()
    penguin.show()
    penguin.setFocus()
    sys.exit(app.exec_())
