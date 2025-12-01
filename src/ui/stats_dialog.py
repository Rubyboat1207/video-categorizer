import matplotlib
matplotlib.use('Qt5Agg') # compatible with Qt6 for embedding
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTabWidget, QWidget, QPushButton, QHBoxLayout, QFileDialog, QMessageBox, QComboBox, QLabel, QScrollArea
import collections
import csv

class StatsDialog(QDialog):
    def __init__(self, project, total_duration, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Video Analysis Stats")
        self.resize(900, 700)
        self.project = project
        self.total_duration = total_duration

        layout = QVBoxLayout(self)
        
        # Scope Selection
        scope_layout = QHBoxLayout()
        scope_layout.addWidget(QLabel("Analysis Scope:"))
        self.scope_combo = QComboBox()
        self.scope_combo.currentIndexChanged.connect(self.on_scope_changed)
        scope_layout.addWidget(self.scope_combo)
        layout.addLayout(scope_layout)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Export Button
        btn_layout = QHBoxLayout()
        export_btn = QPushButton("Export Current View to CSV")
        export_btn.clicked.connect(self.export_csv)
        btn_layout.addStretch()
        btn_layout.addWidget(export_btn)
        layout.addLayout(btn_layout)

        # Map index to data: (sections, bookmarks, duration)
        self.scope_data = {}
        self.populate_scopes()

    def populate_scopes(self):
        self.scope_combo.clear()
        self.scope_data = {}
        
        # Add Full Video (Root)
        self.scope_combo.addItem("Full Video")
        self.scope_data[0] = (self.project.sections, self.project.bookmarks, self.total_duration)
        
        # Recursively add sections
        self.add_sections_recursive(self.project.sections, level=1)
        
    def add_sections_recursive(self, sections, level):
        for section in sections:
            indent = "  " * level
            name = f"{indent}Section: {section.category_name} ({section.start_time}-{section.end_time})"
            self.scope_combo.addItem(name)
            idx = self.scope_combo.count() - 1
            
            end = section.end_time if section.end_time else self.total_duration
            duration = max(0, end - section.start_time)
            
            self.scope_data[idx] = (section.sub_sections, section.bookmarks, duration)
            
            self.add_sections_recursive(section.sub_sections, level + 1)

    def on_scope_changed(self, index):
        if index in self.scope_data:
            sections, bookmarks, duration = self.scope_data[index]
            self.update_charts(sections, bookmarks, duration)

    def update_charts(self, sections, bookmarks, duration):
        self.tabs.clear()
        self.create_section_pie_chart(sections, duration)
        self.create_bookmark_bar_chart(bookmarks)

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Stats", "", "CSV Files (*.csv)")
        if path:
            try:
                idx = self.scope_combo.currentIndex()
                if idx not in self.scope_data: return
                sections, bookmarks, duration = self.scope_data[idx]
                
                with open(path, 'w', newline='') as csvfile:
                    writer = csv.writer(csvfile)
                    
                    writer.writerow(["Scope", self.scope_combo.currentText().strip()])
                    writer.writerow([])
                    
                    # Sections
                    writer.writerow(["Type", "Category", "Start Time (ms)", "End Time (ms)", "Duration (ms)"])
                    for section in sections:
                        end = section.end_time if section.end_time is not None else duration
                        # Note: timestamps here are usually absolute, but visually in stats we might care about relative?
                        # Let's keep absolute for CSV accuracy.
                        writer.writerow(["Sub-Section", section.category_name, section.start_time, end, max(0, end - section.start_time)])
                    
                    writer.writerow([])
                    
                    # Bookmarks
                    writer.writerow(["Type", "Category", "Timestamp (ms)", "Description"])
                    for bm in bookmarks:
                        writer.writerow(["Bookmark", bm.category_name, bm.timestamp, bm.description])
                
                QMessageBox.information(self, "Success", "Stats exported successfully.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export: {str(e)}")

    def create_section_pie_chart(self, sections, duration_scope):
        # Container for multiple charts
        tab = QWidget()
        main_layout = QVBoxLayout(tab)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)

        # 1. Identify Layers present in this scope
        # Note: We can either show ALL defined layers or only those with data.
        # Showing all layers might be better for consistency.
        # But we need to know "duration used per layer".
        
        # Group sections by Layer
        sections_by_layer = collections.defaultdict(list)
        for section in sections:
            # Find category def
            cat = next((c for c in self.project.categories if c.name == section.category_name and c.type == 'section'), None)
            layer = cat.layer if cat else "Unknown"
            sections_by_layer[layer].append(section)
            
        # Also include layers that have no sections but are defined? 
        # Maybe not necessary if empty.
        
        # Sort layers
        sorted_layers = sorted(sections_by_layer.keys())
        if not sorted_layers and sections: sorted_layers = ["Default"] # Fallback

        if not sorted_layers:
             content_layout.addWidget(QLabel("No Section Data"))

        for layer in sorted_layers:
            layer_sections = sections_by_layer.get(layer, [])
            
            # Calculate durations for this layer
            cat_durations = collections.defaultdict(int)
            total_layer_duration = 0
            
            for section in layer_sections:
                if section.end_time is None: continue
                dur = max(0, section.end_time - section.start_time)
                cat_durations[section.category_name] += dur
                total_layer_duration += dur # This counts overlap if any, but sections in same layer shouldn't overlap ideally.

            # Prepare data
            labels = []
            sizes = []
            colors = []
            cat_map = {c.name: c for c in self.project.categories if c.type == 'section'}
            
            for name, duration in cat_durations.items():
                labels.append(name)
                sizes.append(duration)
                if name in cat_map:
                    colors.append(cat_map[name].color)
                else:
                    colors.append('#CCCCCC')

            # Uncategorized time in this layer?
            # A layer tracks time across the whole durationScope.
            # So "Uncategorized" = duration_scope - sum(durations).
            if duration_scope > total_layer_duration:
                labels.append("Uncategorized")
                sizes.append(duration_scope - total_layer_duration)
                colors.append("#888888")
            
            # Create Chart
            fig = Figure(figsize=(5, 4), dpi=100) # Increased height
            ax = fig.add_subplot(111)
            
            if sizes:
                # Calculate percentages manually for legend
                total = sum(sizes)
                percent_labels = [f"{l} ({s/total*100:.1f}%)" for l, s in zip(labels, sizes)]

                # No autopct to avoid collision inside the pie
                wedges, texts = ax.pie(sizes, colors=colors, startangle=90)
                
                # Legend with percentages
                ax.legend(wedges, percent_labels, title="Categories", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
                
                ax.axis('equal') 
                ax.set_title(f"Layer: {layer}", pad=20)
                fig.tight_layout()
            else:
                ax.text(0.5, 0.5, f"No Data for Layer: {layer}", ha='center')

            canvas = FigureCanvas(fig)
            canvas.setMinimumHeight(350)
            content_layout.addWidget(canvas)
            
            # Add Separator
            content_layout.addWidget(QLabel("---"))

        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)
        self.tabs.addTab(tab, "Section Breakdown (Layers)")

    def create_bookmark_bar_chart(self, bookmarks):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        cat_counts = collections.defaultdict(int)
        for bm in bookmarks:
            cat_counts[bm.category_name] += 1
            
        labels = list(cat_counts.keys())
        counts = list(cat_counts.values())
        
        # Colors
        cat_map = {c.name: c for c in self.project.categories if c.type == 'bookmark'}
        colors = [cat_map[l].color if l in cat_map else '#CCCCCC' for l in labels]

        fig = Figure(figsize=(5, 4), dpi=100)
        ax = fig.add_subplot(111)
        
        if counts:
            bars = ax.bar(labels, counts, color=colors)
            ax.set_ylabel('Count')
            ax.set_title('Bookmark Frequency')
            # Rotate labels if needed
            fig.autofmt_xdate(rotation=45)
            fig.tight_layout()
        else:
            ax.text(0.5, 0.5, "No Bookmark Data", ha='center')

        canvas = FigureCanvas(fig)
        layout.addWidget(canvas)
        self.tabs.addTab(tab, "Bookmark Counts")
