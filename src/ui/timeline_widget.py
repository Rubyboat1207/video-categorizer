from PyQt6.QtWidgets import QWidget, QMenu, QInputDialog, QMessageBox, QColorDialog, QScrollBar
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QEvent
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPolygonF, QResizeEvent, QWheelEvent, QMouseEvent, QContextMenuEvent
from typing import Optional, List, Tuple, Dict, Any
from src.models import Project, Section, Bookmark, Category

class TimelineWidget(QWidget):
    positionChanged = pyqtSignal(int)  # Emits new position in ms when clicked
    dataChanged = pyqtSignal() # Emits when data modified via context menu
    aboutToModify = pyqtSignal() # Emits BEFORE data modification
    sectionDoubleClicked = pyqtSignal(object) # Emits the Section object
    exportSectionRequested = pyqtSignal(object) # Emits section to export

    def __init__(self, project: Project, duration: int = 0):
        super().__init__()
        self.project = project
        self.duration = duration  # Total duration in ms
        self.current_time = 0     # Current playback time in ms
        self.current_scope: Optional[Section] = None # None = Root, or Section object
        
        self.setMinimumHeight(100)
        self.setMouseTracking(True)
        
        self.zoom_level = 1.0
        self.scroll_offset = 0 # ms offset from start
        self.vertical_scroll_offset = 0
        
        self.dragging_bookmark: Optional[Bookmark] = None
        self.dragging_playhead = False
        
        self.bm_area_height = 25
        self.min_row_height = 50
        self.current_row_height = 50
        self.scrollbar_height = 15
        
        # Horizontal Scrollbar (Time)
        self.scrollbar = QScrollBar(Qt.Orientation.Horizontal, self)
        self.scrollbar.setFixedHeight(self.scrollbar_height)
        self.scrollbar.valueChanged.connect(self.on_scrollbar_change)
        
        # Edge dragging
        self.drag_edge_section: Optional[Section] = None
        self.drag_edge_type: Optional[str] = None # 'start' or 'end'
        self.hover_section: Optional[Section] = None

    def resizeEvent(self, event: QResizeEvent) -> None:
        self.scrollbar.setGeometry(0, self.height() - self.scrollbar_height, self.width(), self.scrollbar_height)
        self.update_scrollbar()
        super().resizeEvent(event)

    def on_scrollbar_change(self, value: int) -> None:
        # Value is scroll_offset
        self.scroll_offset = value
        self.update()

    def update_scrollbar(self) -> None:
        scope_start, scope_end = self.get_scope_bounds()
        total_scope_duration = max(1, scope_end - scope_start)
        visible_duration = total_scope_duration / self.zoom_level
        
        self.scrollbar.setMinimum(scope_start)
        self.scrollbar.setMaximum(max(scope_start, int(scope_end - visible_duration)))
        self.scrollbar.setPageStep(int(visible_duration))
        self.scrollbar.setValue(int(self.scroll_offset))

    def set_scope(self, scope: Optional[Section]) -> None:
        """Sets the current editing scope (Root project or Section)"""
        self.current_scope = scope
        self.zoom_level = 1.0 # Reset zoom on enter
        if scope is None:
            self.scroll_offset = 0
        else:
            self.scroll_offset = scope.start_time
        self.update()

    def get_scope_bounds(self) -> Tuple[int, int]:
        if self.current_scope is None:
            return 0, self.duration
        else:
            end = self.current_scope.end_time if self.current_scope.end_time else self.duration
            return self.current_scope.start_time, end

    def get_visible_items(self) -> Tuple[List[Section], List[Bookmark]]:
        if self.current_scope is None:
            return self.project.sections, self.project.bookmarks
        else:
            return self.current_scope.sub_sections, self.current_scope.bookmarks

    def set_duration(self, duration: int) -> None:
        self.duration = duration
        self.update_scrollbar()
        self.update()

    def set_position(self, position: int) -> None:
        self.current_time = position
        self.update()

    def set_project(self, project: Project) -> None:
        self.project = project
        self.current_scope = None
        self.update_scrollbar()
        self.update()

    def time_to_x(self, time_ms: int) -> float:
        start, end = self.get_scope_bounds()
        total_scope_duration = max(1, end - start)
        
        visible_duration = total_scope_duration / self.zoom_level
        
        # Adjust scroll offset relative to scope start
        effective_offset = self.scroll_offset
        if self.current_scope is None:
             effective_offset = self.scroll_offset
        
        # If in a section, the "timeline starts" at section.start_time visually
        # But we want to support scrolling.
        # Let's say: relative_time = time_ms - current_view_start
        
        current_view_start = self.scroll_offset
        
        relative_time = time_ms - current_view_start
        return (relative_time / visible_duration) * self.width()

    def x_to_time(self, x: float) -> float:
        start, end = self.get_scope_bounds()
        total_scope_duration = max(1, end - start)
        visible_duration = total_scope_duration / self.zoom_level
        
        relative_time = (x / self.width()) * visible_duration
        return self.scroll_offset + relative_time

    def get_layer_map(self) -> Dict[str, int]:
        # Identify all unique layers from project categories
        # Note: We rely on categories present in the project definition, not just used ones
        # to ensure stable ordering if possible.
        layers = sorted(list(set(c.layer for c in self.project.categories if c.type == 'section')))
        if not layers:
            layers = ["Default"]
        return {name: i for i, name in enumerate(layers)}

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        
        # Draw background
        bg_color = QColor("#333333")
        if self.current_scope:
            bg_color = QColor("#2a2a40") 
            
        painter.fillRect(0, 0, width, height, bg_color)
        
        # Calculate Layers
        layer_map = self.get_layer_map()
        num_layers = len(layer_map)
        
        # Calculate Row Height dynamically
        available_height = height - self.bm_area_height - self.scrollbar_height
        if num_layers > 0:
            self.current_row_height = max(self.min_row_height, available_height / num_layers)
        else:
            self.current_row_height = self.min_row_height

        # Apply Vertical Scroll Transform
        painter.save()
        # Clip to layer area
        painter.setClipRect(0, self.bm_area_height, width, available_height)
        painter.translate(0, -self.vertical_scroll_offset)

        # Draw Layer Backgrounds
        for i in range(num_layers):
            y = self.bm_area_height + i * self.current_row_height
            if i % 2 == 1:
                painter.fillRect(0, int(y), width, int(self.current_row_height), QColor(255, 255, 255, 10))
            # Separator
            painter.setPen(QPen(QColor("#444444"), 1))
            painter.drawLine(0, int(y), width, int(y))

        scope_start, scope_end = self.get_scope_bounds()
        sections, bookmarks = self.get_visible_items()

        # Draw Sections
        for section in sections:
            cat = next((c for c in self.project.categories if c.name == section.category_name and c.type == 'section'), None)
            if not cat:
                continue

            color = QColor(cat.color)
            layer_idx = layer_map.get(cat.layer, 0)
            
            start_x = self.time_to_x(section.start_time)
            end_time = section.end_time if section.end_time is not None else self.current_time
            end_time = min(end_time, scope_end)
            end_x = self.time_to_x(end_time)
            
            if end_x < 0 or start_x > width:
                continue
                
            rect_width = max(1, end_x - start_x) 
            y = self.bm_area_height + layer_idx * self.current_row_height + 2
            h = self.current_row_height - 4

            # Main Section Rect
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(int(start_x), int(y), int(rect_width), int(h), 4, 4)
            
            # Sub-sections (Bottom Half)
            if hasattr(section, 'sub_sections') and section.sub_sections:
                sub_y = y + h / 2
                sub_h = h / 2
                for sub in section.sub_sections:
                    sub_cat = next((c for c in self.project.categories if c.name == sub.category_name and c.type == 'section'), None)
                    if not sub_cat: continue
                    
                    sub_color = QColor(sub_cat.color)
                    
                    # Sub-section times are absolute? If they are relative to section, we adjust.
                    # Assuming absolute for now based on previous implementation.
                    s_start = max(section.start_time, sub.start_time)
                    s_end = sub.end_time if sub.end_time else end_time
                    s_end = min(end_time, s_end)
                    
                    sx = self.time_to_x(s_start)
                    ex = self.time_to_x(s_end)
                    sw = max(1, ex - sx)
                    
                    painter.setBrush(QBrush(sub_color))
                    painter.drawRoundedRect(int(sx), int(sub_y), int(sw), int(sub_h), 2, 2)

        painter.restore()

        # Draw Bookmarks (Fixed Top Area)
        # Separator for bookmark area
        painter.setPen(QPen(QColor("#555555"), 1))
        painter.drawLine(0, self.bm_area_height, width, self.bm_area_height)

        for bookmark in bookmarks:
            cat = next((c for c in self.project.categories if c.name == bookmark.category_name and c.type == 'bookmark'), None)
            if not cat:
                continue
            
            color = QColor(cat.color)
            x = self.time_to_x(bookmark.timestamp)
            
            if x < -10 or x > width + 10:
                continue
            
            # Draw line in main area (through all layers) - Need to respect scroll?
            # Actually, line should go full height, but clipped by scroll area?
            # Let's draw line from top to bottom, but visually it might look weird if scrolling.
            # User focus is playhead.
            
            painter.setPen(QPen(color, 2))
            painter.drawLine(int(x), self.bm_area_height, int(x), height - self.scrollbar_height)
            
            # Draw Handle in mini timeline
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(int(x)-4, 2, 8, self.bm_area_height-4)

        # Draw Current Time Indicator
        cursor_x = self.time_to_x(self.current_time)
        if 0 <= cursor_x <= width:
            painter.setPen(QPen(Qt.GlobalColor.white, 2))
            painter.drawLine(int(cursor_x), 0, int(cursor_x), height - self.scrollbar_height)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.duration <= 0: return
        
        scope_start, scope_end = self.get_scope_bounds()
        total_scope_duration = max(1, scope_end - scope_start)
        
        modifiers = event.modifiers()
        delta = event.angleDelta().y()

        if modifiers & Qt.KeyboardModifier.ControlModifier:
            # Zoom (Ctrl + Wheel)
            zoom_factor = 1.1 if delta > 0 else 0.9
            mouse_time = self.x_to_time(event.position().x())
            self.zoom_level *= zoom_factor
            self.zoom_level = max(1.0, min(self.zoom_level, 50.0))
            
            visible_duration = total_scope_duration / self.zoom_level
            new_offset = mouse_time - (event.position().x() / self.width()) * visible_duration
            
            min_offset = scope_start
            max_offset = max(scope_start, scope_end - visible_duration)
            self.scroll_offset = max(min_offset, min(new_offset, max_offset))
            self.update_scrollbar()

        elif modifiers & Qt.KeyboardModifier.ShiftModifier:
            # Vertical Scroll (Layers) (Shift + Wheel)
            scroll_speed = 30
            if delta > 0:
                self.vertical_scroll_offset -= scroll_speed
            else:
                self.vertical_scroll_offset += scroll_speed
            
            # Clamp vertical scroll
            # Calculate total content height
            num_layers = len(self.get_layer_map())
            content_height = num_layers * self.current_row_height
            visible_height = self.height() - self.bm_area_height - self.scrollbar_height
            
            max_scroll = max(0, content_height - visible_height)
            self.vertical_scroll_offset = max(0, min(self.vertical_scroll_offset, max_scroll))

        else:
            # Horizontal Scroll (Time) (Normal Wheel)
            visible_duration = total_scope_duration / self.zoom_level
            scroll_amount = visible_duration * 0.1 
            if delta > 0:
                self.scroll_offset -= int(scroll_amount)
            else:
                self.scroll_offset += int(scroll_amount)
            
            min_offset = scope_start
            max_offset = max(scope_start, scope_end - visible_duration)
            self.scroll_offset = int(max(min_offset, min(self.scroll_offset, max_offset)))
            self.update_scrollbar()

        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            x = event.pos().x()
            y = event.pos().y()
            # Only trigger on main timeline area
            if y >= self.bm_area_height:
                time_at_cursor = self.x_to_time(x)
                sections, _ = self.get_visible_items()
                scope_start, scope_end = self.get_scope_bounds()
                layer_map = self.get_layer_map()

                # Adjust y for scroll
                adj_y = y - self.bm_area_height + self.vertical_scroll_offset
                clicked_layer_idx = int(adj_y // self.current_row_height)
                
                # Find section under cursor in that layer
                target_section = None
                for section in sections:
                    cat = next((c for c in self.project.categories if c.name == section.category_name and c.type == 'section'), None)
                    if not cat: continue
                    
                    layer_idx = layer_map.get(cat.layer, 0)
                    if layer_idx != clicked_layer_idx: continue

                    end = section.end_time if section.end_time is not None else self.current_time
                    end = min(end, scope_end)
                    if section.start_time <= time_at_cursor <= end:
                        target_section = section
                        break
                
                if target_section:
                    self.sectionDoubleClicked.emit(target_section)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.duration <= 0: return
        
        sections, bookmarks = self.get_visible_items()
        scope_start, scope_end = self.get_scope_bounds()

        if event.button() == Qt.MouseButton.LeftButton:
            x = event.pos().x()
            y = event.pos().y()
            time_at_cursor = self.x_to_time(x)
            
            # Check bookmark drag (Mini Timeline)
            if y < self.bm_area_height:
                # Find close bookmark
                for bm in bookmarks:
                    bm_x = self.time_to_x(bm.timestamp)
                    if abs(x - bm_x) < 6: # 12px hit width
                        self.dragging_bookmark = bm
                        self.aboutToModify.emit()
                        break
                
                if not self.dragging_bookmark:
                    # Start dragging Playhead
                    self.dragging_playhead = True
                    new_pos = max(0, min(int(time_at_cursor), int(self.duration)))
                    self.positionChanged.emit(new_pos)
            else:
                # Check Edge Drag (Section Bounds)
                if self.hover_section:
                    self.drag_edge_section = self.hover_section
                    self.aboutToModify.emit()
                    # Determine start or end based on distance
                    start_x = self.time_to_x(self.drag_edge_section.start_time)
                    end_time = self.drag_edge_section.end_time if self.drag_edge_section.end_time else self.current_time
                    end_time = min(end_time, scope_end)
                    end_x = self.time_to_x(end_time)
                    
                    if abs(x - start_x) < 6:
                        self.drag_edge_type = 'start'
                    elif abs(x - end_x) < 6:
                        self.drag_edge_type = 'end'
                    else:
                        self.drag_edge_section = None 

                if not self.drag_edge_section:
                    # If not dragging edge, allow playhead seek via lower area too?
                    # User asked "drag click the playhead to move it instead of just clicking"
                    # Usually clicking empty space moves playhead. Dragging it keeps moving it.
                    self.dragging_playhead = True
                    new_pos = max(0, min(int(time_at_cursor), int(self.duration)))
                    self.positionChanged.emit(new_pos)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        x = event.pos().x()
        y = event.pos().y()
        time_at_cursor = self.x_to_time(x)
        
        sections, bookmarks = self.get_visible_items()
        scope_start, scope_end = self.get_scope_bounds()

        if self.dragging_bookmark:
            new_time = max(scope_start, min(time_at_cursor, scope_end))
            self.dragging_bookmark.timestamp = int(new_time)
            self.update()
            
        elif self.dragging_playhead:
            new_pos = max(0, min(int(time_at_cursor), int(self.duration)))
            self.positionChanged.emit(new_pos)
            
        elif self.drag_edge_section:
            new_time = max(scope_start, min(time_at_cursor, scope_end))
            if self.drag_edge_type == 'start':
                end = self.drag_edge_section.end_time if self.drag_edge_section.end_time else scope_end
                if new_time < end:
                    self.drag_edge_section.start_time = int(new_time)
            elif self.drag_edge_type == 'end':
                if new_time > self.drag_edge_section.start_time:
                    self.drag_edge_section.end_time = int(new_time)
            self.update()
            
        else:
            # Hover detection for cursor change
            if y >= self.bm_area_height:
                hovering_edge = False
                self.hover_section = None
                
                layer_map = self.get_layer_map()
                adj_y = y - self.bm_area_height + self.vertical_scroll_offset
                clicked_layer_idx = int(adj_y // self.current_row_height)

                for section in sections:
                    cat = next((c for c in self.project.categories if c.name == section.category_name and c.type == 'section'), None)
                    if not cat: continue
                    
                    layer_idx = layer_map.get(cat.layer, 0)
                    if layer_idx != clicked_layer_idx: continue

                    start_x = self.time_to_x(section.start_time)
                    end_time = section.end_time if section.end_time is not None else self.current_time
                    end_time = min(end_time, scope_end)
                    end_x = self.time_to_x(end_time)
                    
                    if abs(x - start_x) < 6:
                        self.setCursor(Qt.CursorShape.SizeHorCursor)
                        self.hover_section = section
                        hovering_edge = True
                        break
                    elif abs(x - end_x) < 6:
                        self.setCursor(Qt.CursorShape.SizeHorCursor)
                        self.hover_section = section
                        hovering_edge = True
                        break
                
                if not hovering_edge:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self.dragging_bookmark:
            self.project.events.append(f"Moved Bookmark '{self.dragging_bookmark.category_name}'")
            self.dataChanged.emit()
            self.dragging_bookmark = None
        
        self.dragging_playhead = False
        
        if self.drag_edge_section:
            self.project.events.append(f"Resized Section '{self.drag_edge_section.category_name}'")
            self.dataChanged.emit()
            self.drag_edge_section = None
            self.drag_edge_type = None
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        if self.duration <= 0:
            return

        x = event.pos().x()
        y = event.pos().y()
        click_time = self.x_to_time(x)
        
        sections, bookmarks = self.get_visible_items()
        scope_start, scope_end = self.get_scope_bounds()

        # If in bookmark area, maybe bookmark context menu?
        if y < self.bm_area_height:
            # Check bookmark hit
            target_bm = None
            for bm in bookmarks:
                bm_x = self.time_to_x(bm.timestamp)
                if abs(x - bm_x) < 6:
                    target_bm = bm
                    break
            
            if target_bm:
                menu = QMenu(self)
                del_action = menu.addAction("Delete Bookmark")
                edit_action = menu.addAction("Edit Description")
                action = menu.exec(event.globalPos())
                
                if action: self.aboutToModify.emit()

                if action == del_action:
                    bookmarks.remove(target_bm)
                    self.project.events.append("Deleted Bookmark")
                    self.update()
                    self.dataChanged.emit()
                elif action == edit_action:
                    desc, ok = QInputDialog.getText(self, "Edit Bookmark", "Description:", text=target_bm.description)
                    if ok:
                        target_bm.description = desc
                        self.update()
                        self.dataChanged.emit()
            return

        # Find section under cursor (Main Timeline)
        target_section = None
        layer_map = self.get_layer_map()
        adj_y = y - self.bm_area_height + self.vertical_scroll_offset
        clicked_layer_idx = int(adj_y // self.current_row_height)
        
        for section in sections:
            cat = next((c for c in self.project.categories if c.name == section.category_name and c.type == 'section'), None)
            if not cat: continue
            
            layer_idx = layer_map.get(cat.layer, 0)
            if layer_idx != clicked_layer_idx: continue

            end = section.end_time if section.end_time is not None else self.current_time
            end = min(end, scope_end)
            if section.start_time <= click_time <= end:
                target_section = section
                break
        
        if target_section:
            menu = QMenu(self)
            
            # Actions
            props_action = menu.addAction("Properties")
            edit_action = menu.addAction("Edit Time")
            
            type_menu = menu.addMenu("Change Category")
            for cat in self.project.get_categories_by_type('section'):
                act = type_menu.addAction(cat.name)
                act.triggered.connect(lambda ch, s=target_section, c=cat.name: self.change_section_category(s, c))
            
            menu.addSeparator()
            export_action = menu.addAction("Export Video Segment")
            menu.addSeparator()
            delete_action = menu.addAction("Delete Section")
            
            action = menu.exec(event.globalPos())
            
            if action and action != props_action and action != export_action: self.aboutToModify.emit()

            if action == props_action:
                self.show_properties(target_section)
            elif action == edit_action:
                self.edit_section_time(target_section)
            elif action == export_action:
                self.exportSectionRequested.emit(target_section)
            elif action == delete_action:
                sections.remove(target_section)
                self.project.events.append(f"Deleted Section: {target_section.category_name}")
                self.update()
                self.dataChanged.emit()

    def change_section_category(self, section: Section, new_cat: str) -> None:
        section.category_name = new_cat
        self.project.events.append(f"Changed Section Category to {new_cat}")
        self.update()
        self.dataChanged.emit()

    def show_properties(self, section: Section) -> None:
        end = section.end_time if section.end_time else "Ongoing"
        msg = f"Category: {section.category_name}\nStart: {section.start_time}ms\nEnd: {end}"
        QMessageBox.information(self, "Section Properties", msg)

    def edit_section_time(self, section: Section) -> None:
        # Simplistic edit: change start time
        val, ok = QInputDialog.getInt(self, "Edit Start Time", "Start Time (ms):", section.start_time, 0, self.duration)
        if ok:
            section.start_time = val
            self.update()
            self.dataChanged.emit()
