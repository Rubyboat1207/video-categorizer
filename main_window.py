import sys
import os
import random
import colorsys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QFileDialog, QListWidget, QListWidgetItem, 
                             QInputDialog, QColorDialog, QSplitter, QGroupBox, QFormLayout, 
                             QComboBox, QMessageBox, QMenu)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtCore import QUrl, Qt, QTimer, QSettings
from PyQt6.QtGui import QAction, QIcon, QColor, QDragEnterEvent, QDropEvent, QKeySequence

from models import Project, Section, Bookmark, Category
from timeline_widget import TimelineWidget
from stats_dialog import StatsDialog
from keybind_dialog import KeybindDialog

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Reviewer")
        self.resize(1200, 800)
        
        # Apply Modern Dark Theme
        self.apply_stylesheet()

        self.project = Project()
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.video_widget = QVideoWidget()
        self.media_player.setVideoOutput(self.video_widget)
        
        # Connect signals
        self.media_player.positionChanged.connect(self.position_changed)
        self.media_player.durationChanged.connect(self.duration_changed)
        
        self.active_section = None # Currently recording section
        self.current_scope = None # Current Section being edited (None for root)
        
        self.settings = QSettings("VideoReviewer", "App")
        self.recent_files = self.settings.value("recent_files", [], type=list)
        self.current_project_path = None
        
        self.undo_stack = []
        self.redo_stack = []

        self.autosave_timer = QTimer()
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start(60000) # 60 seconds

        self.init_ui()
        self.create_menu()

    def apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1E1E1E;
            }
            QWidget {
                color: #CCCCCC;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px;
            }
            QPushButton {
                background-color: #0E639C;
                color: white;
                border: none;
                padding: 5px 10px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1177BB;
            }
            QPushButton:pressed {
                background-color: #094771;
            }
            QPushButton:disabled {
                background-color: #333333;
                color: #888888;
            }
            QLineEdit, QComboBox, QListWidget, QScrollArea {
                background-color: #3C3C3C;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 4px;
                color: #CCCCCC;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #252526;
                selection-background-color: #094771;
            }
            QGroupBox {
                border: 1px solid #3E3E42;
                border-radius: 4px;
                margin-top: 20px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
            }
            QSplitter::handle {
                background-color: #333333;
            }
            QMenuBar {
                background-color: #333333;
                color: #CCCCCC;
            }
            QMenuBar::item:selected {
                background-color: #505050;
            }
            QMenu {
                background-color: #252526;
                border: 1px solid #3E3E42;
            }
            QMenu::item:selected {
                background-color: #094771;
            }
            QScrollBar:vertical {
                border: none;
                background: #1E1E1E;
                width: 14px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #424242;
                min-height: 20px;
                border-radius: 7px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background: #686868;
            }
            QScrollBar:horizontal {
                border: none;
                background: #1E1E1E;
                height: 14px;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: #424242;
                min-width: 20px;
                border-radius: 7px;
                margin: 2px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #686868;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                border: none;
                background: none;
            }
        """)

    def init_ui(self):
        self.setAcceptDrops(True)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Splitter for Main Content vs Sidebar
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # Left Side: Video & Timeline
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # Video Area
        left_layout.addWidget(self.video_widget, stretch=4)
        
        # Controls Area
        controls_layout = QHBoxLayout()
        
        # Scope Navigation (Back Button)
        self.back_scope_btn = QPushButton("Back to Parent")
        self.back_scope_btn.setEnabled(False)
        self.back_scope_btn.clicked.connect(self.exit_scope)
        controls_layout.addWidget(self.back_scope_btn)

        # Navigation
        self.prev_sec_btn = QPushButton("|<< Sec")
        self.prev_sec_btn.clicked.connect(self.jump_prev_section)
        controls_layout.addWidget(self.prev_sec_btn)
        
        self.prev_frame_btn = QPushButton("<< Frame")
        self.prev_frame_btn.clicked.connect(self.prev_frame)
        controls_layout.addWidget(self.prev_frame_btn)

        self.play_btn = QPushButton("Play")
        self.play_btn.clicked.connect(self.play_video)
        controls_layout.addWidget(self.play_btn)

        self.next_frame_btn = QPushButton("Frame >>")
        self.next_frame_btn.clicked.connect(self.next_frame)
        controls_layout.addWidget(self.next_frame_btn)

        self.next_sec_btn = QPushButton("Sec >>|")
        self.next_sec_btn.clicked.connect(self.jump_next_section)
        controls_layout.addWidget(self.next_sec_btn)

        # Time Label
        self.time_label = QLabel("00:00 / 00:00")
        controls_layout.addWidget(self.time_label)

        # Speed Control
        controls_layout.addWidget(QLabel("Speed:"))
        self.speed_combo = QComboBox()
        self.speed_combo.setEditable(True)
        self.speed_combo.addItems(["0.25x", "0.5x", "1.0x", "1.5x", "2.0x", "3.0x", "5.0x"])
        self.speed_combo.setCurrentText("1.0x")
        self.speed_combo.currentTextChanged.connect(self.change_speed)
        controls_layout.addWidget(self.speed_combo)
        
        left_layout.addLayout(controls_layout)

        # Timeline
        self.timeline = TimelineWidget(self.project)
        self.timeline.positionChanged.connect(self.seek_video)
        self.timeline.dataChanged.connect(self.on_timeline_data_changed)
        self.timeline.aboutToModify.connect(self.save_state_for_undo)
        self.timeline.sectionDoubleClicked.connect(self.enter_section_scope)
        left_layout.addWidget(self.timeline, stretch=1)

        splitter.addWidget(left_widget)

        # Right Side: Sidebar
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # Categories Management
        cat_group = QGroupBox("Categories")
        cat_layout = QVBoxLayout()
        
        hbox_cat = QHBoxLayout()
        self.add_cat_btn = QPushButton("Add Category")
        self.add_cat_btn.clicked.connect(self.add_category_dialog)
        hbox_cat.addWidget(self.add_cat_btn)
        cat_layout.addLayout(hbox_cat)
        
        cat_group.setLayout(cat_layout)
        right_layout.addWidget(cat_group)

        # Sections Controls
        sec_group = QGroupBox("Sections")
        sec_layout = QVBoxLayout()
        
        self.sec_combo = QComboBox()
        sec_layout.addWidget(QLabel("Section Type:"))
        
        hbox_sec_edit = QHBoxLayout()
        hbox_sec_edit.addWidget(self.sec_combo)
        
        edit_sec_btn = QPushButton("Edit")
        edit_sec_btn.setMaximumWidth(50)
        edit_sec_btn.clicked.connect(lambda: self.edit_category("section"))
        hbox_sec_edit.addWidget(edit_sec_btn)
        
        sec_layout.addLayout(hbox_sec_edit)
        
        self.start_sec_btn = QPushButton("Start Section")
        self.start_sec_btn.clicked.connect(self.toggle_section)
        sec_layout.addWidget(self.start_sec_btn)
        
        sec_group.setLayout(sec_layout)
        right_layout.addWidget(sec_group)

        # Bookmarks Controls
        bk_group = QGroupBox("Bookmarks")
        bk_layout = QVBoxLayout()
        
        self.bk_combo = QComboBox()
        self.bk_combo.setEditable(True)
        bk_layout.addWidget(QLabel("Bookmark Type:"))
        bk_layout.addWidget(self.bk_combo)
        
        self.refresh_combos()

        self.add_bk_btn = QPushButton("Add Bookmark")
        self.add_bk_btn.clicked.connect(self.add_bookmark)
        bk_layout.addWidget(self.add_bk_btn)
        
        bk_group.setLayout(bk_layout)
        right_layout.addWidget(bk_group)

        # Event Log
        right_layout.addWidget(QLabel("Event Log:"))
        self.event_list = QListWidget()
        right_layout.addWidget(self.event_list)

        # Stats Button
        self.stats_btn = QPushButton("View Stats")
        self.stats_btn.clicked.connect(self.show_stats)
        right_layout.addWidget(self.stats_btn)

        splitter.addWidget(right_widget)
        
        # Set initial sizes
        splitter.setSizes([800, 300])

    def create_menu(self):
        menu_bar = self.menuBar()
        
        file_menu = menu_bar.addMenu("File")
        
        open_action = QAction("Open Video", self)
        open_action.triggered.connect(self.open_video)
        file_menu.addAction(open_action)
        
        save_action = QAction("Save Project", self)
        save_action.triggered.connect(self.save_project)
        file_menu.addAction(save_action)
        
        load_action = QAction("Load Project", self)
        load_action.triggered.connect(self.load_project_dialog)
        file_menu.addAction(load_action)

        self.recent_menu = file_menu.addMenu("Recent Projects")
        self.update_recent_menu()
        
        options_menu = menu_bar.addMenu("Options")
        
        self.autosave_action = QAction("Enable Autosave", self, checkable=True)
        self.autosave_action.setChecked(True)
        self.autosave_action.triggered.connect(self.toggle_autosave)
        options_menu.addAction(self.autosave_action)

        keybind_action = QAction("Manage Keybinds", self)
        keybind_action.triggered.connect(self.show_keybind_dialog)
        options_menu.addAction(keybind_action)
        
        edit_menu = menu_bar.addMenu("Edit")
        undo_action = QAction("Undo", self)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.triggered.connect(self.undo)
        edit_menu.addAction(undo_action)
        
        redo_action = QAction("Redo", self)
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        redo_action.triggered.connect(self.redo)
        edit_menu.addAction(redo_action)

    def save_state_for_undo(self):
        if self.project:
            self.undo_stack.append(self.project.to_json())
            self.redo_stack.clear()
            if len(self.undo_stack) > 50:
                self.undo_stack.pop(0)

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(self.project.to_json())
        state = self.undo_stack.pop()
        self.project = Project.from_json(state)
        self.refresh_ui_after_state_change()
        self.update_log("Undid action")

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(self.project.to_json())
        state = self.redo_stack.pop()
        self.project = Project.from_json(state)
        self.refresh_ui_after_state_change()
        self.update_log("Redid action")

    def refresh_ui_after_state_change(self):
        self.timeline.set_project(self.project)
        self.current_scope = None # Reset scope on undo/redo to avoid invalid pointers
        self.timeline.set_scope(None)
        self.back_scope_btn.setEnabled(False)
        self.refresh_combos()
        self.event_list.clear()
        for e in self.project.events:
            self.event_list.addItem(e)
        self.event_list.scrollToBottom()

    def keyPressEvent(self, event):
        # Handle custom keybinds for bookmarks
        if not self.project: return
        
        # Build key string
        key = event.key()
        modifiers = event.modifiers()
        
        # Don't trigger on modifiers alone
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            super().keyPressEvent(event)
            return

        from PyQt6.QtGui import QKeySequence
        try:
            mod_val = modifiers.value
        except AttributeError:
            mod_val = int(modifiers)
            
        sequence = QKeySequence(key | mod_val)
        key_str = sequence.toString()
        
        if key_str in self.project.keybinds:
            cat_name = self.project.keybinds[key_str]
            # Verify category exists
            cat = next((c for c in self.project.categories if c.name == cat_name and c.type == 'bookmark'), None)
            if cat:
                self.save_state_for_undo()
                timestamp = self.media_player.position()
                bm = Bookmark(cat_name, timestamp, "")
                
                # Add to current scope
                target_list = self.current_scope.bookmarks if self.current_scope else self.project.bookmarks
                target_list.append(bm)
                
                self.timeline.update()
                self.update_log(f"Added Bookmark via Keybind: {cat_name}")
                event.accept()
                return
        
        super().keyPressEvent(event)

    def show_keybind_dialog(self):
        dlg = KeybindDialog(self.project, self)
        dlg.exec()

    def update_recent_menu(self):
        self.recent_menu.clear()
        for path in self.recent_files:
            action = QAction(path, self)
            action.triggered.connect(lambda checked, p=path: self.load_project(p))
            self.recent_menu.addAction(action)

    def add_recent_file(self, path):
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        if len(self.recent_files) > 10:
            self.recent_files = self.recent_files[:10]
        self.settings.setValue("recent_files", self.recent_files)
        self.update_recent_menu()

    def toggle_autosave(self):
        if self.autosave_action.isChecked():
            self.autosave_timer.start(60000)
        else:
            self.autosave_timer.stop()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        if files:
            video_path = files[0]
            # Simple check for extensions
            if video_path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                # Confirm new project
                reply = QMessageBox.question(self, "New Project", 
                                             "Start a new project with this video?", 
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.Yes:
                    self.project = Project(video_path=video_path)
                    self.current_project_path = None
                    self.timeline.set_project(self.project)
                    self.refresh_combos()
                    self.event_list.clear()
                    self.media_player.setSource(QUrl.fromLocalFile(video_path))
                    self.play_btn.setEnabled(True)
                    self.play_video()
                    self.update_log(f"Started new project with {os.path.basename(video_path)}")

    def autosave(self):
        if self.current_project_path:
            try:
                self.project.save(self.current_project_path)
                # Don't log autosaves to avoid clutter
            except Exception as e:
                print(f"Autosave failed: {e}")

    def on_timeline_data_changed(self):
        self.update_log("Timeline data modified")

    def edit_category(self, cat_type):
        self.save_state_for_undo()
        combo = self.sec_combo if cat_type == 'section' else self.bk_combo
        current_name = combo.currentText()
        if not current_name:
            return
            
        cat = next((c for c in self.project.categories if c.name == current_name and c.type == cat_type), None)
        if not cat:
            return

        menu = QMenu(self)
        rename_action = menu.addAction("Rename")
        color_action = menu.addAction("Change Color")
        delete_action = menu.addAction("Delete")
        
        action = menu.exec(combo.mapToGlobal(combo.rect().bottomLeft()))
        
        if action == rename_action:
            new_name, ok = QInputDialog.getText(self, "Rename Category", "Name:", text=current_name)
            if ok and new_name:
                # Update category
                cat.name = new_name
                # Update references
                if cat_type == 'section':
                    for s in self.project.sections:
                        if s.category_name == current_name: s.category_name = new_name
                else:
                    for b in self.project.bookmarks:
                        if b.category_name == current_name: b.category_name = new_name
                self.refresh_combos()
                combo.setCurrentText(new_name)
                self.timeline.update()
                
            # If section, allow changing layer too?
            if cat_type == 'section':
                layers = sorted(list(set(c.layer for c in self.project.categories if c.type == 'section')))
                if not layers: layers = ["Default"]
                
                current_layer_idx = 0
                if cat.layer in layers:
                    current_layer_idx = layers.index(cat.layer)
                
                layer, ok_layer = QInputDialog.getItem(self, "Change Layer", "Layer Name:", layers, current_layer_idx, True)
                if ok_layer and layer:
                    cat.layer = layer
                    self.timeline.update()
                
        elif action == color_action:
            color = QColorDialog.getColor(QColor(cat.color))
            if color.isValid():
                cat.color = color.name()
                self.timeline.update()
                
        elif action == delete_action:
            reply = QMessageBox.question(self, "Delete Category", 
                                         "Delete this category? Associated sections/bookmarks will remain but may lose color.",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.project.categories.remove(cat)
                self.refresh_combos()
                self.timeline.update()

    def jump_prev_section(self):
        combo = self.sec_combo if cat_type == 'section' else self.bk_combo
        current_name = combo.currentText()
        if not current_name:
            return
            
        cat = next((c for c in self.project.categories if c.name == current_name and c.type == cat_type), None)
        if not cat:
            return

        menu = QMenu(self)
        rename_action = menu.addAction("Rename")
        color_action = menu.addAction("Change Color")
        delete_action = menu.addAction("Delete")
        
        action = menu.exec(combo.mapToGlobal(combo.rect().bottomLeft()))
        
        if action == rename_action:
            new_name, ok = QInputDialog.getText(self, "Rename Category", "Name:", text=current_name)
            if ok and new_name:
                # Update category
                cat.name = new_name
                # Update references
                if cat_type == 'section':
                    for s in self.project.sections:
                        if s.category_name == current_name: s.category_name = new_name
                else:
                    for b in self.project.bookmarks:
                        if b.category_name == current_name: b.category_name = new_name
                self.refresh_combos()
                combo.setCurrentText(new_name)
                self.timeline.update()
                
        elif action == color_action:
            color = QColorDialog.getColor(QColor(cat.color))
            if color.isValid():
                cat.color = color.name()
                self.timeline.update()
                
        elif action == delete_action:
            reply = QMessageBox.question(self, "Delete Category", 
                                         "Delete this category? Associated sections/bookmarks will remain but may lose color.",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.project.categories.remove(cat)
                self.refresh_combos()
                self.timeline.update()

    def jump_prev_section(self):
        current = self.media_player.position()
        target = 0
        
        points = [0]
        for s in self.project.sections:
            points.append(s.start_time)
            if s.end_time: points.append(s.end_time)
        points = sorted(list(set(points)))
        
        # Find closest point strictly less than current
        for p in reversed(points):
            if p < current - 500: # 500ms threshold to jump to previous
                target = p
                break
                
        self.media_player.setPosition(target)

    def jump_next_section(self):
        current = self.media_player.position()
        duration = self.media_player.duration()
        target = duration
        
        points = []
        for s in self.project.sections:
            points.append(s.start_time)
            if s.end_time: points.append(s.end_time)
        points = sorted(list(set(points)))
        
        for p in points:
            if p > current + 500: # 500ms threshold
                target = p
                break
                
        self.media_player.setPosition(target)

    def open_video(self):
        # Prompt to save current project if needed (or just save if autosave is on? Better to ask)
        if self.project.sections or self.project.bookmarks:
            reply = QMessageBox.question(self, "Save Project?", 
                                         "Do you want to save the current project before opening a new video?", 
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.Yes:
                self.save_project()
        
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Video")
        if file_path:
            # Start New Project
            self.project = Project(video_path=file_path)
            self.current_project_path = None
            self.timeline.set_project(self.project)
            self.refresh_combos()
            self.event_list.clear()
            
            self.media_player.setSource(QUrl.fromLocalFile(file_path))
            self.play_btn.setEnabled(True)
            self.play_video()
            self.update_log(f"Started new project with {os.path.basename(file_path)}")

    def play_video(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            self.play_btn.setText("Play")
        else:
            self.media_player.play()
            self.play_btn.setText("Pause")

    def prev_frame(self):
        self.media_player.pause()
        self.play_btn.setText("Play")
        current = self.media_player.position()
        self.media_player.setPosition(max(0, current - 33)) # Approx 1 frame at 30fps

    def next_frame(self):
        self.media_player.pause()
        self.play_btn.setText("Play")
        current = self.media_player.position()
        self.media_player.setPosition(current + 33) # Approx 1 frame at 30fps

    def change_speed(self, text):
        try:
            speed_str = text.lower().replace('x', '')
            speed = float(speed_str)
            if speed > 0:
                self.media_player.setPlaybackRate(speed)
        except ValueError:
            pass # Invalid input, ignore

    def position_changed(self, position):
        self.timeline.set_position(position)
        self.update_time_label(position)
        
        # If we are recording a section, update UI visual feedback?
        if self.active_section:
            # We could dynamically draw the growing section here if we wanted
            # For now, timeline just shows static sections
            pass

    def duration_changed(self, duration):
        self.timeline.set_duration(duration)
        self.update_time_label(self.media_player.position())

    def update_time_label(self, position):
        duration = self.media_player.duration()
        pos_str = self.format_time(position)
        dur_str = self.format_time(duration)
        self.time_label.setText(f"{pos_str} / {dur_str}")

    def format_time(self, ms):
        seconds = (ms // 1000) % 60
        minutes = (ms // 60000) % 60
        hours = (ms // 3600000)
        if hours > 0:
            return f"{hours:02}:{minutes:02}:{seconds:02}"
        return f"{minutes:02}:{seconds:02}"

    def seek_video(self, position):
        self.media_player.setPosition(position)

    def add_category_dialog(self):
        name, ok = QInputDialog.getText(self, "New Category", "Category Name:")
        if ok and name:
            type_name, ok_type = QInputDialog.getItem(self, "Category Type", "Type:", ["section", "bookmark"], 0, False)
            if ok_type:
                layer = "Default"
                if type_name == 'section':
                    # Get existing layers
                    layers = sorted(list(set(c.layer for c in self.project.categories if c.type == 'section')))
                    if not layers: layers = ["Default"]
                    
                    layer, ok_layer = QInputDialog.getItem(self, "Select Layer", "Layer Name (or type new):", layers, 0, True)
                    if not ok_layer: return
                    if not layer: layer = "Default"
                
                color = QColorDialog.getColor()
                if color.isValid():
                    self.project.add_category(name, type_name, color.name(), layer)
                    self.refresh_combos()
                    self.timeline.update()

    def refresh_combos(self):
        self.sec_combo.clear()
        self.bk_combo.clear()
        
        secs = self.project.get_categories_by_type('section')
        for c in secs:
            self.sec_combo.addItem(c.name)
            
        bks = self.project.get_categories_by_type('bookmark')
        for c in bks:
            self.bk_combo.addItem(c.name)

    def enter_section_scope(self, section):
        self.current_scope = section
        self.timeline.set_scope(section)
        self.back_scope_btn.setEnabled(True)
        # Zoom video player logic could be added here to loop only this section, 
        # but for now let's just focus the timeline.
        self.setWindowTitle(f"Video Reviewer - {section.category_name} (Sub-Section Mode)")

    def exit_scope(self):
        # TODO: Handle multi-level nesting (stack) if needed. 
        # Currently just 1 level deep is implemented for simplicity, but model supports infinite.
        # To support infinite, we'd need a parent reference or traverse from root.
        # For this task, let's assume 1 level or implement simple stack in future.
        # Actually, let's just go to Root for now to be safe.
        self.current_scope = None
        self.timeline.set_scope(None)
        self.back_scope_btn.setEnabled(False)
        self.setWindowTitle("Video Reviewer")

    def toggle_section(self):
        if self.active_section:
            self.save_state_for_undo()
            # Stop section
            self.active_section.end_time = self.media_player.position()
            self.active_section = None
            self.start_sec_btn.setText("Start Section")
            self.timeline.update() # Redraw
            self.update_log("Ended Section")
        else:
            # Start section
            cat_name = self.sec_combo.currentText()
            if not cat_name:
                QMessageBox.warning(self, "Error", "Create a section category first!")
                return
            
            self.save_state_for_undo()
            start_time = self.media_player.position()
            new_sec = Section(cat_name, start_time, end_time=None) # end_time None means ongoing
            
            # Add to current scope
            if self.current_scope:
                self.current_scope.sub_sections.append(new_sec)
            else:
                self.project.sections.append(new_sec)
                
            self.active_section = new_sec
            self.start_sec_btn.setText("Stop Section")
            self.update_log(f"Started Section: {cat_name}")

    def add_bookmark(self):
        cat_name = self.bk_combo.currentText()
        if not cat_name:
            return
            
        # Check if category exists
        cat = next((c for c in self.project.categories if c.name == cat_name and c.type == 'bookmark'), None)
        if not cat:
            # Create new category with random color
            h = random.random()
            s = random.uniform(0.6, 1.0)
            v = random.uniform(0.8, 1.0)
            r, g, b = colorsys.hsv_to_rgb(h, s, v)
            color_hex = QColor.fromRgbF(r, g, b).name()
            
            self.save_state_for_undo()
            self.project.add_category(cat_name, 'bookmark', color_hex)
            self.refresh_combos()
            self.bk_combo.setCurrentText(cat_name)
            self.update_log(f"Created new bookmark category: {cat_name}")

        timestamp = self.media_player.position()
        desc, ok = QInputDialog.getText(self, "Bookmark Description", "Description (optional):")
        
        bm = Bookmark(cat_name, timestamp, desc if ok else "")
        self.save_state_for_undo()
        
        # Add to current scope
        if self.current_scope:
            self.current_scope.bookmarks.append(bm)
        else:
            self.project.bookmarks.append(bm)
            
        self.timeline.update()
        self.update_log(f"Added Bookmark: {cat_name}")

    def update_log(self, message):
        self.event_list.addItem(message)
        self.event_list.scrollToBottom()
        self.project.events.append(message)

    def show_stats(self):
        if not self.project.sections and not self.project.bookmarks:
            QMessageBox.information(self, "Info", "No data to analyze yet.")
            return
            
        dlg = StatsDialog(self.project, self.media_player.duration(), self)
        dlg.exec()

    def save_project(self):
        if self.current_project_path:
            path = self.current_project_path
        else:
            path, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "JSON Files (*.json)")
        
        if path:
            self.current_project_path = path
            self.project.save(path)
            self.add_recent_file(path)
            self.update_log("Project saved.")

    def load_project_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Project", "", "JSON Files (*.json)")
        if path:
            self.load_project(path)

    def load_project(self, path):
        if not os.path.exists(path):
            QMessageBox.warning(self, "Error", "File does not exist.")
            return

        try:
            self.project = Project.load(path)
            self.current_project_path = path
            self.add_recent_file(path)
            
            self.timeline.set_project(self.project)
            self.refresh_combos()
            
            # Load Event Log
            self.event_list.clear()
            for event in self.project.events:
                self.event_list.addItem(event)
            self.event_list.scrollToBottom()
            
            # Try to load video if path exists
            if self.project.video_path and os.path.exists(self.project.video_path):
                self.media_player.setSource(QUrl.fromLocalFile(self.project.video_path))
                self.play_btn.setEnabled(True)
            
            self.update_log("Project loaded.")
            self.timeline.update()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load project: {str(e)}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
