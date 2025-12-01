import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict

@dataclass
class Category:
    name: str
    type: str  # 'section' or 'bookmark'
    color: str  # Hex code e.g., "#FF0000"
    layer: str = "Default" # For grouping stats/tracks

@dataclass
class Bookmark:
    category_name: str
    timestamp: int  # milliseconds
    description: str = ""

@dataclass
class Section:
    category_name: str
    start_time: int  # milliseconds
    end_time: Optional[int] = None  # milliseconds
    sub_sections: List['Section'] = field(default_factory=list)
    bookmarks: List[Bookmark] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data):
        # Handle simple fields
        sec = cls(
            category_name=data['category_name'],
            start_time=data['start_time'],
            end_time=data.get('end_time')
        )
        # Handle recursive sub-sections
        if 'sub_sections' in data:
            sec.sub_sections = [cls.from_dict(s) for s in data['sub_sections']]
        # Handle bookmarks
        if 'bookmarks' in data:
            sec.bookmarks = [Bookmark(**b) for b in data['bookmarks']]
        return sec

@dataclass
class Project:
    video_path: str = ""
    categories: List[Category] = field(default_factory=list)
    sections: List[Section] = field(default_factory=list)
    bookmarks: List[Bookmark] = field(default_factory=list)
    events: List[str] = field(default_factory=list)
    keybinds: Dict[str, str] = field(default_factory=dict) # Key (e.g. "Ctrl+B") -> Category Name

    def to_json(self):
        return json.dumps(asdict(self), indent=4)

    @classmethod
    def from_json(cls, json_str):
        data = json.loads(json_str)
        project = cls(video_path=data.get('video_path', ""))
        
        for cat_data in data.get('categories', []):
            project.categories.append(Category(**cat_data))
            
        for sec_data in data.get('sections', []):
            project.sections.append(Section.from_dict(sec_data))
            
        for bkm_data in data.get('bookmarks', []):
            project.bookmarks.append(Bookmark(**bkm_data))
            
        project.events = data.get('events', [])
        project.keybinds = data.get('keybinds', {})
            
        return project

    def save(self, filepath):
        with open(filepath, 'w') as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, filepath):
        with open(filepath, 'r') as f:
            return cls.from_json(f.read())

    def get_categories_by_type(self, type_name):
        return [c for c in self.categories if c.type == type_name]

    def add_category(self, name, type_name, color, layer="Default"):
        if not any(c.name == name and c.type == type_name for c in self.categories):
            self.categories.append(Category(name, type_name, color, layer))

    def remove_category(self, name, type_name):
        self.categories = [c for c in self.categories if not (c.name == name and c.type == type_name)]
        # Also maybe clean up sections/bookmarks with this category? 
        # For now, let's keep them but they might be orphaned or we can handle it in UI.
