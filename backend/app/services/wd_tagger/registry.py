import numpy as np
import pandas as pd

AVAILABLE_MODELS = {
    "pixai-tagger-v1.0": "noaione/pixai-tagger-v1.0-onnx",
    "wd-eva02-large-tagger-v3": "SmilingWolf/wd-eva02-large-tagger-v3",
    "wd-vit-large-tagger-v3": "SmilingWolf/wd-vit-large-tagger-v3",
    "wd-swinv2-tagger-v3": "SmilingWolf/wd-swinv2-tagger-v3",
    "wd-convnext-tagger-v3": "SmilingWolf/wd-convnext-tagger-v3",
    "wd-vit-tagger-v3": "SmilingWolf/wd-vit-tagger-v3",
}

LEGACY_MODEL_VARIANTS = {
    "pixai-tagger-v1.0": ["A1yCE/pixai-tagger-v1.0-onnx-fp16"],
}

MODEL_REPO_SPECS = {
    "noaione/pixai-tagger-v1.0-onnx": {
        "required_files": ["model.onnx", "model.onnx.data", "tags.json"],
        "model_file": "model.onnx",
        "label_file": "tags.json",
        "download_size_bytes": int(1980.0 * 1024 * 1024),
    },
    "A1yCE/pixai-tagger-v1.0-onnx-fp16": {
        "required_files": ["model.onnx", "tags.json"],
        "model_file": "model.onnx",
        "label_file": "tags.json",
        "download_size_bytes": int(935.4 * 1024 * 1024),
    },
}

# Speed ranking (relative, lower is faster)
MODEL_SPEED_RANKING = {
    "wd-vit-tagger-v3": 1,        # Fastest
    "wd-convnext-tagger-v3": 2,
    "wd-swinv2-tagger-v3": 3,
    "wd-eva02-large-tagger-v3": 4,
    "wd-vit-large-tagger-v3": 5,
    "pixai-tagger-v1.0": 6,       # Slowest
}

# Accuracy ranking (relative, lower is more accurate), based on benchmarks found online
MODEL_ACCURACY_RANKING = {
    "pixai-tagger-v1.0": 1,        # Most accurate
    "wd-eva02-large-tagger-v3": 2,
    "wd-vit-large-tagger-v3": 3,
    "wd-swinv2-tagger-v3": 4,
    "wd-convnext-tagger-v3": 5,
    "wd-vit-tagger-v3": 6,         # Least accurate
}

MODEL_FILENAME = "model.onnx"
LABEL_FILENAME = "selected_tags.csv"

# Measured per-model plateau caps on CPU (Ryzen 7 5700G)
OPTIMAL_BATCH_SIZES = {
    "pixai-tagger-v1.0": 1,
    "wd-convnext-tagger-v3": 1,
    "wd-eva02-large-tagger-v3": 2,
    "wd-vit-large-tagger-v3": 5,
    "wd-vit-tagger-v3": 10,
    "wd-swinv2-tagger-v3": 15,
}

# Total download sizes (model file + tags file) in bytes
MODEL_DOWNLOAD_SIZES_BYTES = {
    "wd-vit-tagger-v3": int(379.3 * 1024 * 1024),
    "wd-convnext-tagger-v3": int(375.3 * 1024 * 1024),
    "wd-swinv2-tagger-v3": int(445.3 * 1024 * 1024),
    "wd-eva02-large-tagger-v3": int(850.3 * 1024 * 1024),
    "wd-vit-large-tagger-v3": int(1200.3 * 1024 * 1024),
    "pixai-tagger-v1.0": int(1980.0 * 1024 * 1024),
}

def parse_label_data(label_path: str) -> dict:
    """Parse tag labels from CSV (WD models) or JSON (PixAI models)."""
    if label_path.endswith(".json"):
        import json
        with open(label_path, "r", encoding="utf-8") as f:
            tag_map = json.load(f)
        num_classes = tag_map.get("num_classes", 30877)
        all_names = [""] * num_classes
        general_indices = []
        character_indices = []
        copyright_indices = []
        artist_indices = []
        meta_indices = []
        rating_indices = []

        for cat in tag_map.get("categories", []):
            cname = cat["name"]
            offset = cat["offset"]
            count = cat["count"]
            tags = cat["tags"]
            for i, tag in enumerate(tags):
                all_names[offset + i] = tag
            indices = np.arange(offset, offset + count)
            if cname == "general":
                general_indices = indices
            elif cname == "character":
                character_indices = indices
            elif cname == "copyright":
                copyright_indices = indices
            elif cname == "style":
                artist_indices = indices
            elif cname == "meta":
                meta_indices = indices
            elif cname == "rating":
                rating_indices = indices

        return {
            'names': all_names,
            'general': np.array(general_indices, dtype=int),
            'character': np.array(character_indices, dtype=int),
            'copyright': np.array(copyright_indices, dtype=int),
            'artist': np.array(artist_indices, dtype=int),
            'meta': np.array(meta_indices, dtype=int),
            'rating': np.array(rating_indices, dtype=int),
            'is_pixai': True,
        }
    else:
        df = pd.read_csv(label_path)
        return {
            'names': df["name"].tolist(),
            'general': np.where(df["category"] == 0)[0],
            'character': np.where(df["category"] == 4)[0],
            'copyright': np.array([], dtype=int),
            'artist': np.array([], dtype=int),
            'meta': np.array([], dtype=int),
            'rating': np.where(df["category"] == 9)[0],
            'is_pixai': False,
        }
