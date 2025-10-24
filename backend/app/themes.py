from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class Theme:
    """Represents a theme configuration"""
    id: str
    name: str
    css_path: str
    is_dark: bool
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "css_path": self.css_path,
            "is_dark": self.is_dark
        }

class ThemeRegistry:
    """Central registry for managing themes"""
    
    def __init__(self):
        self._themes: Dict[str, Theme] = {}
        self._register_default_themes()
    
    def register_theme(self, theme: Theme) -> None:
        """Register a new theme"""
        self._themes[theme.id] = theme
    
    def get_theme(self, theme_id: str) -> Optional[Theme]:
        """Get a theme by ID"""
        return self._themes.get(theme_id)
    
    def get_all_themes(self) -> List[Theme]:
        """Get all registered themes"""
        return list(self._themes.values())
    
    def theme_exists(self, theme_id: str) -> bool:
        """Check if a theme exists"""
        return theme_id in self._themes
    
    def _register_default_themes(self) -> None:
        """Register built-in themes"""
        self.register_theme(Theme(id="default_dark", name="Default Dark", css_path="/static/css/themes/default_dark.css", is_dark=True))
        self.register_theme(Theme(id="oled", name="OLED", css_path="/static/css/themes/oled.css", is_dark=True))
        self.register_theme(Theme(id="ctp_mocha", name="Catppuccin Mocha", css_path="/static/css/themes/ctp_mocha.css", is_dark=True))
        self.register_theme(Theme(id="ctp_macchiato", name="Catppuccin Macchiato", css_path="/static/css/themes/ctp_macchiato.css", is_dark=True))
        self.register_theme(Theme(id="ctp_frappe", name="Catppuccin Frappé", css_path="/static/css/themes/ctp_frappe.css", is_dark=True))
        self.register_theme(Theme(id="ctp_latte", name="Catppuccin Latte", css_path="/static/css/themes/ctp_latte.css", is_dark=False))
        self.register_theme(Theme(id="gruvbox_dark_hard", name="gruvbox dark (hard)", css_path="/static/css/themes/gruvbox_dark_hard.css", is_dark=True))
        self.register_theme(Theme(id="gruvbox_light_soft", name="gruvbox light (soft)", css_path="/static/css/themes/gruvbox_light_soft.css", is_dark=False))
        self.register_theme(Theme(id="everforest_dark_hard", name="Everforest Dark (Hard)", css_path="/static/css/themes/everforest_dark_hard.css", is_dark=True))
        self.register_theme(Theme(id="everforest_light_soft", name="Everforest Light (Soft)", css_path="/static/css/themes/everforest_light_soft.css", is_dark=False))
        self.register_theme(Theme(id="green", name="Green", css_path="/static/css/themes/green.css", is_dark=False))

# Global theme registry instance
theme_registry = ThemeRegistry()
