import enum

class RatingEnum(str, enum.Enum):
    safe = "safe"
    questionable = "questionable"
    explicit = "explicit"

class TagCategoryEnum(str, enum.Enum):
    general = "general"
    artist = "artist"
    character = "character"
    copyright = "copyright"
    meta = "meta"

class FileTypeEnum(str, enum.Enum):
    image = "image"
    video = "video"
    gif = "gif"
