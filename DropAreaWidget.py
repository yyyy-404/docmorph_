from PySide6.QtWidgets import QLabel, QSizePolicy
from PySide6.QtCore import Qt, Signal

class DropAreaWidget(QLabel):
    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setText("📥 拖拽文件到这里进行转换")
        self.setAlignment(Qt.AlignCenter)
        self.setAcceptDrops(True)
        self.setProperty("dragging", False)
        self.setObjectName("DropArea")  # ✅ 设置用于样式表匹配的对象名
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(120)  # ✅ 拖拽区域可见

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("dragging", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event):
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event):
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        self.files_dropped.emit(paths)
