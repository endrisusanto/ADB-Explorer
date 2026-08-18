import os
import sys
import hashlib
import shutil
import re
import time
from pathlib import Path
import subprocess
import configparser

from PyQt6.QtWidgets import (
    QMainWindow, QSplitter, QVBoxLayout, QHBoxLayout, QWidget,
    QPushButton, QMessageBox, QStatusBar, QLabel, QDialog,
    QFileDialog, QMenu, QApplication, QScrollArea, QSizePolicy,
    QGraphicsDropShadowEffect, QBoxLayout,
)
from PyQt6.QtCore import Qt, QTimer, QUrl, QEvent
from PyQt6.QtGui import QDesktopServices, QIcon, QColor

from handler import ADBHandler, LocalFileHandler
from ui.device_panel import DevicePanel
from ui.widgets import ADB_MIME
from ui.task_manager import BackgroundTaskManager
from ui.theme import LIGHT, DARK

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(os.path.abspath(__file__)).parent

def get_resource_dir():
    return Path(getattr(sys, "_MEIPASS", Path(os.path.abspath(__file__)).parent.parent))

CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "adb-file-explorer" / "config.ini"
MAX_PANELS = 4
VERTICAL_MAX_PANELS = 3
MODEL_COLORS = (
    "#2563eb", "#dc2626", "#16a34a", "#f97316",
    "#7c3aed", "#0891b2", "#db2777", "#65a30d",
    "#0f766e", "#ca8a04", "#4f46e5", "#be123c",
)


def _model_color(model):
    digest = hashlib.blake2s(model.encode("utf-8"), digest_size=1).digest()[0]
    return MODEL_COLORS[digest % len(MODEL_COLORS)]


def _soft_color(color):
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r}, {g}, {b}, 42)"


def _format_size(bytes_size):
    bytes_size = float(bytes_size)
    for unit in ("B", "KB", "MB", "GB"):
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"


def _card_shadow(color, dark):
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    effect = QGraphicsDropShadowEffect()
    effect.setBlurRadius(12 if dark else 10)
    effect.setOffset(0, 0 if dark else 3)
    effect.setColor(QColor(r, g, b, 190 if dark else 115))
    return effect

def _load_theme():
    cp = configparser.ConfigParser()
    cp.read(CONFIG_PATH)
    try:
        return cp.getboolean("app", "dark_mode")
    except Exception:
        return False


def _save_theme(dark: bool):
    cp = configparser.ConfigParser()
    cp.read(CONFIG_PATH)
    if "app" not in cp:
        cp["app"] = {}
    cp["app"]["dark_mode"] = "yes" if dark else "no"
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            cp.write(f)
    except Exception:
        pass


class MultiDeviceWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ADB Explorer")
        self.setGeometry(100, 100, 1100, 600)
        self.setWindowIcon(QIcon(str(get_resource_dir() / "assets" / "logo.svg")))

        self.device_panels = []
        self._dark = _load_theme()
        self._device_list_vertical = True
        QApplication.instance().setStyleSheet(DARK if self._dark else LIGHT)

        
        self._setup_ui()

        
        self._initialize_panels()

        
        self.connection_timer = QTimer()
        self.connection_timer.timeout.connect(self._check_connections)
        self.connection_timer.start(10000)

    def _setup_ui(self):
        central = QWidget()
        central.setObjectName("app_root")
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.device_status_label = QLabel("Detecting devices...")
        self.device_status_label.setObjectName("device_count_badge")
        self.device_status_label.setToolTip("Connected device count")

        self.sidebar = QWidget()
        self.sidebar.setObjectName("device_sidebar")
        self.sidebar.setFixedWidth(292)
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(12, 12, 12, 12)
        self.sidebar_layout.setSpacing(10)
        layout.addWidget(self.sidebar)

        self.content = QWidget()
        self.content.setObjectName("content_root")
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        layout.addWidget(self.content, 1)

        self.topbar = QWidget()
        self.topbar.setObjectName("main_topbar")
        self.topbar.setFixedHeight(112)
        self.topbar_layout = QHBoxLayout(self.topbar)
        self.topbar_layout.setContentsMargins(12, 8, 12, 10)
        self.topbar_layout.setSpacing(10)
        content_layout.addWidget(self.topbar)

        self.device_scroll = QScrollArea()
        self.device_scroll.setObjectName("device_strip")
        self.device_scroll.setWidgetResizable(True)
        self.device_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.device_scroll.viewport().installEventFilter(self)
        self.device_strip = QWidget()
        self.device_strip_layout = QBoxLayout(QBoxLayout.Direction.TopToBottom, self.device_strip)
        self.device_strip_layout.setContentsMargins(0, 4, 0, 12)
        self.device_strip_layout.setSpacing(10)
        self.device_strip.installEventFilter(self)
        self.device_scroll.setWidget(self.device_strip)

        self.action_group = QWidget()
        self.action_group.setObjectName("topbar_actions")
        action_layout = QHBoxLayout(self.action_group)
        action_layout.setContentsMargins(4, 4, 4, 4)
        action_layout.setSpacing(6)
        self.device_status_label.setText("0")
        action_layout.addWidget(self.device_status_label)

        self.layout_mode_btn = QPushButton()
        self.layout_mode_btn.setObjectName("icon_badge")
        self.layout_mode_btn.setToolTip("Toggle device list layout")
        self.layout_mode_btn.clicked.connect(self._toggle_device_list_mode)
        action_layout.addWidget(self.layout_mode_btn)

        self.refresh_devices_btn = QPushButton()
        self.refresh_devices_btn.setObjectName("icon_badge")
        self.refresh_devices_btn.setToolTip("Refresh devices")
        self.refresh_devices_btn.clicked.connect(lambda _=False: self._refresh_device_cards())
        action_layout.addWidget(self.refresh_devices_btn)

        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("icon_badge")
        self.theme_btn.setCheckable(True)
        self.theme_btn.setChecked(self._dark)
        self.theme_btn.setToolTip("Toggle dark mode")
        self._update_topbar_icons()
        self.theme_btn.toggled.connect(self._toggle_theme)
        action_layout.addWidget(self.theme_btn)

        
        menubar = self.menuBar()
        menubar.setObjectName("main_menu")
        edit_menu = menubar.addMenu("Edit")
        edit_menu.addAction("Cut", self._broadcast_cut)
        edit_menu.addAction("Copy", self._broadcast_copy)
        edit_menu.addAction("Paste", self._broadcast_paste)
        edit_menu.addSeparator()
        edit_menu.addAction("Delete", self._broadcast_delete)
        edit_menu.addAction("Rename", self._broadcast_rename)
        view_menu = menubar.addMenu("View")
        self.dark_mode_action = view_menu.addAction("Dark Mode")
        self.dark_mode_action.setCheckable(True)
        self.dark_mode_action.setChecked(self._dark)
        self.dark_mode_action.toggled.connect(self._toggle_theme)
        tools_menu = menubar.addMenu("Tools")
        tools_menu.addAction("Install APK...", self._install_apk_dialog)
        tools_menu.addAction("Install XAPK...", self._install_xapk_dialog)
        help_menu = menubar.addMenu("Help")
        help_menu.addAction("Check for Updates...", self._open_updates)

        
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(True)
        content_layout.addWidget(self.splitter, 1)

        
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("Ready")
        self.status_bar.addWidget(self.status_label)

        
        self.task_manager = BackgroundTaskManager(central)
        self._apply_device_list_mode()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'task_manager') and self.task_manager.isVisible():
            self._position_task_manager()

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, 'task_manager'):
            self._position_task_manager()

    def eventFilter(self, obj, event):
        if not self._device_list_vertical and obj is self.device_scroll.viewport() and event.type() == QEvent.Type.Wheel:
            delta = event.angleDelta().y() or event.angleDelta().x()
            if delta:
                bar = self.device_scroll.horizontalScrollBar()
                bar.setValue(bar.value() - delta)
                return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        if hasattr(self, 'task_manager'):
            self.task_manager.setParent(None)
        self.device_panels.clear()
        event.accept()

    def _position_task_manager(self):
        if not hasattr(self, 'task_manager'):
            return
        mgr = self.task_manager
        parent = mgr.parentWidget() or self
        margin = 15
        x = max(margin, parent.width() - mgr.width() - margin)
        y = max(margin, parent.height() - mgr.height() - margin)
        mgr.move(x, y)
        mgr.raise_()

    

    def _initialize_panels(self):
        initial_devices = ADBHandler().get_unique_devices()
        self._refresh_device_cards(initial_devices)

        if not initial_devices:
            self.status_label.setText("No ADB devices found. Connect a device and refresh.")
            return

        self.status_label.setText("Ready. Choose a card to open a panel.")

    def _add_panel_for_device(self, serial, model, start_path="/storage/emulated/0"):
        if self._panel_limit_reached():
            return None
        try:
            handler = ADBHandler(device_serial=serial)
            panel = DevicePanel(self.splitter, handler, device_info={"model": model}, start_path=start_path)
            self.splitter.addWidget(panel)
            self.device_panels.append(panel)
            panel.cross_device_drop.connect(self._on_cross_device_drop)
            panel.close_requested.connect(lambda p=panel: self._close_panel(p))

            
            idx = len(self.device_panels)
            self.status_label.setText(f"Added panel {idx}: {model} ({serial})")
            self._update_panel_count_ui()
            self._reconnect_drop_signals()
            return panel
        except Exception as e:
            self.status_label.setText(f"Failed to add panel: {e}")
            return None

    def _add_panel(self):
        devices = ADBHandler().get_unique_devices()
        existing_serials = {p.device_serial for p in self.device_panels}
        for serial, model in devices.items():
            if serial not in existing_serials:
                self._add_panel_for_device(serial, model)
                return
        QMessageBox.information(self, "No Devices", "No unopened ADB devices found.")

    def _close_panel(self, panel):
        if panel not in self.device_panels:
            return
        self.device_panels.remove(panel)
        panel.prepare_for_close()
        self._update_panel_count_ui()
        self._reconnect_drop_signals()
        self.status_label.setText("Panel closed")

    def _update_panel_count_ui(self):
        self._refresh_device_cards()

    def _panel_limit_reached(self):
        limit = self._panel_limit()
        if len(self.device_panels) < limit:
            return False
        self.status_label.setText(f"Maximum {limit} panels open")
        return True

    def _panel_limit(self):
        return VERTICAL_MAX_PANELS if self._device_list_vertical else MAX_PANELS

    def _toggle_device_list_mode(self):
        self._device_list_vertical = not self._device_list_vertical
        self._apply_device_list_mode()
        self._refresh_device_cards()

    def _take_layout_widget(self, layout, widget):
        for i in range(layout.count()):
            if layout.itemAt(i).widget() is widget:
                return layout.takeAt(i)
        return None

    def _apply_device_list_mode(self):
        self._take_layout_widget(self.sidebar_layout, self.device_scroll)
        self._take_layout_widget(self.sidebar_layout, self.action_group)
        self._take_layout_widget(self.topbar_layout, self.device_scroll)
        self._take_layout_widget(self.topbar_layout, self.action_group)

        if self._device_list_vertical:
            self.sidebar.show()
            self.topbar.hide()
            self.device_scroll.setMinimumHeight(0)
            self.device_scroll.setMaximumHeight(16777215)
            self.device_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.device_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.device_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.device_strip_layout.setDirection(QBoxLayout.Direction.TopToBottom)
            self.device_strip_layout.setContentsMargins(0, 4, 0, 12)
            self.sidebar_layout.addWidget(self.device_scroll, 1)
            self.sidebar_layout.addWidget(self.action_group)
            self.layout_mode_btn.setText("↔")
            self.layout_mode_btn.setToolTip("Switch to horizontal device list")
        else:
            self.sidebar.hide()
            self.topbar.show()
            self.device_scroll.setMinimumWidth(0)
            self.device_scroll.setMaximumWidth(16777215)
            self.device_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.device_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.device_scroll.setFixedHeight(94)
            self.device_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.device_strip_layout.setDirection(QBoxLayout.Direction.LeftToRight)
            self.device_strip_layout.setContentsMargins(14, 10, 14, 30)
            self.topbar_layout.addWidget(self.device_scroll, 1)
            self.topbar_layout.addWidget(self.action_group)
            self.layout_mode_btn.setText("↕")
            self.layout_mode_btn.setToolTip("Switch to vertical device list")
        self.device_scroll.verticalScrollBar().setSingleStep(28)
        self.device_scroll.horizontalScrollBar().setSingleStep(28)
        self._repolish_topbar()

    def _style_device_card(self, btn, model):
        color = _model_color(model or "Root")
        soft = _soft_color(color)
        bg = "#141416" if self._dark else "#ffffff"
        hover = "#18181b" if self._dark else "#f8fbff"
        base_text = "#f4f4f5" if self._dark else "#334155"
        text = "#f4f4f5" if self._dark else "#0f172a"
        disabled = "#71717a" if self._dark else "#94a3b8"
        min_width = 0 if self._device_list_vertical else 210
        max_width = 260 if self._device_list_vertical else 220
        btn.setMinimumWidth(min_width)
        btn.setMaximumWidth(max_width)
        btn.setStyleSheet(
            f"QPushButton#device_card {{ min-width: {min_width}px; max-width: {max_width}px; background: {bg}; border-color: {color}; color: {base_text}; }}"
            f"QPushButton#device_card:hover {{ background: {hover}; border-color: {color}; color: {text}; }}"
            f"QPushButton#device_card:checked {{ background: {soft}; border-color: {color}; color: {text}; }}"
            f"QPushButton#device_card:disabled {{ border-color: {color}; color: {disabled}; }}"
        )
        btn.style().unpolish(btn)
        btn.style().polish(btn)
        btn._shadow_effect = _card_shadow(color, self._dark) if btn.isChecked() else None
        btn.setGraphicsEffect(btn._shadow_effect)
        btn.update()

    def _repolish_topbar(self):
        for widget in (self.sidebar, self.topbar, self.action_group, self.device_status_label, self.layout_mode_btn, self.refresh_devices_btn, self.theme_btn):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()

    def _refresh_device_cards(self, devices=None):
        devices = ADBHandler().get_unique_devices() if devices is None else devices
        bar = self.device_scroll.verticalScrollBar() if self._device_list_vertical else self.device_scroll.horizontalScrollBar()
        scroll_pos = bar.value()
        while self.device_strip_layout.count():
            item = self.device_strip_layout.takeAt(0)
            if item.widget():
                widget = item.widget()
                widget.setParent(None)
                widget.deleteLater()

        opened = {p.device_serial for p in self.device_panels}
        root_open = any(p.device_serial == LocalFileHandler.device_serial for p in self.device_panels)
        can_open = len(self.device_panels) < self._panel_limit()
        self.device_status_label.setText(str(len(devices)))

        if not devices:
            empty = QLabel("No ADB devices connected")
            empty.setObjectName("device_empty")
            empty.installEventFilter(self)
            self.device_strip_layout.addWidget(empty)

        cards = [("root", "Root", str(Path.home()), root_open)]
        cards += [(serial, model or "Android Device", serial, serial in opened) for serial, model in devices.items()]
        for serial, model, subtitle, is_open in sorted(cards, key=lambda item: not item[3]):
            btn = QPushButton(f"{'Active' if is_open else 'Ready'} · {model}\n{subtitle}")
            btn.setObjectName("device_card")
            btn.setCheckable(True)
            btn.setChecked(is_open)
            btn.setEnabled(is_open or can_open)
            btn.setToolTip("Close panel" if is_open else "Open panel")
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.installEventFilter(self)
            self._style_device_card(btn, model)
            if serial == "root":
                btn.clicked.connect(lambda _=False: self._open_root_card())
            else:
                btn.clicked.connect(lambda _, s=serial, m=model: self._open_device_card(s, m))
            self.device_strip_layout.addWidget(btn)

        self.device_strip_layout.addStretch()
        QTimer.singleShot(0, lambda v=scroll_pos: bar.setValue(min(v, bar.maximum())))

    def _open_device_card(self, serial, model):
        for panel in self.device_panels:
            if panel.device_serial == serial:
                self._close_panel(panel)
                return
        self._add_panel_for_device(serial, model)

    def _open_root_card(self):
        for panel in self.device_panels:
            if panel.device_serial == LocalFileHandler.device_serial:
                self._close_panel(panel)
                return
        if self._panel_limit_reached():
            return
        panel = DevicePanel(
            self.splitter,
            LocalFileHandler(),
            device_info={"model": "Root"},
            start_path=str(Path.home()),
        )
        self.splitter.addWidget(panel)
        self.device_panels.append(panel)
        panel.cross_device_drop.connect(self._on_cross_device_drop)
        panel.close_requested.connect(lambda p=panel: self._close_panel(p))
        self.status_label.setText(f"Added local root panel: {Path.home()}")
        self._update_panel_count_ui()

    def _reconnect_drop_signals(self):
        
        pass  

    

    def _on_cross_device_drop(self, src_serial, paths, dest_path, move=False):
        
        dest_panel = self.sender()
        if not isinstance(dest_panel, DevicePanel):
            return

        
        src_panel = None
        for p in self.device_panels:
            if p.device_serial == src_serial:
                src_panel = p
                break

        if not src_panel:
            self.status_label.setText("Source device panel not found")
            return

        self._stream_items(src_panel, dest_panel, paths, move, dest_path)

    def _stream_items(self, src_panel, dest_panel, paths, move=False, dest_dir=None):
        from ui.task_manager import WorkerThread
        task = None

        def run():
            for path in paths:
                name = path.rstrip('/').split('/')[-1]
                dest = f"{(dest_dir or dest_panel.current_path).rstrip('/')}/{name}"
                size = Path(path).stat().st_size if isinstance(src_panel.adb_handler, LocalFileHandler) and Path(path).is_file() else 0
                task.status_changed.emit(f"file={name}" + (f"|size={size}" if size else ""))

                if isinstance(src_panel.adb_handler, LocalFileHandler):
                    dest_panel.adb_handler.create_folder(dest_panel.current_path)
                    ok = dest_panel.adb_handler.push_file_streaming(path, dest, line_callback=task.status_changed.emit)
                    if ok and move:
                        shutil.rmtree(path) if Path(path).is_dir() else Path(path).unlink(missing_ok=True)
                    if not ok:
                        return False
                    continue

                test_cmd = ['adb', '-s', src_panel.device_serial, 'exec-out', 'test', '-d', path]
                test_r = subprocess.run(test_cmd, capture_output=True, timeout=10)
                is_dir = test_r.returncode == 0
                if not is_dir:
                    stat_r = subprocess.run(
                        ['adb', '-s', src_panel.device_serial, 'exec-out', 'stat', '-c%s', path],
                        capture_output=True, timeout=10,
                    )
                    if stat_r.returncode == 0:
                        size = stat_r.stdout.decode("utf-8", errors="replace").strip()
                        if size.isdigit():
                            task.status_changed.emit(f"file={name}|size={size}")

                if isinstance(dest_panel.adb_handler, LocalFileHandler):
                    Path(dest).parent.mkdir(parents=True, exist_ok=True)
                    ok = src_panel.adb_handler.pull_file_streaming(path, dest, line_callback=task.status_changed.emit)
                    if ok and move:
                        src_panel.adb_handler.delete_item(path, is_dir)
                    if not ok:
                        return False
                    continue

                if is_dir:
                    ok = src_panel.adb_handler.stream_directory(
                        src_panel.device_serial, path,
                        dest_panel.device_serial, dest,
                        line_callback=task.status_changed.emit,
                    )
                else:
                    ok = src_panel.adb_handler.stream_file(
                        src_panel.device_serial, path,
                        dest_panel.device_serial, dest,
                    )
                if not ok:
                    return False
            return True

        def on_done(ok):
            if ok:
                self.status_label.setText("Move complete" if move else "Copy complete")
                src_panel.refresh_files()
                dest_panel.refresh_files()
            else:
                on_error()

        def on_error():
            err = src_panel.adb_handler.last_error or dest_panel.adb_handler.last_error or ""
            self.status_label.setText((("Move failed" if move else "Copy failed") + (f": {err}" if err else ""))[:180])

        task = WorkerThread(f"{'Move' if move else 'Copy'} to {dest_panel.device_name}", run)
        self._run_modal(f"{'Move' if move else 'Copy'} to {dest_panel.device_name}", task=task, on_done=on_done, on_error=on_error)

    

    def _target_panel(self):
        for p in self.device_panels:
            if isinstance(p.adb_handler, ADBHandler) and p.adb_handler.device_connected:
                return p
        return None

    def _install_apk_dialog(self):
        panel = self._target_panel()
        if not panel:
            QMessageBox.warning(self, "No Device", "No connected device panel to install to.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Select APK", "", "APK (*.apk)")
        if not path:
            return
        self._run_modal(
            "Install APK", panel.adb_handler.install_apk, path,
            on_done=lambda ok: (
                self.status_label.setText("APK installed successfully") if ok
                else self.status_label.setText("APK installation failed")
            ),
        )

    def _install_xapk_dialog(self):
        panel = self._target_panel()
        if not panel:
            QMessageBox.warning(self, "No Device", "No connected device panel to install to.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Select XAPK", "", "XAPK (*.xapk)")
        if not path:
            return

        def on_done(val):
            if val:
                self.status_label.setText(f"XAPK installed ({val} APK files)")

        def on_error():
            err = panel.adb_handler.last_error or "XAPK install failed"
            self.status_label.setText(err)

        self._run_modal("Install XAPK", panel.adb_handler.install_xapk, path,
                        on_done=on_done, on_error=on_error)

    

    def _active_panel(self):
        for p in self.device_panels:
            if p.tree_view.hasFocus():
                return p
        return self._target_panel()

    def _broadcast_copy(self):
        p = self._active_panel()
        if p:
            p.copy_selected()

    def _broadcast_cut(self):
        p = self._active_panel()
        if p:
            p.cut_selected()

    def _broadcast_paste(self):
        p = self._active_panel()
        if p:
            p.paste_items()

    def _broadcast_delete(self):
        p = self._active_panel()
        if p:
            p.delete_selected_items()

    def _broadcast_rename(self):
        p = self._active_panel()
        if p:
            if len(p.tree_view.selectionModel().selectedRows()) == 1:
                name = p.tree_model.data(p.tree_model.index(p.tree_view.selectionModel().selectedRows()[0].row(), 0))
                if name and name != "..":
                    p.rename_item(name)

    def _open_updates(self):
        QDesktopServices.openUrl(QUrl("https://github.com/JSleim/adb-file-explorer/releases"))

    def _toggle_theme(self, dark):
        self._dark = dark
        _save_theme(dark)
        QApplication.instance().setStyleSheet(DARK if dark else LIGHT)
        if hasattr(self, "dark_mode_action"):
            self.dark_mode_action.blockSignals(True)
            self.dark_mode_action.setChecked(dark)
            self.dark_mode_action.blockSignals(False)
        if hasattr(self, "theme_btn"):
            self.theme_btn.blockSignals(True)
            self.theme_btn.setChecked(dark)
            self.theme_btn.blockSignals(False)
        self._update_topbar_icons()
        self._repolish_topbar()
        self._refresh_device_cards()

    def _update_topbar_icons(self):
        if hasattr(self, "refresh_devices_btn"):
            refresh = "refresh-dark.svg" if self._dark else "refresh-light.svg"
            self.refresh_devices_btn.setIcon(QIcon(str(get_resource_dir() / "assets" / refresh)))
        if hasattr(self, "theme_btn"):
            icon = "sun.svg" if self._dark else "moon.svg"
            self.theme_btn.setIcon(QIcon(str(get_resource_dir() / "assets" / icon)))
            self.theme_btn.setText("")

    

    def _check_connections(self):
        for panel in self.device_panels:
            was = panel.adb_handler.device_connected
            panel.adb_handler.device_connected = panel.adb_handler.check_adb_connection()
            if was != panel.adb_handler.device_connected:
                panel.update_connection_status()
                if not panel.adb_handler.device_connected:
                    panel.status_label.setText("Disconnected")
                else:
                    panel.status_label.setText("Reconnected")
                    panel.refresh_files()
        self._refresh_device_cards()

    

    def _run_modal(self, title, fn=None, *args, on_done=None, on_error=None, refresh=False, task=None):
        from ui.task_manager import WorkerThread
        from PyQt6.QtWidgets import QProgressBar, QPushButton

        task = task or WorkerThread(title, fn, *args)
        started_at = time.monotonic()

        dlg = QDialog(self)
        dlg.setObjectName("transfer_dialog")
        dlg.setWindowTitle(f"{title} · Transfer Statistics")
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setFixedSize(520, 260)
        dlg.setStyleSheet("""
            QDialog#transfer_dialog {
                background: #141416;
                color: #f4f4f5;
            }
            QDialog#transfer_dialog QLabel#transfer_title {
                font-weight: 700;
                font-size: 13px;
                color: #f4f4f5;
            }
            QDialog#transfer_dialog QLabel#transfer_stat {
                color: #a1a1aa;
                padding: 1px 0;
            }
            QDialog#transfer_dialog QProgressBar {
                min-height: 12px;
                border: 1px solid #27272a;
                border-radius: 6px;
                background: #09090b;
                text-align: center;
                color: #f4f4f5;
            }
            QDialog#transfer_dialog QProgressBar::chunk {
                border-radius: 6px;
                background: #2563eb;
            }
        """)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)

        label = QLabel(f"{title}...")
        label.setObjectName("transfer_title")
        layout.addWidget(label)

        bar = QProgressBar()
        bar.setRange(0, 0)
        layout.addWidget(bar)

        filename_label = QLabel("Filename: -")
        size_label = QLabel("Size: -")
        speed_label = QLabel("Speed: -")
        eta_label = QLabel("ETA: -")
        for stat_label in (filename_label, size_label, speed_label, eta_label):
            stat_label.setObjectName("transfer_stat")
            stat_label.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(stat_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        bg_btn = QPushButton("Background")
        cancel_btn = QPushButton("Cancel")
        btn_row.addWidget(bg_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        sent_to_background = [False]
        completed = [False]
        failed = [False]

        def reopen_dialog():
            if completed[0]:
                return
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()

        def send_to_background():
            if sent_to_background[0]:
                dlg.hide()
                return
            sent_to_background[0] = True
            dlg.hide()
            self.task_manager.add_task(task, name=title, on_reopen=reopen_dialog)
            self._position_task_manager()

        bg_btn.clicked.connect(send_to_background)

        def cancel_task():
            task.cancel()
            dlg.close()

        cancel_btn.clicked.connect(cancel_task)

        def update_progress(line):
            if not line:
                return
            if line.startswith("file="):
                parts = dict(part.split("=", 1) for part in line.split("|") if "=" in part)
                filename_label.setText(f"Filename: {parts.get('file', '-')}")
                if "size" in parts:
                    size_label.setText(f"Size: {_format_size(int(parts['size']))}")
                return
            if line.startswith("stat="):
                parts = dict(part.split("=", 1) for part in line.split("|") if "=" in part)
                done = int(float(parts.get("stat", 0)))
                total = int(float(parts.get("total", 0)))
                speed_value = float(parts.get("speed", 0))
                pct = int(done * 100 / total) if total else 0
                bar.setRange(0, 100)
                bar.setValue(min(100, pct))
                size_label.setText(f"Size: {_format_size(done)} / {_format_size(total)}")
                speed_label.setText(f"Speed: {_format_size(speed_value)}/s")
                eta_label.setText(f"ETA: {parts.get('eta', '0')}s")
                return
            percent = re.search(r'(?:\[?\s*|: )(\d{1,3})%\]?\s*(.*)', line)
            speed = re.search(r'([\d.]+\s*[KMGTP]?B/s)', line)
            done = re.search(r'([\d.]+\s*[KMGTP]?B/s).*\((\d+) bytes in ([\d.]+)s\)', line)
            if percent:
                pct = min(100, int(percent.group(1)))
                name = os.path.basename(percent.group(2).strip()) or title
                elapsed = max(time.monotonic() - started_at, 0.1)
                eta = int(elapsed * (100 - pct) / pct) if pct else 0
                bar.setRange(0, 100)
                bar.setValue(pct)
                label.setText(name)
                filename_label.setText(f"Filename: {name}")
                eta_label.setText(f"ETA: {eta}s")
                if speed:
                    speed_label.setText(f"Speed: {speed.group(1)}")
            elif done:
                bar.setRange(0, 100)
                bar.setValue(100)
                size_label.setText(f"Size: {_format_size(int(done.group(2)))}")
                speed_label.setText(f"Speed: {done.group(1)}")
                eta_label.setText(f"ETA: done in {done.group(3)}s")
            else:
                filename_label.setText(f"Filename: {line[:140]}")

        def handle_finished(val):
            completed[0] = True
            if dlg.isVisible():
                dlg.close()
            if failed[0]:
                return
            is_ok = not failed[0] and (bool(val) if val is not None else False)
            if is_ok:
                if on_done:
                    on_done(val)
                if refresh:
                    pass  
            elif not sent_to_background[0]:
                if on_error:
                    on_error()
                else:
                    self.status_label.setText(f"{title} failed")

        def handle_error(msg):
            failed[0] = True
            if dlg.isVisible():
                dlg.close()
            if on_error:
                on_error()

        task.finished_signal.connect(handle_finished)
        task.error_signal.connect(handle_error)
        task.status_changed.connect(update_progress)
        dlg.show()
        task.start()
        return task
