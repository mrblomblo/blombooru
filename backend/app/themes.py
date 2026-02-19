from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass
class Theme:
    """Represents a theme configuration"""
    id: str
    name: str
    css_path: str
    is_dark: bool
    primary_color: str
    background_color: str
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "css_path": self.css_path,
            "is_dark": self.is_dark,
            "primary_color": self.primary_color,
            "background_color": self.background_color
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
        self.register_theme(Theme(
            id="default_dark", 
            name="Default Dark", 
            css_path="/static/css/themes/default_dark.css", 
            is_dark=True,
            primary_color="#3b82f6",
            background_color="#0f172a"
        ))
        self.register_theme(Theme(
            id="oled", 
            name="OLED", 
            css_path="/static/css/themes/oled.css", 
            is_dark=True,
            primary_color="#ffffff",
            background_color="#000000"
        ))
        self.register_theme(Theme(
            id="ctp_mocha", 
            name="Catppuccin Mocha", 
            css_path="/static/css/themes/ctp_mocha.css", 
            is_dark=True,
            primary_color="#fab387",
            background_color="#11111b"
        ))
        self.register_theme(Theme(
            id="ctp_macchiato", 
            name="Catppuccin Macchiato", 
            css_path="/static/css/themes/ctp_macchiato.css", 
            is_dark=True,
            primary_color="#f5a97f",
            background_color="#181926"
        ))
        self.register_theme(Theme(
            id="ctp_frappe", 
            name="Catppuccin Frappé", 
            css_path="/static/css/themes/ctp_frappe.css", 
            is_dark=True,
            primary_color="#ef9f76",
            background_color="#232634"
        ))
        self.register_theme(Theme(
            id="ctp_latte", 
            name="Catppuccin Latte", 
            css_path="/static/css/themes/ctp_latte.css", 
            is_dark=False,
            primary_color="#fe640b",
            background_color="#dce0e8"
        ))
        self.register_theme(Theme(
            id="gruvbox_dark_hard", 
            name="gruvbox dark (hard)", 
            css_path="/static/css/themes/gruvbox_dark_hard.css", 
            is_dark=True,
            primary_color="#d79921",
            background_color="#1d2021"
        ))
        self.register_theme(Theme(
            id="gruvbox_light_soft", 
            name="gruvbox light (soft)", 
            css_path="/static/css/themes/gruvbox_light_soft.css", 
            is_dark=False,
            primary_color="#d79921",
            background_color="#f2e5bc"
        ))
        self.register_theme(Theme(
            id="everforest_dark_hard", 
            name="Everforest Dark (Hard)", 
            css_path="/static/css/themes/everforest_dark_hard.css", 
            is_dark=True,
            primary_color="#a7c080",
            background_color="#1e2326"
        ))
        self.register_theme(Theme(
            id="everforest_light_soft", 
            name="Everforest Light (Soft)", 
            css_path="/static/css/themes/everforest_light_soft.css", 
            is_dark=False,
            primary_color="#8da101",
            background_color="#f3ead3"
        ))
        self.register_theme(Theme(
            id="autumn", 
            name="Autumn", 
            css_path="/static/css/themes/autumn.css", 
            is_dark=True,
            primary_color="#d4741a",
            background_color="#1a1815"
        ))
        self.register_theme(Theme(
            id="dracula", 
            name="Dracula", 
            css_path="/static/css/themes/dracula.css", 
            is_dark=True,
            primary_color="#bd93f9",
            background_color="#282a36"
        ))
        self.register_theme(Theme(
            id="nord_polar_night", 
            name="Nord Polar Night", 
            css_path="/static/css/themes/nord_polar_night.css", 
            is_dark=True,
            primary_color="#88c0d0",
            background_color="#2e3440"
        ))
        self.register_theme(Theme(
            id="nord_snow_storm", 
            name="Nord Snow Storm", 
            css_path="/static/css/themes/nord_snow_storm.css", 
            is_dark=False,
            primary_color="#5e81ac",
            background_color="#eceff4"
        ))
        self.register_theme(Theme(
            id="rose_pine", 
            name="Rosé Pine", 
            css_path="/static/css/themes/rose_pine.css", 
            is_dark=True,
            primary_color="#c4a7e7",
            background_color="#191724"
        ))
        self.register_theme(Theme(
            id="rose_pine_moon", 
            name="Rosé Pine Moon", 
            css_path="/static/css/themes/rose_pine_moon.css", 
            is_dark=True,
            primary_color="#c4a7e7",
            background_color="#232136"
        ))
        self.register_theme(Theme(
            id="rose_pine_dawn", 
            name="Rosé Pine Dawn", 
            css_path="/static/css/themes/rose_pine_dawn.css", 
            is_dark=False,
            primary_color="#907aa9",
            background_color="#faf4ed"
        ))
        self.register_theme(Theme(
            id="vapor",  
            name="Vapor", 
            css_path="/static/css/themes/vapor.css", 
            is_dark=True,
            primary_color="#3584e4",
            background_color="#151c23"
        ))
        self.register_theme(Theme(
            id="green", 
            name="Green", 
            css_path="/static/css/themes/green.css", 
            is_dark=False,
            primary_color="#bbec96",
            background_color="#aae5a4"
        ))

theme_registry = ThemeRegistry()
