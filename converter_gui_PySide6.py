import os
import sys
import glob
import threading
import configparser
from datetime import datetime
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QFileDialog,
    QVBoxLayout, QHBoxLayout, QComboBox, QProgressBar, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from FilesChange import DocumentConverter  # 假设 DocumentConverter 在 FilesChange.py 中
from DropAreaWidget import DropAreaWidget  # 假设 DropAreaWidget 在 DropAreaWidget.py 中


# --- 定义一个 Worker 线程来执行耗时操作 ---
class ConversionWorker(QThread):
    # 定义信号，用于向主线程发送结果和进度
    conversion_finished = Signal(bool, str)  # 成功状态，消息
    progress_updated = Signal(int)  # 当前进度值
    file_converted = Signal(str, str, str)  # 文件路径，状态，消息

    def __init__(self, converter: DocumentConverter, file_paths: list, output_dir: str,
                 from_format: str, to_format: str, is_batch_mode: bool = False, parent=None):
        super().__init__(parent)
        self.converter = converter
        self.file_paths = file_paths
        self.output_dir = output_dir
        self.from_format = from_format
        self.to_format = to_format
        self.is_batch_mode = is_batch_mode
        self.failed_files = []

    def run(self):
        success_count = 0
        total_files = len(self.file_paths)
        self.failed_files = []

        if self.is_batch_mode:
            for idx, file_path in enumerate(self.file_paths):
                from_fmt = Path(file_path).suffix[1:].lower()
                if self.to_format not in self.converter.get_supported_conversions(from_fmt):
                    self.failed_files.append(file_path)
                    self.file_converted.emit(file_path, "SKIPPED", f"不支持从 {from_fmt} 到 {self.to_format}")
                    self.progress_updated.emit(int(((idx + 1) / total_files) * 100))
                    continue

                out_file = os.path.join(self.output_dir, f"{Path(file_path).stem}.{self.to_format}")
                if os.path.exists(out_file) and not self.converter.overwrite_output:
                    self.file_converted.emit(file_path, "SKIPPED", "目标已存在，跳过")
                    self.progress_updated.emit(int(((idx + 1) / total_files) * 100))
                    continue

                try:
                    if self.converter.convert(file_path, out_file, from_fmt, self.to_format):
                        success_count += 1
                        self.file_converted.emit(file_path, "SUCCESS", f"转换为 {out_file}")
                    else:
                        self.failed_files.append(file_path)
                        self.file_converted.emit(file_path, "FAILED", "转换器报告失败")
                except Exception as e:
                    self.failed_files.append(file_path)
                    self.file_converted.emit(file_path, "ERROR", str(e))

                self.progress_updated.emit(int(((idx + 1) / total_files) * 100))

            msg = f"已尝试转换 {total_files} 个文件，成功 {success_count} 个"
            if self.failed_files:
                msg += f"\n❌ 失败 {len(self.failed_files)} 个:\n" + "\n".join(Path(f).name for f in self.failed_files)
            self.conversion_finished.emit(True, msg)

        else:  # 单文件或拖拽多文件转换
            if not self.file_paths:
                self.conversion_finished.emit(False, "没有文件需要转换。")
                return

            try:
                for idx, file_path in enumerate(self.file_paths):
                    from_fmt = Path(file_path).suffix[1:].lower()
                    out_file = os.path.join(self.output_dir, f"{Path(file_path).stem}.{self.to_format}")
                    if self.converter.convert(file_path, out_file, from_fmt, self.to_format):
                        success_count += 1
                        self.file_converted.emit(file_path, "SUCCESS", f"转换成功为 {out_file}")
                    else:
                        self.failed_files.append(file_path)
                        self.file_converted.emit(file_path, "FAILED", "转换器报告失败")
                    self.progress_updated.emit(int(((idx + 1) / total_files) * 100))

                msg = f"✅ 成功转换 {success_count} 个文件"
                if self.failed_files:
                    msg += f"\n❌ 失败 {len(self.failed_files)} 个:\n" + "\n".join(
                        Path(f).name for f in self.failed_files)
                self.conversion_finished.emit(True, msg)
            except Exception as e:
                self.conversion_finished.emit(False, f"转换发生错误: {e}")
                self.file_converted.emit("N/A", "ERROR", f"转换发生错误: {e}")


class DocumentConverterGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("📄 文档格式转换器 - PySide6")
        self.setFixedSize(600, 360)
        self.config = configparser.ConfigParser()
        self._load_config()
        self.input_paths = []  # 存储选中的文件路径列表
        self.current_input_type = "file"  # "file" 或 "folder"
        self.failed_files = []  # 记录转换失败的文件
        self.to_format = self.config.get("Defaults", "default_general_to_format", fallback="pdf")
        self.overwrite_output = self.config.getboolean("Settings", "overwrite_output", fallback=False)
        pdf_engine = self.config.get("Defaults", "default_pdf_engine", fallback="weasyprint")
        self.converter = DocumentConverter(pdf_engine=pdf_engine, overwrite=self.overwrite_output, gui_mode=True)
        self._setup_ui()
        os.makedirs(self.input_path_line_edit.text(), exist_ok=True)
        os.makedirs(self.output_path_line_edit.text(), exist_ok=True)
        self._load_stylesheet()  # 样式表在 UI 设置后加载，可以覆盖默认样式
        self._update_format_combos_initial()
        QApplication.instance().aboutToQuit.connect(self._flush_logs_on_exit)

    def _flush_logs_on_exit(self):
        try:
            self.converter._flush_log_buffer()
            print("GUI 退出时，日志缓冲区已刷新。")
        except Exception as e:
            print(f"退出时刷新日志失败: {e}")

    def _setup_ui(self):
        layout = QVBoxLayout()
        # 输入路径和按钮
        self.input_path_line_edit = QLineEdit(self.config.get("Paths", "input_directory", fallback="input"))

        # 保存为类属性（关键修复）
        self.btn_select_files = QPushButton("📁 选择多个文件")
        self.btn_select_folder = QPushButton("📂 选择文件夹")

        self.btn_select_files.clicked.connect(self.select_input_files)
        self.btn_select_folder.clicked.connect(self.select_input_folder)

        h_input = QHBoxLayout()
        h_input.addWidget(QLabel("输入路径:"))
        h_input.addWidget(self.input_path_line_edit)
        h_input.addWidget(self.btn_select_files)
        h_input.addWidget(self.btn_select_folder)
        layout.addLayout(h_input)

        # 输出目录一行
        self.output_path_line_edit = QLineEdit(self.config.get("Paths", "output_directory", fallback="output"))

        # 保存为类属性
        self.btn_output = QPushButton("📂 浏览输出目录")

        self.btn_output.clicked.connect(self.select_output_folder)

        h_output = QHBoxLayout()
        h_output.addWidget(QLabel("输出目录:"))
        h_output.addWidget(self.output_path_line_edit)
        h_output.addWidget(self.btn_output)
        layout.addLayout(h_output)

        # 拖拽区域
        self.drop_area = DropAreaWidget()
        self.drop_area.setFixedHeight(100)
        self.drop_area.files_dropped.connect(self.handle_dropped_files)
        layout.addWidget(self.drop_area)

        # 源格式和目标格式一行
        self.combo_from_format = QComboBox()
        self.combo_to_format = QComboBox()
        self.combo_from_format.currentTextChanged.connect(self._update_to_format_combo)

        h_format = QHBoxLayout()
        h_format.addWidget(QLabel("源格式:"))
        h_format.addWidget(self.combo_from_format)
        h_format.addWidget(QLabel("目标格式:"))
        h_format.addWidget(self.combo_to_format)
        layout.addLayout(h_format)

        # 转换按钮
        self.btn_convert = QPushButton("🚀 执行转换")
        self.btn_quick = QPushButton("⚡ 批量转换输入目录")

        self.btn_convert.clicked.connect(self.start_conversion_task)
        self.btn_quick.clicked.connect(self.quick_convert_input_folder)

        h_buttons = QHBoxLayout()
        h_buttons.addWidget(self.btn_convert)
        h_buttons.addWidget(self.btn_quick)
        layout.addLayout(h_buttons)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(10)  # 设置进度条高度为 10 像素
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.setLayout(layout)

    def _update_format_combos_initial(self):
        supported_input_formats = sorted(self.converter.supported_conversions.keys())
        self.combo_from_format.addItems(supported_input_formats)
        if supported_input_formats:
            self.combo_from_format.setCurrentText(supported_input_formats[0])
        self._update_to_format_combo(self.combo_from_format.currentText())

    def _update_to_format_combo(self, from_format: str):
        formats = self.converter.get_supported_conversions(from_format)
        self.combo_to_format.clear()
        if formats:
            self.combo_to_format.addItems(formats)
            default_key = f"default_{from_format}_to_format"
            default_target = self.config.get("Defaults", default_key, fallback=formats[0])
            if default_target in formats:
                self.combo_to_format.setCurrentText(default_target)
            else:
                self.combo_to_format.setCurrentText(formats[0])

    def handle_dropped_files(self, paths: list[str]):
        if not paths:
            return
        if len(paths) == 1 and os.path.isdir(paths[0]):
            self.input_path_line_edit.setText(paths[0])
            self.current_input_type = "folder"
            self.quick_convert_input_folder()
            QMessageBox.information(self, "目录拖拽成功", f"已拖入目录：{paths[0]}，将自动批量转换。")
            return

        supported_files = []
        for p in paths:
            if os.path.isfile(p):
                ext = Path(p).suffix[1:].lower()
                if ext in self.converter.supported_conversions:
                    supported_files.append(p)
                else:
                    QMessageBox.warning(self, "不支持的文件",
                                        f"文件类型 '{ext}' (来自 {os.path.basename(p)}) 暂不支持转换。")

        if supported_files:
            self.input_paths = supported_files
            self.current_input_type = "file"
            first_file_ext = Path(supported_files[0]).suffix[1:].lower()
            if first_file_ext in self.converter.supported_conversions:
                self.combo_from_format.setCurrentText(first_file_ext)
            self.input_path_line_edit.setText(f"{len(supported_files)} 个文件已选择...")
            QMessageBox.information(self, "文件拖拽成功", f"已添加 {len(supported_files)} 个文件。")
        else:
            QMessageBox.warning(self, "无支持文件", "拖入的文件中没有支持转换的类型。")

    def _load_stylesheet(self, file_path="style.css"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        except Exception as e:
            print(f"[样式表加载失败] {e}")

    def _load_config(self):
        config_file = "config.ini"
        self.config['Paths'] = {
            'input_directory': 'input',
            'output_directory': 'output',
            'log_directory': 'logs'
        }
        self.config['Defaults'] = {
            'default_docx_to_format': 'pdf',
            'default_pdf_to_format': 'docx',
            'default_general_to_format': 'pdf',
            'default_pdf_engine': 'weasyprint'
        }
        self.config['Settings'] = {
            'overwrite_output': 'No',
            'pdf_chunk_size': '2'
        }
        if os.path.exists(config_file):
            self.config.read(config_file, encoding="utf-8")
        else:
            try:
                with open(config_file, 'w', encoding="utf-8") as f:
                    self.config.write(f)
                print(f"ℹ️ 已创建默认配置文件: {config_file}")
            except IOError as e:
                print(f"⚠️ 无法创建配置文件 {config_file}: {e}。将使用内存中的默认设置。")

    def select_input_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择多个源文件", self.input_path_line_edit.text())
        if files:
            self.input_paths = files
            self.current_input_type = "file"
            first_file_ext = Path(files[0]).suffix[1:].lower()
            if first_file_ext in self.converter.supported_conversions:
                self.combo_from_format.setCurrentText(first_file_ext)
            self.input_path_line_edit.setText(f"{len(files)} 个文件已选择...")
            QMessageBox.information(self, "文件选择", f"已选择 {len(files)} 个文件。")

    def select_input_folder(self):
        path = QFileDialog.getExistingDirectory(self, "选择文件夹", self.input_path_line_edit.text())
        if path:
            self.input_path_line_edit.setText(path)
            self.input_paths = []
            self.current_input_type = "folder"
            QMessageBox.information(self, "目录选择", f"已选择目录：{path}，将在批量模式下处理。")

    def select_output_folder(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_path_line_edit.text())
        if path:
            self.output_path_line_edit.setText(path)

    def start_conversion_task(self):
        if not self.input_paths:
            QMessageBox.warning(self, "错误", "请先选择要转换的文件。")
            return

        from_fmt = self.combo_from_format.currentText()
        to_fmt = self.combo_to_format.currentText()
        output_dir = self.output_path_line_edit.text()

        if not to_fmt:
            QMessageBox.warning(self, "错误", "请选择目标格式。")
            return

        if to_fmt not in self.converter.get_supported_conversions(from_fmt):
            QMessageBox.warning(self, "错误", f"不支持从 {from_fmt} 转换为 {to_fmt}。")
            return

        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(100)
        self.failed_files = []

        self.worker_thread = ConversionWorker(
            converter=self.converter,
            file_paths=self.input_paths,
            output_dir=output_dir,
            from_format=from_fmt,
            to_format=to_fmt,
            is_batch_mode=False
        )

        self.worker_thread.conversion_finished.connect(self.on_conversion_finished)
        self.worker_thread.progress_updated.connect(self.progress_bar.setValue)
        self.worker_thread.file_converted.connect(self.on_file_converted)
        self.worker_thread.start()

        self.set_ui_enabled(False)

    def quick_convert_input_folder(self):
        input_dir = self.input_path_line_edit.text()
        output_dir = self.output_path_line_edit.text()
        to_fmt = self.combo_to_format.currentText()

        if not os.path.isdir(input_dir):
            QMessageBox.warning(self, "错误", "输入路径不是一个有效的目录。")
            return

        if not to_fmt:
            QMessageBox.warning(self, "错误", "请选择目标格式。")
            return

        all_files_to_convert = []
        for from_fmt in self.converter.supported_conversions.keys():
            all_files_to_convert.extend(glob.glob(os.path.join(input_dir, f"**/*.{from_fmt}"), recursive=True))

        if not all_files_to_convert:
            QMessageBox.information(self, "提示", f"在 '{input_dir}' 中没有找到任何支持转换的文件。")
            return

        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(100)
        self.failed_files = []

        self.worker_thread = ConversionWorker(
            converter=self.converter,
            file_paths=all_files_to_convert,
            output_dir=output_dir,
            from_format=None,
            to_format=to_fmt,
            is_batch_mode=True
        )

        self.worker_thread.conversion_finished.connect(self.on_conversion_finished)
        self.worker_thread.progress_updated.connect(self.progress_bar.setValue)
        self.worker_thread.file_converted.connect(self.on_file_converted)
        self.worker_thread.start()

        self.set_ui_enabled(False)

    def on_file_converted(self, file_path: str, status: str, message: str):
        self.converter.write_log(status, file_path, message)
        if status in ("FAILED", "ERROR"):
            self.failed_files.append(file_path)

    def on_conversion_finished(self, success: bool, message: str):
        self.set_ui_enabled(True)
        self.progress_bar.setValue(100)

        final_msg = message
        if self.failed_files:
            final_msg += f"\n❌ 失败文件:\n" + "\n".join(Path(f).name for f in self.failed_files)
            QMessageBox.warning(self, "转换完成 (有错误)", final_msg)
        else:
            QMessageBox.information(self, "转换完成", final_msg)

        self.worker_thread.quit()
        self.worker_thread.wait()
        self.worker_thread = None

    def set_ui_enabled(self, enabled: bool):
        """安全地启用/禁用所有UI控件，包含空值检查"""
        # 确保所有控件都已初始化
        if not hasattr(self, 'input_path_line_edit') or self.input_path_line_edit is None:
            return

        # 为每个控件添加空值检查
        if hasattr(self, 'input_path_line_edit') and self.input_path_line_edit:
            self.input_path_line_edit.setEnabled(enabled)
        if hasattr(self, 'output_path_line_edit') and self.output_path_line_edit:
            self.output_path_line_edit.setEnabled(enabled)
        if hasattr(self, 'btn_select_files') and self.btn_select_files:
            self.btn_select_files.setEnabled(enabled)
        if hasattr(self, 'btn_select_folder') and self.btn_select_folder:
            self.btn_select_folder.setEnabled(enabled)
        if hasattr(self, 'btn_output') and self.btn_output:
            self.btn_output.setEnabled(enabled)
        if hasattr(self, 'combo_from_format') and self.combo_from_format:
            self.combo_from_format.setEnabled(enabled)
        if hasattr(self, 'combo_to_format') and self.combo_to_format:
            self.combo_to_format.setEnabled(enabled)
        if hasattr(self, 'btn_convert') and self.btn_convert:
            self.btn_convert.setEnabled(enabled)
        if hasattr(self, 'btn_quick') and self.btn_quick:
            self.btn_quick.setEnabled(enabled)
        if hasattr(self, 'drop_area') and self.drop_area:
            self.drop_area.setEnabled(enabled)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = DocumentConverterGUI()
    gui.show()
    sys.exit(app.exec())