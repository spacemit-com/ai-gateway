from enum import Enum


class ModelStatus(str, Enum):
    AVAILABLE = "available"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    LOADING = "loading"
    LOADED = "loaded"
    ERROR = "error"
