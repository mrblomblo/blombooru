import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

@dataclass
class Language:
    """Represents a language configuration"""
    id: str           # e.g., "en", "de", "fr"
    name: str         # e.g., "English", "Deutsch"
    native_name: str  # e.g., "English", "Deutsch"
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "native_name": self.native_name
        }

class LanguageRegistry:
    """Central registry for managing languages"""
    
    def __init__(self):
        self._languages: Dict[str, Language] = {}
        self._register_default_languages()
    
    def register_language(self, language: Language) -> None:
        """Register a new language"""
        self._languages[language.id] = language
    
    def get_language(self, language_id: str) -> Optional[Language]:
        """Get a language by ID"""
        return self._languages.get(language_id)
    
    def get_all_languages(self) -> List[Language]:
        """Get all registered languages"""
        return list(self._languages.values())
    
    def language_exists(self, language_id: str) -> bool:
        """Check if a language exists"""
        return language_id in self._languages
    
    def _register_default_languages(self) -> None:
        """Register built-in languages"""
        self.register_language(Language(
            id="en",
            name="English",
            native_name="English"
        ))

        self.register_language(Language(
            id="sv",
            name="Swedish",
            native_name="Svenska"
        ))

        self.register_language(Language(
            id="ru",
            name="Russian",
            native_name="Русский"
        ))

        # Additional languages are registered here
        # Example (Note how "name" should be in English, while "native_name" should be in the native language):
        # self.register_language(Language(
        #     id="de",
        #     name="German",
        #     native_name="Deutsch"
        # ))

class TranslationHelper:
    """Helper for getting translated strings with fallback to English"""
    
    def __init__(self, locales_dir: Path):
        self._locales_dir = locales_dir
        self._translations: Dict[str, Dict] = {}
        self._fallback_lang = "en"
        self._current_lang = "en"
        self._load_all_translations()
    
    def _load_all_translations(self) -> None:
        """Load all translation files from locales directory"""
        if not self._locales_dir.exists():
            self._locales_dir.mkdir(parents=True, exist_ok=True)
            return
            
        for locale_file in self._locales_dir.glob("*.json"):
            lang_id = locale_file.stem
            try:
                with open(locale_file, 'r', encoding='utf-8') as f:
                    self._translations[lang_id] = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading translation file {locale_file}: {e}")
    
    def reload_translations(self) -> None:
        """Reload all translation files"""
        self._translations.clear()
        self._load_all_translations()
    
    def set_language(self, lang: str) -> None:
        """Set the current language"""
        self._current_lang = lang
    
    def get_current_language(self) -> str:
        """Get the current language"""
        return self._current_lang
    
    def get_translations(self, lang: str = None) -> Dict:
        """Get all translations for a language"""
        target_lang = lang or self._current_lang
        return self._translations.get(target_lang, self._translations.get(self._fallback_lang, {}))
    
    def _get_nested_value(self, data: Dict, key: str) -> Optional[str]:
        """Get a nested value using dot notation (e.g., 'nav.albums')"""
        keys = key.split('.')
        value = data
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return None
        
        return value if isinstance(value, str) else None
    
    def get(self, key: str, lang: str = None, **kwargs) -> str:
        """
        Get a translation string by key.
        
        Args:
            key: Dot-notation key (e.g., 'nav.albums')
            lang: Language code (optional, uses current language if not specified)
            **kwargs: Interpolation parameters (e.g., count=5 for '{count} items')
        
        Returns:
            Translated string, or the key itself if not found
        """
        target_lang = lang or self._current_lang
        
        # Try to get from target language
        translations = self._translations.get(target_lang, {})
        value = self._get_nested_value(translations, key)
        
        # Fallback to English if not found
        if value is None and target_lang != self._fallback_lang:
            fallback_translations = self._translations.get(self._fallback_lang, {})
            value = self._get_nested_value(fallback_translations, key)
        
        # If still not found, return the key itself
        if value is None:
            return key
        
        # Handle interpolation
        if kwargs:
            try:
                value = value.format(**kwargs)
            except KeyError:
                pass  # Return value without interpolation if params don't match
        
        return value

_locales_dir = Path(__file__).parent.parent.parent / "frontend" / "static" / "locales"
language_registry = LanguageRegistry()
translation_helper = TranslationHelper(_locales_dir)
