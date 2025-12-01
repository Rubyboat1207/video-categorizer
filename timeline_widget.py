from PyQt6.QtWidgets import QWidget, QMenu, QInputDialog, QMessageBox, QColorDialog
from PyQt6.QtCore import Qt, pyqtSignal, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPolygonF

class TimelineWidget(QWidget):
    positionChanged = pyqtSignal(int)  # Emits new position in ms when clicked
    dataChanged = pyqtSignal() # Emits when data modified via context menu
    aboutToModify = pyqtSignal() # Emits BEFORE data modification
    sectionDoubleClicked = pyqtSignal(object) # Emits the Section object

    def __init__(self, project, duration=0):
        super().__init__()
        self.project = project
        self.duration = duration  # Total duration in ms
        self.current_time = 0     # Current playback time in ms
        self.current_scope = None # None = Root, or Section object
        
        self.setMinimumHeight(100) # Increased for bookmark area
        self.setMouseTracking(True)
        
        self.zoom_level = 1.0
        self.scroll_offset = 0 # ms offset from start
        
        self.dragging_bookmark = None
        self.bm_area_height = 25
        self.row_height = 30
        
        # Edge dragging
        self.drag_edge_section = None
        self.drag_edge_type = None # 'start' or 'end'
        self.hover_section = None

    def set_scope(self, scope):
        """Sets the current editing scope (Root project or Section)"""
        self.current_scope = scope
        self.zoom_level = 1.0 # Reset zoom on enter
        if scope is None:
            self.scroll_offset = 0
        else:
            self.scroll_offset = scope.start_time
        self.update()

    def get_scope_bounds(self):
        if self.current_scope is None:
            return 0, self.duration
        else:
            end = self.current_scope.end_time if self.current_scope.end_time else self.duration
            return self.current_scope.start_time, end

    def get_visible_items(self):
        if self.current_scope is None:
            return self.project.sections, self.project.bookmarks
        else:
            return self.current_scope.sub_sections, self.current_scope.bookmarks

    def set_duration(self, duration):
        self.duration = duration
        self.update()

    def set_position(self, position):
        self.current_time = position
        self.update()

    def set_project(self, project):
        self.project = project
        self.current_scope = None
        self.update()

    def time_to_x(self, time_ms):
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

    def x_to_time(self, x):
        start, end = self.get_scope_bounds()
        total_scope_duration = max(1, end - start)
        visible_duration = total_scope_duration / self.zoom_level
        
        relative_time = (x / self.width()) * visible_duration
        return self.scroll_offset + relative_time

    def get_layer_map(self):
        # Identify all unique layers from project categories
        # Note: We rely on categories present in the project definition, not just used ones
        # to ensure stable ordering if possible.
        layers = sorted(list(set(c.layer for c in self.project.categories if c.type == 'section')))
        if not layers:
            layers = ["Default"]
        return {name: i for i, name in enumerate(layers)}

    def paintEvent(self, event):
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
        
        # Ensure widget is tall enough
        required_height = self.bm_area_height + num_layers * self.row_height
        if self.minimumHeight() != required_height:
            self.setMinimumHeight(required_height)

        # Draw Layer Backgrounds (Alternating?)
        for i in range(num_layers):
            y = self.bm_area_height + i * self.row_height
            if i % 2 == 1:
                painter.fillRect(0, y, width, self.row_height, QColor(255, 255, 255, 10))
            # Separator
            painter.setPen(QPen(QColor("#444444"), 1))
            painter.drawLine(0, y, width, y)

        # Separator for bookmark area
        painter.setPen(QPen(QColor("#555555"), 1))
        painter.drawLine(0, self.bm_area_height, width, self.bm_area_height)

        if self.duration <= 0:
            return
            
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
            y = self.bm_area_height + layer_idx * self.row_height + 2 # +2 padding
            h = self.row_height - 4

            painter.fillRect(int(start_x), y, int(rect_width), h, color)

        # Draw Bookmarks
        for bookmark in bookmarks:
            cat = next((c for c in self.project.categories if c.name == bookmark.category_name and c.type == 'bookmark'), None)
            if not cat:
                continue
            
            color = QColor(cat.color)
            x = self.time_to_x(bookmark.timestamp)
            
            if x < -10 or x > width + 10:
                continue
            
            # Draw line in main area (through all layers)
            painter.setPen(QPen(color, 2))
            painter.drawLine(int(x), self.bm_area_height, int(x), height)
            
            # Draw Handle in mini timeline
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(int(x)-4, 2, 8, self.bm_area_height-4)

        # Draw Current Time Indicator
        cursor_x = self.time_to_x(self.current_time)
        if 0 <= cursor_x <= width:
            painter.setPen(QPen(Qt.GlobalColor.white, 2))
            painter.drawLine(int(cursor_x), 0, int(cursor_x), height)

    def wheelEvent(self, event):
        if self.duration <= 0: return
        
        scope_start, scope_end = self.get_scope_bounds()
        total_scope_duration = max(1, scope_end - scope_start)

        # Zoom
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            zoom_factor = 1.1 if delta > 0 else 0.9
            
            # Zoom centered on mouse
            mouse_time = self.x_to_time(event.position().x())
            
            self.zoom_level *= zoom_factor
            self.zoom_level = max(1.0, min(self.zoom_level, 50.0))
            
            visible_duration = total_scope_duration / self.zoom_level
            new_offset = mouse_time - (event.position().x() / self.width()) * visible_duration
            
            # Clamp offset to scope bounds
            min_offset = scope_start
            max_offset = scope_end - visible_duration
            self.scroll_offset = max(min_offset, min(new_offset, max_offset))
            
        else: # Scroll
            delta = event.angleDelta().y()
            visible_duration = total_scope_duration / self.zoom_level
            scroll_amount = visible_duration * 0.1 # Scroll 10% of visible
            
            if delta > 0:
                self.scroll_offset -= scroll_amount
            else:
                self.scroll_offset += scroll_amount
            
            min_offset = scope_start
            max_offset = scope_end - visible_duration
            self.scroll_offset = max(min_offset, min(self.scroll_offset, max_offset))
            
        self.update()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            x = event.pos().x()
            y = event.pos().y()
            # Only trigger on main timeline area
            if y >= self.bm_area_height:
                time_at_cursor = self.x_to_time(x)
                sections, _ = self.get_visible_items()
                scope_start, scope_end = self.get_scope_bounds()
                layer_map = self.get_layer_map()

                # Determine which layer was clicked
                clicked_layer_idx = (y - self.bm_area_height) // self.row_height
                
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

    def mousePressEvent(self, event):
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
                    # Seek if clicked on empty space in mini timeline
                    new_pos = int(time_at_cursor)
                    # Clamp to scope for seeking? Or allow global?
                    # Let's allow global seek but clamped to video duration
                    new_pos = max(0, min(new_pos, int(self.duration)))
                    self.positionChanged.emit(new_pos)
            else:
                # Check Edge Drag (Section Bounds)
                if self.hover_section:
                    # Validate we are still on the same layer?
                    # For simplicity, edge drag works if you hover the edge.
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
                        self.drag_edge_section = None # False alarm

                if not self.drag_edge_section:
                    # Normal seek
                    new_pos = int(time_at_cursor)
                    new_pos = max(0, min(new_pos, int(self.duration)))
                    self.positionChanged.emit(new_pos)

    def mouseMoveEvent(self, event):
        x = event.pos().x()
        y = event.pos().y()
        time_at_cursor = self.x_to_time(x)
        
        sections, bookmarks = self.get_visible_items()
        scope_start, scope_end = self.get_scope_bounds()

        if self.dragging_bookmark:
            # Clamp to scope? Or just valid time?
            new_time = max(scope_start, min(time_at_cursor, scope_end))
            self.dragging_bookmark.timestamp = int(new_time)
            self.update()
            
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
                clicked_layer_idx = (y - self.bm_area_height) // self.row_height

                for section in sections:
                    cat = next((c for c in self.project.categories if c.name == section.category_name and c.type == 'section'), None)
                    if not cat: continue
                    
                    layer_idx = layer_map.get(cat.layer, 0)
                    # Only detect edge if mouse is on correct layer row
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

    def mouseReleaseEvent(self, event):
        if self.dragging_bookmark:
            self.project.events.append(f"Moved Bookmark '{self.dragging_bookmark.category_name}'")
            self.dataChanged.emit()
            self.dragging_bookmark = None
        
        if self.drag_edge_section:
            self.project.events.append(f"Resized Section '{self.drag_edge_section.category_name}'")
            self.dataChanged.emit()
            self.drag_edge_section = None
            self.drag_edge_type = None
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def contextMenuEvent(self, event):
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
        clicked_layer_idx = (y - self.bm_area_height) // self.row_height
        
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
            delete_action = menu.addAction("Delete Section")
            
            action = menu.exec(event.globalPos())
            
            if action and action != props_action: self.aboutToModify.emit()

            if action == props_action:
                self.show_properties(target_section)
            elif action == edit_action:
                self.edit_section_time(target_section)
            elif action == delete_action:
                sections.remove(target_section)
                self.project.events.append(f"Deleted Section: {target_section.category_name}")
                self.update()
                self.dataChanged.emit()

    def change_section_category(self, section, new_cat):
        section.category_name = new_cat
        self.project.events.append(f"Changed Section Category to {new_cat}")
        self.update()
        self.dataChanged.emit()

    def show_properties(self, section):
        end = section.end_time if section.end_time else "Ongoing"
        msg = f"Category: {section.category_name}\nStart: {section.start_time}ms\nEnd: {end}"
        QMessageBox.information(self, "Section Properties", msg)

    def edit_section_time(self, section):
        # Simplistic edit: change start time
        val, ok = QInputDialog.getInt(self, "Edit Start Time", "Start Time (ms):", section.start_time, 0, self.duration)
        if ok:
            section.start_time = val
            self.update()
            self.dataChanged.emit()
