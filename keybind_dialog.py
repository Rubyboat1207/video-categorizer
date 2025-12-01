from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, 
                             QPushButton, QComboBox, QLabel, QMessageBox, QHeaderView)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence

class KeybindDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Keybinds")
        self.resize(500, 400)
        self.project = project
        self.captured_key = None
        
        layout = QVBoxLayout(self)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Key Sequence", "Bookmark Category"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        
        self.populate_table()
        
        # Add New
        add_group = QHBoxLayout()
        
        self.key_btn = QPushButton("Press Key...")
        self.key_btn.setCheckable(True)
        self.key_btn.clicked.connect(self.capture_key)
        add_group.addWidget(self.key_btn)
        
        self.cat_combo = QComboBox()
        self.update_cat_combo()
        add_group.addWidget(self.cat_combo)
        
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self.add_keybind)
        add_group.addWidget(add_btn)
        
        layout.addLayout(add_group)
        
        # Remove
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self.remove_keybind)
        layout.addWidget(remove_btn)
        
        # Note
        layout.addWidget(QLabel("Note: These keybinds create bookmarks at current time."))

    def populate_table(self):
        self.table.setRowCount(0)
        for key, cat in self.project.keybinds.items():
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(key))
            self.table.setItem(row, 1, QTableWidgetItem(cat))

    def update_cat_combo(self):
        self.cat_combo.clear()
        for cat in self.project.get_categories_by_type('bookmark'):
            self.cat_combo.addItem(cat.name)

    def capture_key(self):
        self.key_btn.setText("Press any key...")
        self.grabKeyboard()

    def keyPressEvent(self, event):
        if self.key_btn.isChecked():
            key = event.key()
            modifiers = event.modifiers()
            
            # Ignore modifier-only presses
            if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
                return
                
            try:
                # PyQt6 enum handling
                mod_val = modifiers.value
            except AttributeError:
                # Fallback if it's already int
                mod_val = int(modifiers)
                
            sequence = QKeySequence(key | mod_val)
            key_str = sequence.toString()
            
            self.captured_key = key_str
            self.key_btn.setText(key_str)
            self.key_btn.setChecked(False)
            self.releaseKeyboard()
        else:
            super().keyPressEvent(event)

    def add_keybind(self):
        if not self.captured_key:
            QMessageBox.warning(self, "Error", "Please press a key first.")
            return
            
        cat = self.cat_combo.currentText()
        if not cat:
            QMessageBox.warning(self, "Error", "No bookmark category selected.")
            return
            
        self.project.keybinds[self.captured_key] = cat
        self.populate_table()
        self.captured_key = None
        self.key_btn.setText("Press Key...")

    def remove_keybind(self):
        row = self.table.currentRow()
        if row >= 0:
            key = self.table.item(row, 0).text()
            if key in self.project.keybinds:
                del self.project.keybinds[key]
                self.populate_table()
