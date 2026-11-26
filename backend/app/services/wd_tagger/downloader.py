import os
import threading
import time
from contextlib import contextmanager
from typing import Callable, Optional

from ...config import settings
from ...utils.logger import logger

class DownloadCancelledException(Exception):
    """Raised when a model download is cancelled by the client."""
    pass

def cleanup_orphaned_model_temp_files():
    """Remove any orphaned tmp* files in MODELS_DIR and custom model staging folders."""
    try:
        models_dir = settings.MODELS_DIR
        if models_dir.exists():
            for p in models_dir.glob("tmp*"):
                if p.is_file():
                    try:
                        p.unlink()
                        logger.info(f"Cleaned up orphaned model temp file: {p.name}")
                    except Exception as e:
                        logger.warning(f"Could not remove orphaned model temp file {p.name}: {e}")
    except Exception as e:
        logger.warning(f"Error cleaning up orphaned model temp files: {e}")

    try:
        from .custom_models import custom_model_manager
        custom_model_manager.cleanup_orphaned_staging()
    except Exception as e:
        logger.warning(f"Error cleaning up custom model staging files: {e}")

@contextmanager
def cancellable_hf_download(
    is_cancelled: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[dict], None]] = None,
    expected_total_bytes: Optional[int] = None
):
    """Context manager to intercept and cancel streaming Hugging Face model downloads, report progress, and clean up temporary files."""
    import huggingface_hub.file_download as fd
    orig_request_wrapper = fd._request_wrapper
    orig_http_get = fd.http_get

    active_temp_paths = set()
    session_start_time = time.time()
    last_report_time = 0.0
    cumulative_completed_bytes = 0
    file_index = 0

    def custom_http_get(*g_args, **g_kwargs):
        temp_file = g_kwargs.get("temp_file") or (g_args[1] if len(g_args) > 1 else None)
        temp_name = getattr(temp_file, "name", None)
        if temp_name:
            active_temp_paths.add(temp_name)
        try:
            return orig_http_get(*g_args, **g_kwargs)
        except Exception:
            if temp_file and not getattr(temp_file, "closed", True):
                try:
                    temp_file.close()
                except Exception:
                    pass
            if temp_name and os.path.exists(temp_name):
                try:
                    os.unlink(temp_name)
                    logger.info(f"Cleaned up cancelled model temp file: {temp_name}")
                except Exception as ex:
                    logger.warning(f"Failed to unlink temp file {temp_name}: {ex}")
            raise
        finally:
            if temp_name:
                active_temp_paths.discard(temp_name)

    def custom_request_wrapper(*r_args, **r_kwargs):
        nonlocal file_index
        file_index += 1
        
        r = orig_request_wrapper(*r_args, **r_kwargs)
        orig_iter = r.iter_content
        
        content_length = r.headers.get("Content-Length")
        file_total_bytes = int(content_length) if content_length and content_length.isdigit() else None
        
        url = r_kwargs.get("url") or (r_args[1] if len(r_args) > 1 else "")
        filename = url.split("/")[-1].split("?")[0] if url else f"file_{file_index}"
        
        file_downloaded_bytes = 0

        def custom_iter(*i_args, **i_kwargs):
            nonlocal file_downloaded_bytes, cumulative_completed_bytes, last_report_time
            # Use 512KB subchunks for responsive cancellation and smooth progress
            chunk_size = min(i_kwargs.get("chunk_size", 524288), 524288)
            for chunk in orig_iter(chunk_size=chunk_size):
                if is_cancelled and is_cancelled():
                    raise DownloadCancelledException("Model download cancelled by user")
                
                chunk_len = len(chunk)
                file_downloaded_bytes += chunk_len
                total_dl = cumulative_completed_bytes + file_downloaded_bytes
                now = time.time()
                
                if progress_callback and (now - last_report_time >= 0.25 or (file_total_bytes and file_downloaded_bytes >= file_total_bytes)):
                    last_report_time = now
                    elapsed = max(now - session_start_time, 0.001)
                    speed_bps = total_dl / elapsed
                    
                    effective_total = expected_total_bytes or (cumulative_completed_bytes + file_total_bytes if file_total_bytes else None)
                    if effective_total and effective_total > 0:
                        percent = min(round((total_dl / effective_total) * 100, 1), 99.9)
                    else:
                        percent = None
                        
                    progress_callback({
                        "type": "progress",
                        "filename": filename,
                        "file_index": file_index,
                        "file_downloaded_bytes": file_downloaded_bytes,
                        "file_total_bytes": file_total_bytes,
                        "downloaded_bytes": total_dl,
                        "total_bytes": effective_total,
                        "percent": percent,
                        "speed_bps": speed_bps,
                        "elapsed_seconds": round(elapsed, 1)
                    })
                yield chunk
            
            cumulative_completed_bytes += file_downloaded_bytes

        r.iter_content = custom_iter
        return r

    fd._request_wrapper = custom_request_wrapper
    fd.http_get = custom_http_get
    try:
        if is_cancelled and is_cancelled():
            raise DownloadCancelledException("Model download cancelled by user")
        yield
    except Exception:
        for p in list(active_temp_paths):
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except Exception:
                    pass
        cleanup_orphaned_model_temp_files()
        raise
    finally:
        fd._request_wrapper = orig_request_wrapper
        fd.http_get = orig_http_get

class DownloadTask:
    """Tracks an in-progress model download and broadcasts progress to subscribers."""
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.listeners = set()
        self.cancelled = False
        self.last_progress = None
        self.lock = threading.Lock()

    def add_listener(self, cb: Callable[[dict], None]):
        with self.lock:
            self.listeners.add(cb)
            if self.last_progress:
                try:
                    cb(self.last_progress)
                except Exception:
                    pass

    def remove_listener(self, cb: Callable[[dict], None]):
        with self.lock:
            self.listeners.discard(cb)

    def cancel(self):
        with self.lock:
            self.cancelled = True

    def has_listeners(self) -> bool:
        with self.lock:
            return len(self.listeners) > 0

    def notify(self, event: dict):
        with self.lock:
            if event.get("type") == "progress":
                self.last_progress = event
            listeners = list(self.listeners)
        for cb in listeners:
            try:
                cb(event)
            except Exception:
                pass

    def is_cancelled(self) -> bool:
        with self.lock:
            return self.cancelled
