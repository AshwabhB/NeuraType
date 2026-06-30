"""
NeuraType Backend (CHG000: Renamed from Voice Transcriber)

All non-UI logic: Whisper model management, audio recording, transcription,
hotkey handling, auto-paste, text processing, OpenAI integration, dictionary,
snippets, audio feedback, GPU management, and history file I/O.

No GUI imports — communicates with the frontend via callbacks.
"""

import threading
import tempfile
import os
import sys
import subprocess
import shutil
import time
import json
import re
import numpy as np
import sounddevice as sd
import soundfile as sf
import whisper
import torch
import pyperclip
import keyboard
from datetime import datetime

# ---------------------------------------------------------------------------
# INC003 Fix: Prevent window flash when subprocess (e.g. ffmpeg) spawns
# via VBS launcher. Monkey-patch subprocess.Popen so every child process
# is created with CREATE_NO_WINDOW unless the caller already set flags.
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    _orig_popen_init = subprocess.Popen.__init__

    def _patched_popen_init(self, *args, **kwargs):
        _CREATE_NO_WINDOW = 0x08000000
        kwargs.setdefault("creationflags", _CREATE_NO_WINDOW)
        _orig_popen_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _patched_popen_init

# Optional: OpenAI for grammar / format / command mode / tone (CHG004, CHG012, CHG013)
try:
    from openai import OpenAI as _OpenAIClient
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# ---------------------------------------------------------------------------
# Auto-detect CUDA GPU
# ---------------------------------------------------------------------------
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

if DEVICE == "cuda":
    _gpu_name = torch.cuda.get_device_name(0)
    _vram = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
    GPU_INFO = f"{_gpu_name} ({_vram:.1f} GB VRAM)"
else:
    GPU_INFO = "CPU mode"

# ---------------------------------------------------------------------------
# Model catalogue — fastest first
# ---------------------------------------------------------------------------
WHISPER_MODELS = {
    "tiny":   {"size": "~39 MB",   "desc": "Fastest, basic accuracy"},
    "base":   {"size": "~74 MB",   "desc": "Fast, decent accuracy"},
    "small":  {"size": "~244 MB",  "desc": "Moderate speed, good accuracy"},
    "medium": {"size": "~769 MB",  "desc": "Slower, very good accuracy"},
    "turbo":  {"size": "~1.5 GB",  "desc": "Fast for size, excellent accuracy"},
    "large":  {"size": "~1.5 GB",  "desc": "Slowest, best accuracy"},
}

DEFAULT_MODEL = "turbo"

# ---------------------------------------------------------------------------
# faster-whisper (CTranslate2) engine — optional, selected via settings["engine"]
# ---------------------------------------------------------------------------
# Same Whisper weights as openai-whisper, run through the CTranslate2 engine:
# ~4x faster, lower VRAM, releases GPU memory more cleanly. Accuracy is
# effectively identical at float16 compute. Falls back to openai-whisper if the
# package is unavailable.
try:
    from faster_whisper import WhisperModel as _FasterWhisperModel
    HAS_FASTER_WHISPER = True
except Exception:
    HAS_FASTER_WHISPER = False

# Map our short model names → faster-whisper / CTranslate2 model ids
_FW_NAME_MAP = {
    "tiny": "tiny", "base": "base", "small": "small",
    "medium": "medium", "large": "large-v3", "turbo": "large-v3-turbo",
}

DEFAULT_HOTKEY = "ctrl+win"
DEFAULT_CANCEL_HOTKEY = "ctrl+shift+space"
DEFAULT_PAUSE_HOTKEY = "ctrl+shift+p"

# ---------------------------------------------------------------------------
# Local LLM model catalogue — smallest first
# ---------------------------------------------------------------------------
LOCAL_LLM_MODELS = {
    "Qwen2.5-1.5B-Instruct": {
        "size": "~900 MB",
        "desc": "Smallest, fastest — good for basic edits",
        "url": (
            "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/"
            "qwen2.5-1.5b-instruct-q4_k_m.gguf"
        ),
        "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
    },
    "Qwen2.5-3B-Instruct": {
        "size": "~1.8 GB",
        "desc": "Best balance of quality and speed",
        "url": (
            "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/"
            "qwen2.5-3b-instruct-q4_k_m.gguf"
        ),
        "filename": "qwen2.5-3b-instruct-q4_k_m.gguf",
    },
    "Llama-3.2-3B-Instruct": {
        "size": "~1.8 GB",
        "desc": "Strong English, good reasoning",
        "url": (
            "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/"
            "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
        ),
        "filename": "Llama-3.2-3B-Instruct-Q4_K_M.gguf",
    },
    "Phi-3.5-mini": {
        "size": "~2.2 GB",
        "desc": "Largest, highest quality output",
        "url": (
            "https://huggingface.co/bartowski/Phi-3.5-mini-instruct-GGUF/resolve/main/"
            "Phi-3.5-mini-instruct-Q4_K_M.gguf"
        ),
        "filename": "Phi-3.5-mini-instruct-Q4_K_M.gguf",
    },
}

DEFAULT_LOCAL_LLM_MODEL = "Qwen2.5-1.5B-Instruct"

# ---------------------------------------------------------------------------
# Supported languages (CHG007) — value is Whisper language code
# ---------------------------------------------------------------------------
SUPPORTED_LANGUAGES = {
    "Auto-Detect": None,
    "English": "en", "Spanish": "es", "French": "fr", "German": "de",
    "Italian": "it", "Portuguese": "pt", "Russian": "ru", "Japanese": "ja",
    "Korean": "ko", "Chinese": "zh", "Arabic": "ar", "Hindi": "hi",
    "Turkish": "tr", "Dutch": "nl", "Polish": "pl", "Swedish": "sv",
    "Danish": "da", "Norwegian": "no", "Finnish": "fi", "Greek": "el",
    "Czech": "cs", "Romanian": "ro", "Hungarian": "hu", "Thai": "th",
    "Vietnamese": "vi", "Indonesian": "id", "Malay": "ms", "Filipino": "tl",
    "Ukrainian": "uk", "Hebrew": "he",
}

# ---------------------------------------------------------------------------
# Filler words for removal (CHG010)
# ---------------------------------------------------------------------------
FILLER_WORDS = [
    "um", "uh", "uh huh", "like", "you know", "so basically",
    "basically", "i mean", "literally", "right",
    "okay so", "well", "kind of", "sort of", "er", "ah",
]

# ---------------------------------------------------------------------------
# Backtrack / correction phrases (CHG011)
# ---------------------------------------------------------------------------
BACKTRACK_PHRASES = [
    "scratch that", "no wait", "delete that", "never mind",
    "no no", "let me rephrase", "correction", "i meant",
]

# ---------------------------------------------------------------------------
# Paths & settings
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Directory layout
# ---------------------------------------------------------------------------
# _BASE_DIR  = where the source code lives (read-only in installed mode)
# _DATA_DIR  = where writable user data goes (settings, models, history …)
#
# Dev mode:      _BASE_DIR == _DATA_DIR  (both F:\TTS\)
# Portable mode: _BASE_DIR → Program Files\NeuraType\app\
#                _DATA_DIR → %APPDATA%\NeuraType\
# ---------------------------------------------------------------------------
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_PORTABLE = os.environ.get("_NEURATYPE_PORTABLE") == "1"
if _PORTABLE:
    _DATA_DIR = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")), "NeuraType"
    )
    os.makedirs(_DATA_DIR, exist_ok=True)
    # Ensure ffmpeg shipped with the portable build is on PATH
    _ffmpeg_dir = os.path.join(os.path.dirname(_BASE_DIR), "ffmpeg")
    if os.path.isdir(_ffmpeg_dir):
        os.environ["PATH"] = _ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
else:
    _DATA_DIR = _BASE_DIR

SETTINGS_FILE = os.path.join(_DATA_DIR, "settings.json")
DICTIONARY_FILE = os.path.join(_DATA_DIR, "custom_dictionary.json")
SNIPPETS_FILE = os.path.join(_DATA_DIR, "snippets.json")
STATS_FILE = os.path.join(_DATA_DIR, "stats.json")
FIRST_BOOT_FILE = os.path.join(_DATA_DIR, "models", "firstBootSettings.json")

DEFAULT_SETTINGS = {
    "hotkey": DEFAULT_HOTKEY,
    "cancel_hotkey": DEFAULT_CANCEL_HOTKEY,
    "pause_hotkey": DEFAULT_PAUSE_HOTKEY,
    "hotkey_enabled": True,
    "auto_paste": True,
    "recording_indicator": True,
    "model": DEFAULT_MODEL,
    "mic_device_name": None,
    # Transcription engine: "faster-whisper" (CTranslate2, efficient) or "openai-whisper"
    "engine": "faster-whisper",
    # CTranslate2 compute type for faster-whisper. "float16" = no quality loss on
    # GPU; coerced to "int8" automatically on CPU. "int8_float16" trades a sliver
    # of accuracy for less VRAM.
    "fw_compute_type": "float16",
    # CHG002 — theme
    "theme": "dark",
    # CHG004 — OpenAI
    "openai_api_key": "",
    "correct_grammar": False,
    "auto_format": False,
    # CHG006 — hotkey mode
    "hotkey_mode": "toggle",
    # CHG007 — language
    "language": "English",
    # CHG010
    "filler_removal": False,
    # CHG011
    "backtrack_correction": False,
    # CHG012
    "command_mode": False,
    # CHG013
    "context_aware_tone": False,
    # CHG014
    "smart_insertion": False,
    # CHG015
    "audio_feedback": True,
    # CHG018
    "hands_free_mode": False,
    # CHG019
    "numbered_list_format": False,
    # CHG020
    "repaste_hotkey": "alt+shift+z",
    # CHG021
    "auto_detect_language": False,
    # CHG022
    "mic_sensitivity": 1.0,
    # CHG023
    "minimize_to_tray": True,
    # CHG024 — release GPU VRAM after this many idle minutes (0 = never).
    # On by default so backgrounded sessions stop hogging VRAM from games/apps.
    "gpu_idle_release_minutes": 3,
    # CHG025
    "adaptive_model": False,
    # CHG026
    "silence_auto_stop": False,
    "silence_timeout_seconds": 3,
    # CHG027
    "paste_delay_ms": 100,
    # CHG028
    "show_stats": True,
    # CHG030
    "auto_start": False,
    # CHG032
    "history_hotkey": "ctrl+shift+h",
    # Refresh hotkeys shortcut
    "refresh_hotkey": "ctrl+alt+z",
    # CHG7: local LLM
    "use_local_llm": False,
    "local_llm_model": DEFAULT_LOCAL_LLM_MODEL,
    # Model selection
    "selected_whisper_models": ["turbo"],
    "selected_llm_models": [],
    # Debug
    "debug_logging": False,
    # Speaker diarization via WhisperX
    "speaker_diarization": False,
    "hf_token": "",
    "num_speakers": 0,  # 0 = auto-detect
    "speaker_align": False,  # word-level alignment (slower but more precise)
}

# ---------------------------------------------------------------------------
# Debug logger — writes to neuratype_debug.log when enabled
# ---------------------------------------------------------------------------
DEBUG_LOG_FILE = os.path.join(_DATA_DIR, "neuratype_debug.log")


class DebugLogger:
    """Simple file logger controlled by the debug_logging setting."""

    def __init__(self):
        self._enabled = False
        self._file = None

    def set_enabled(self, enabled):
        if enabled and not self._enabled:
            try:
                self._file = open(DEBUG_LOG_FILE, "a", encoding="utf-8")
                self._log("=== NeuraType debug session started ===")
            except Exception as e:
                print(f"Failed to open debug log: {e}")
                self._file = None
        elif not enabled and self._enabled:
            self._log("=== NeuraType debug session ended ===")
            if self._file:
                try:
                    self._file.close()
                except Exception:
                    pass
                self._file = None
        self._enabled = enabled

    @property
    def enabled(self):
        return self._enabled

    def _log(self, msg):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"[{ts}] {msg}"
        if self._file:
            try:
                self._file.write(line + "\n")
                self._file.flush()
            except Exception:
                pass

    def log(self, msg):
        if self._enabled:
            self._log(msg)

    def close(self):
        if self._file:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None


debug_logger = DebugLogger()


def load_settings():
    """Load settings from JSON. Unknown keys are ignored; missing keys get defaults."""
    settings = dict(DEFAULT_SETTINGS)
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for key in DEFAULT_SETTINGS:
                if key in saved:
                    settings[key] = saved[key]
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return settings


def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except OSError as e:
        print(f"Failed to save settings: {e}")


def is_first_boot():
    """Check whether the first-boot model selection has been completed."""
    if not os.path.exists(FIRST_BOOT_FILE):
        return True
    try:
        with open(FIRST_BOOT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return not data.get("first_boot_done", False)
    except (json.JSONDecodeError, OSError):
        return True


def mark_first_boot_done():
    """Mark first boot as completed so the dialog won't show again."""
    os.makedirs(os.path.dirname(FIRST_BOOT_FILE), exist_ok=True)
    try:
        with open(FIRST_BOOT_FILE, "w", encoding="utf-8") as f:
            json.dump({"first_boot_done": True}, f, indent=2)
    except OSError as e:
        print(f"Failed to save first boot flag: {e}")


def get_downloaded_whisper_models_standalone():
    """Return Whisper model names on disk (no backend instance needed)."""
    model_dir = os.path.join(_DATA_DIR, "models")
    downloaded = []
    try:
        import whisper as _w
        for name in WHISPER_MODELS:
            try:
                url = _w._MODELS[name]
                fname = os.path.basename(url)
                if os.path.exists(os.path.join(model_dir, fname)):
                    downloaded.append(name)
            except (KeyError, AttributeError):
                pass
    except ImportError:
        pass
    return downloaded


def get_downloaded_llm_models_standalone():
    """Return LLM model names whose GGUF files exist on disk (no backend instance needed)."""
    model_dir = os.path.join(_DATA_DIR, "models")
    downloaded = []
    for name, info in LOCAL_LLM_MODELS.items():
        if os.path.exists(os.path.join(model_dir, info["filename"])):
            downloaded.append(name)
    return downloaded


# =========================================================================
# Utility classes
# =========================================================================

class DictionaryManager:
    """Custom dictionary for corrections and allowed words (CHG005, CHG017)."""

    def __init__(self, path=DICTIONARY_FILE):
        self._path = path
        self._data = {"corrections": {}, "allowed_words": []}
        self._load()

    def _load(self):
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    def _save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def add_word(self, word):
        word = word.strip()
        if word and word not in self._data["allowed_words"]:
            self._data["allowed_words"].append(word)
            self._save()

    def remove_word(self, word):
        word = word.strip()
        if word in self._data["allowed_words"]:
            self._data["allowed_words"].remove(word)
        self._data["corrections"].pop(word.lower(), None)
        self._save()

    def learn_correction(self, original, corrected):
        """Auto-learn a word correction from user edit (CHG017)."""
        original = original.strip().lower()
        corrected = corrected.strip()
        if original and corrected and original != corrected.lower():
            self._data["corrections"][original] = corrected
            self._save()

    def apply_corrections(self, text):
        for wrong, right in self._data.get("corrections", {}).items():
            text = re.sub(re.escape(wrong), right, text, flags=re.IGNORECASE)
        return text

    def get_allowed_words(self):
        return list(self._data.get("allowed_words", []))

    def get_corrections(self):
        return dict(self._data.get("corrections", {}))


class SnippetManager:
    """Snippet library with trigger phrases (CHG016)."""

    def __init__(self, path=SNIPPETS_FILE):
        self._path = path
        self._snippets = {}
        self._load()

    def _load(self):
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as f:
                    self._snippets = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    def _save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._snippets, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def add_snippet(self, trigger, replacement):
        self._snippets[trigger.strip().lower()] = replacement
        self._save()

    def remove_snippet(self, trigger):
        self._snippets.pop(trigger.strip().lower(), None)
        self._save()

    def get_all(self):
        return dict(self._snippets)

    def apply_snippets(self, text):
        for trigger, replacement in self._snippets.items():
            text = re.sub(re.escape(trigger), replacement, text, flags=re.IGNORECASE)
        return text


class TextProcessor:
    """Local text processing: filler removal, backtrack, numbered lists (CHG010/11/14/19)."""

    @staticmethod
    def remove_fillers(text):
        result = text
        for filler in sorted(FILLER_WORDS, key=len, reverse=True):
            result = re.sub(
                r'\b' + re.escape(filler) + r'\b[\s,]*',
                ' ', result, flags=re.IGNORECASE,
            )
        result = re.sub(r'\s{2,}', ' ', result)
        result = re.sub(r'\s+([,.])', r'\1', result)
        return result.strip()

    @staticmethod
    def apply_backtrack(text):
        result = text
        for phrase in BACKTRACK_PHRASES:
            result = re.sub(
                r'[^.!?]*\b' + re.escape(phrase) + r'\b[\s,]*',
                '', result, flags=re.IGNORECASE,
            )
        return result.strip()

    # Words preceding an ordinal that indicate adjective usage, not list items
    _NON_LIST_PREFIXES = frozenset({
        "the", "my", "a", "an", "his", "her", "their", "our", "its",
        "at", "for", "is", "was", "are", "were", "this", "that",
    })

    @staticmethod
    def format_numbered_list(text):
        ordinals = {
            "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
            "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
        }
        sequence = {
            "first": "1", "second": "2", "third": "3", "fourth": "4",
            "fifth": "5", "sixth": "6", "seventh": "7", "eighth": "8",
            "ninth": "9", "tenth": "10",
        }
        all_markers = {}
        all_markers.update(ordinals)
        all_markers.update(sequence)

        # Guard: require at least 2 distinct markers in the text
        found = 0
        for word in all_markers:
            if re.search(r'\b' + re.escape(word) + r'\b', text, re.IGNORECASE):
                found += 1
            if found >= 2:
                break
        if found < 2:
            return text

        # Replace markers, but skip when preceded by an article/possessive
        result = text
        for mapping in (ordinals, sequence):
            for word, num in mapping.items():
                pattern = re.compile(
                    r'\b' + re.escape(word) + r'\b[\s,]+', re.IGNORECASE,
                )

                def _replacer(m, _num=num):
                    start = m.start()
                    before = result[:start].rstrip()
                    prev_word = before.rsplit(None, 1)[-1].lower().rstrip('.,;:') if before.split() else ""
                    if prev_word in TextProcessor._NON_LIST_PREFIXES:
                        return m.group(0)  # keep original
                    return f'\n{_num}. '

                result = pattern.sub(_replacer, result)
        return result.strip()

    @staticmethod
    def adjust_for_insertion(text, preceding_char):
        """Adjust capitalization for mid-sentence insertion (CHG014)."""
        if not text or not preceding_char:
            return text
        if preceding_char.isalpha() or preceding_char in (',', ';', ':'):
            return text[0].lower() + text[1:] if text else text
        return text


class LocalLLMProcessor:
    """Local LLM alternative to OpenAI using llama-cpp-python (CHG7).

    Auto-downloads a GGUF model on first use, similar to how Whisper models
    are downloaded.  Supports multiple models via LOCAL_LLM_MODELS catalogue.
    Requires: pip install llama-cpp-python
    """

    def __init__(self, models_dir="", model_name=""):
        self._models_dir = models_dir
        self._model_name = model_name or DEFAULT_LOCAL_LLM_MODEL
        self._llm = None
        self._loading = False
        self._has_llama_cpp = None  # lazy check

    @property
    def current_model_name(self):
        return self._model_name

    def set_model(self, model_name):
        """Switch to a different model. Unloads current model if different."""
        if model_name == self._model_name:
            return
        if self._llm is not None:
            self.unload()
        self._model_name = model_name

    def _model_info(self):
        return LOCAL_LLM_MODELS.get(self._model_name, LOCAL_LLM_MODELS[DEFAULT_LOCAL_LLM_MODEL])

    @property
    def model_path(self):
        return os.path.join(self._models_dir, self._model_info()["filename"])

    @property
    def model_url(self):
        return self._model_info()["url"]

    @property
    def is_model_downloaded(self):
        return os.path.exists(self.model_path)

    @property
    def is_loaded(self):
        return self._llm is not None

    @property
    def is_loading(self):
        return self._loading

    def has_llama_cpp(self):
        if self._has_llama_cpp is None:
            try:
                import llama_cpp  # noqa: F401
                self._has_llama_cpp = True
            except ImportError:
                self._has_llama_cpp = False
        return self._has_llama_cpp

    def download_model(self, on_progress=None, on_done=None, on_error=None):
        """Download the selected GGUF model in a background thread."""
        if self.is_model_downloaded:
            if on_done:
                on_done()
            return

        def _dl():
            try:
                import urllib.request
                os.makedirs(self._models_dir, exist_ok=True)
                partial = self.model_path + ".part"
                req = urllib.request.Request(self.model_url)
                with urllib.request.urlopen(req) as resp:
                    total = int(resp.headers.get("Content-Length", 0))
                    downloaded = 0
                    chunk_size = 1024 * 256  # 256 KB
                    with open(partial, "wb") as f:
                        while True:
                            chunk = resp.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if on_progress and total > 0:
                                on_progress(downloaded, total)
                os.replace(partial, self.model_path)
                if on_done:
                    on_done()
            except Exception as e:
                # Clean up partial file
                partial = self.model_path + ".part"
                if os.path.exists(partial):
                    try:
                        os.remove(partial)
                    except OSError:
                        pass
                if on_error:
                    on_error(str(e))

        threading.Thread(target=_dl, daemon=True).start()

    def load_model(self, on_status=None):
        """Load the GGUF model into memory. Call from a background thread."""
        if self._llm is not None:
            return True
        if not self.is_model_downloaded:
            return False
        if not self.has_llama_cpp():
            return False
        self._loading = True
        try:
            from llama_cpp import Llama
            if on_status:
                on_status(f"Loading local LLM ({self._model_name})...", "#f59e0b")
            self._llm = Llama(
                model_path=self.model_path,
                n_ctx=2048,
                n_gpu_layers=-1 if DEVICE == "cuda" else 0,
                verbose=False,
            )
            self._loading = False
            return True
        except ImportError:
            self._loading = False
            return False
        except Exception as e:
            print(f"Failed to load local LLM: {e}")
            self._loading = False
            return False

    def _chat(self, system_prompt, user_text):
        if self._llm is None:
            if not self.load_model():
                return user_text
        try:
            output = self._llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                temperature=0.3,
                max_tokens=1024,
            )
            return output["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"Local LLM error: {e}")
            return user_text

    def process(self, text, correct_grammar=False, auto_format=False):
        if not correct_grammar and not auto_format:
            return text

        # Explicit, example-driven prompts for small local LLMs (1.5B-3.8B)
        system_parts = [
            "You are a text editor. You receive speech-to-text output and clean it up.",
            "Return ONLY the corrected text with no explanations or commentary.",
        ]

        if correct_grammar:
            system_parts.append(
                "Fix all grammar errors.\n"
                "Examples of fixes you MUST make:\n"
                "- 'I will be go' -> 'I will go'\n"
                "- 'She don't like' -> 'She doesn't like'\n"
                "- 'one biscuits' -> 'one biscuit'\n"
                "- 'two apple' -> 'two apples'\n"
                "- 'He have a car' -> 'He has a car'\n"
                "Fix spelling, punctuation, and capitalization. "
                "Do NOT add extra words or explanations."
            )

        if auto_format:
            system_parts.append(
                "If the text lists multiple items with numbers or ordinals "
                "(e.g. 'one apples two bananas three cookies'), "
                "format them as a numbered list with each item on its own line. "
                "Example input: 'I need to buy the following one bread two milk three eggs'\n"
                "Example output:\n"
                "I need to buy the following.\n"
                "1. Bread\n"
                "2. Milk\n"
                "3. Eggs\n"
                "Always capitalize the first letter of each list item. "
                "Add a period after the introductory sentence before the list."
            )

        prompt = "\n".join(system_parts)
        return self._chat(prompt, text)

    def adjust_tone(self, text, app_name):
        app = app_name.lower()
        if any(w in app for w in ("slack", "whatsapp", "telegram", "discord", "messenger")):
            tone = "casual and conversational, like a chat message"
        elif any(w in app for w in ("gmail", "outlook", "mail", "thunderbird")):
            tone = "professional and polished, like a business email"
        elif any(w in app for w in ("code", "visual studio", "vim", "sublime", "pycharm")):
            tone = "technical and concise, appropriate for code comments"
        elif any(w in app for w in ("word", "docs", "notion", "obsidian")):
            tone = "clear and well-structured, appropriate for a document"
        else:
            return text
        return self._chat(
            f"Adjust the tone to be {tone}. Keep meaning identical. Return ONLY the text.",
            text,
        )

    def execute_command(self, selected_text, voice_command):
        return self._chat(
            f"The user wants you to: {voice_command}\n\n"
            "Apply the transformation to the provided text. Return ONLY the result.",
            selected_text,
        )

    def unload(self):
        self._llm = None
        if DEVICE == "cuda":
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass


class OpenAIProcessor:
    """OpenAI-powered text transforms: grammar, format, tone, commands (CHG004/12/13)."""

    def __init__(self, api_key=""):
        self._api_key = api_key
        self._client = None
        self._last_error = ""

    def set_api_key(self, key):
        self._api_key = key
        self._client = None

    def _get_client(self):
        if not HAS_OPENAI or not self._api_key:
            return None
        if self._client is None:
            self._client = _OpenAIClient(api_key=self._api_key)
        return self._client

    def _chat(self, system_prompt, user_text):
        client = self._get_client()
        if not client:
            return user_text
        try:
            resp = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                temperature=0.3,
                max_tokens=2048,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            debug_logger.log(f"OpenAI API error: {e}")
            self._last_error = str(e)
            return user_text

    def process(self, text, correct_grammar=False, auto_format=False):
        parts = []
        if correct_grammar:
            parts.append("Correct any grammar, spelling, and punctuation errors.")
        if auto_format:
            parts.append(
                "If the text contains lists or points, format them with bullet points "
                "or numbered lists. Preserve the meaning exactly."
            )
        if not parts:
            return text
        prompt = " ".join(parts) + " Return ONLY the corrected text."
        return self._chat(prompt, text)

    def adjust_tone(self, text, app_name):
        app = app_name.lower()
        if any(w in app for w in ("slack", "whatsapp", "telegram", "discord", "messenger")):
            tone = "casual and conversational, like a chat message"
        elif any(w in app for w in ("gmail", "outlook", "mail", "thunderbird")):
            tone = "professional and polished, like a business email"
        elif any(w in app for w in ("code", "visual studio", "vim", "sublime", "pycharm")):
            tone = "technical and concise, appropriate for code comments"
        elif any(w in app for w in ("word", "docs", "notion", "obsidian")):
            tone = "clear and well-structured, appropriate for a document"
        else:
            return text
        return self._chat(
            f"Adjust the tone to be {tone}. Keep meaning identical. Return ONLY the text.",
            text,
        )

    def execute_command(self, selected_text, voice_command):
        return self._chat(
            f"The user wants you to: {voice_command}\n\n"
            "Apply the transformation to the provided text. Return ONLY the result.",
            selected_text,
        )


class AudioFeedback:
    """Short audio pings for record start / stop (CHG015)."""

    @staticmethod
    def play_start_sound():
        def _play():
            try:
                sr = 44100
                t = np.linspace(0, 0.08, int(sr * 0.08), endpoint=False)
                tone = np.sin(2 * np.pi * 880 * t) * 0.25
                fade = int(sr * 0.01)
                tone[:fade] *= np.linspace(0, 1, fade)
                tone[-fade:] *= np.linspace(1, 0, fade)
                sd.play(tone.astype(np.float32), samplerate=sr, blocking=True)
            except Exception:
                pass
        threading.Thread(target=_play, daemon=True).start()

    @staticmethod
    def play_stop_sound():
        def _play():
            try:
                sr = 44100
                t = np.linspace(0, 0.1, int(sr * 0.1), endpoint=False)
                half = len(t) // 2
                tone = np.empty_like(t)
                tone[:half] = np.sin(2 * np.pi * 660 * t[:half]) * 0.25
                tone[half:] = np.sin(2 * np.pi * 440 * t[half:]) * 0.25
                fade = int(sr * 0.01)
                tone[:fade] *= np.linspace(0, 1, fade)
                tone[-fade:] *= np.linspace(1, 0, fade)
                sd.play(tone.astype(np.float32), samplerate=sr, blocking=True)
            except Exception:
                pass
        threading.Thread(target=_play, daemon=True).start()


class StatsTracker:
    """Transcription statistics (CHG028)."""

    def __init__(self, path=STATS_FILE):
        self._path = path
        self._data = {"total_words": 0, "total_transcriptions": 0, "total_time": 0.0, "daily": {}}
        self._session = {"words": 0, "transcriptions": 0, "time": 0.0}
        self._load()

    def _load(self):
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    def _save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except OSError:
            pass

    def record(self, duration_seconds, word_count):
        self._data["total_words"] += word_count
        self._data["total_transcriptions"] += 1
        self._data["total_time"] += duration_seconds
        today = datetime.now().strftime("%Y-%m-%d")
        day = self._data.setdefault("daily", {}).setdefault(today, {"words": 0, "transcriptions": 0})
        day["words"] += word_count
        day["transcriptions"] += 1
        self._session["words"] += word_count
        self._session["transcriptions"] += 1
        self._session["time"] += duration_seconds
        self._save()

    def get_all_time(self):
        return {
            "words": self._data.get("total_words", 0),
            "transcriptions": self._data.get("total_transcriptions", 0),
            "time": self._data.get("total_time", 0.0),
        }

    def get_today(self):
        today = datetime.now().strftime("%Y-%m-%d")
        d = self._data.get("daily", {}).get(today, {})
        return {"words": d.get("words", 0), "transcriptions": d.get("transcriptions", 0)}

    def get_session(self):
        return dict(self._session)


# =========================================================================
# Main backend class
# =========================================================================

class TranscriberBackend:
    """Backend engine for NeuraType voice transcription."""

    def __init__(self, on_status, on_model_loaded, on_model_load_failed,
                 on_transcription_complete, on_transcription_error,
                 on_hotkey_triggered, on_cancel_hotkey_triggered,
                 on_predownload_progress,
                 on_hold_release=None,
                 on_silence_detected=None,
                 on_history_hotkey_triggered=None,
                 on_repaste_hotkey_triggered=None,
                 on_transcription_stats=None,
                 on_refresh_hotkey_triggered=None,
                 on_pause_hotkey_triggered=None):
        # Callbacks
        self.on_status = on_status
        self.on_model_loaded = on_model_loaded
        self.on_model_load_failed = on_model_load_failed
        self.on_transcription_complete = on_transcription_complete
        self.on_transcription_error = on_transcription_error
        self.on_hotkey_triggered = on_hotkey_triggered
        self.on_hold_release = on_hold_release or (lambda: None)
        self.on_cancel_hotkey_triggered = on_cancel_hotkey_triggered
        self.on_predownload_progress = on_predownload_progress
        self.on_silence_detected = on_silence_detected or (lambda: None)
        self.on_history_hotkey_triggered = on_history_hotkey_triggered or (lambda: None)
        self.on_repaste_hotkey_triggered = on_repaste_hotkey_triggered or (lambda: None)
        self.on_transcription_stats = on_transcription_stats or (lambda *a: None)
        self.on_refresh_hotkey_triggered = on_refresh_hotkey_triggered or (lambda: None)
        self.on_pause_hotkey_triggered = on_pause_hotkey_triggered or (lambda: None)

        # Settings
        self.settings = load_settings()

        # Recording state
        self.is_recording = False
        self.is_paused = False
        self.audio_data = []
        self.sample_rate = 16000
        self.selected_device_index = None
        self.audio_level = 0.0
        self.stream = None
        self._silence_start = None
        self._speech_detected = False
        self._last_audio = None           # CHG009: stored for retry
        self._command_context = None       # CHG012: selected text for command mode
        self._last_transcription = ""      # CHG020: re-paste
        self._playback_start_time = None   # seek bar: wall time when playback began
        self._playback_start_frame = 0     # seek bar: frame offset playback started at

        # Hotkey state
        self.current_hotkey = self.settings["hotkey"]
        self.current_cancel_hotkey = self.settings["cancel_hotkey"]
        self.current_pause_hotkey = self.settings.get("pause_hotkey", DEFAULT_PAUSE_HOTKEY)
        self.hotkey_enabled = self.settings["hotkey_enabled"]
        self.auto_paste = self.settings["auto_paste"]

        # Whisper model state
        self.whisper_model = None
        self.model_loading = True
        self.current_model_name = self.settings["model"]
        self._fast_model = None            # CHG025
        self._gpu_released = False         # CHG024
        self._last_activity = time.time()  # CHG024
        self.engine = self._resolve_engine()  # active transcription engine

        # Directories — use _DATA_DIR so models/history go to writable location
        self.model_dir = os.path.join(_DATA_DIR, "models")
        os.makedirs(self.model_dir, exist_ok=True)
        self._history_dir = os.path.join(_DATA_DIR, "history")
        os.makedirs(self._history_dir, exist_ok=True)
        self._audio_cache_dir = os.path.join(_DATA_DIR, "audio_cache")
        os.makedirs(self._audio_cache_dir, exist_ok=True)
        self._last_audio_path = os.path.join(self._audio_cache_dir, "last_recording.wav")
        # Restore _last_audio from disk so retry/playback survives a crash or restart
        if os.path.exists(self._last_audio_path):
            try:
                data, sr = sf.read(self._last_audio_path)
                if sr == self.sample_rate and data.size > 0:
                    self._last_audio = data.reshape(-1, 1) if data.ndim == 1 else data
            except Exception:
                pass

        # Sub-systems
        self.dictionary = DictionaryManager()
        self.snippets = SnippetManager()
        self.openai_processor = OpenAIProcessor(self.settings.get("openai_api_key", ""))
        self.local_llm = LocalLLMProcessor(
            models_dir=self.model_dir,
            model_name=self.settings.get("local_llm_model", DEFAULT_LOCAL_LLM_MODEL),
        )
        self.stats = StatsTracker()
        self.audio_feedback = AudioFeedback()

        # CHG024 / INC002: GPU idle release timer
        self._start_gpu_idle_timer()

        # Activate debug logger from saved settings
        debug_logger.set_enabled(self.settings.get("debug_logging", False))

    # ------------------------------------------------------------------
    # Model management
    # ------------------------------------------------------------------
    def _resolve_engine(self):
        """Resolve the active engine, falling back to openai-whisper if
        faster-whisper isn't installed."""
        eng = self.settings.get("engine", "faster-whisper")
        if eng == "faster-whisper" and not HAS_FASTER_WHISPER:
            debug_logger.log("faster-whisper unavailable; falling back to openai-whisper")
            eng = "openai-whisper"
        return eng

    def _load_engine_model(self, model_name):
        """Load a Whisper model object for the active engine.

        faster-whisper → a CTranslate2 WhisperModel (same weights, faster engine).
        openai-whisper → the reference PyTorch model. Both expose .transcribe().
        """
        if self.engine == "faster-whisper":
            ct = self.settings.get("fw_compute_type", "float16")
            if DEVICE != "cuda" and ct in ("float16", "int8_float16"):
                ct = "int8"  # float16 isn't supported on CPU
            fw_name = _FW_NAME_MAP.get(model_name, model_name)
            debug_logger.log(f"loading faster-whisper '{fw_name}' compute={ct} on {DEVICE}")
            return _FasterWhisperModel(
                fw_name, device=DEVICE, compute_type=ct,
                download_root=self.model_dir,
            )
        return whisper.load_model(model_name, device=DEVICE, download_root=self.model_dir)

    def load_model(self, model_name):
        self.model_loading = True
        self.whisper_model = None
        self.current_model_name = model_name
        self._gpu_released = False
        self.engine = self._resolve_engine()
        info = WHISPER_MODELS[model_name]
        self.on_status(f"Loading model '{model_name}' ({info['size']})...", "#f59e0b")
        debug_logger.log(f"load_model '{model_name}' on {DEVICE} via {self.engine}")

        def _load():
            try:
                t0 = time.time()
                model = self._load_engine_model(model_name)
                self.whisper_model = model
                self.model_loading = False
                self._last_activity = time.time()
                debug_logger.log(f"load_model '{model_name}' OK in {time.time()-t0:.1f}s")
                self.on_model_loaded(model_name)
            except Exception as e:
                self.model_loading = False
                debug_logger.log(f"load_model FAILED: {e}")
                self.on_model_load_failed(str(e))

        threading.Thread(target=_load, daemon=True).start()

    def unload_model(self):
        """Free GPU VRAM by unloading Whisper + local LLM models (CHG024 / CHG7)."""
        if self.whisper_model is not None:
            del self.whisper_model
            self.whisper_model = None
        if self._fast_model is not None:
            del self._fast_model
            self._fast_model = None
        # CHG7: also release local LLM
        if self.local_llm.is_loaded:
            self.local_llm.unload()
        if DEVICE == "cuda":
            torch.cuda.empty_cache()
        self._gpu_released = True
        self.on_status("GPU released — model reloads on next recording", "#f59e0b")

    def reload_model(self):
        if self._gpu_released:
            self._gpu_released = False
            self.load_model(self.current_model_name)
            # CHG7: also reload local LLM if enabled
            if self.settings.get("use_local_llm", False) and self.local_llm.is_model_downloaded:
                threading.Thread(
                    target=self.local_llm.load_model,
                    kwargs={"on_status": self.on_status},
                    daemon=True,
                ).start()

    # ------------------------------------------------------------------
    # Model inventory and deletion
    # ------------------------------------------------------------------
    def _fw_cached_dirs(self):
        """CTranslate2 model cache folders under model_dir (HF snapshot format)."""
        try:
            return [
                d for d in os.listdir(self.model_dir)
                if os.path.isdir(os.path.join(self.model_dir, d))
                and "faster-whisper" in d.lower()
            ]
        except OSError:
            return []

    def _fw_dir_matches(self, name, dirname):
        """Whether a CT2 cache folder corresponds to our short model name."""
        dl = dirname.lower()
        if name == "large":          # large → large-v3, but NOT large-v3-turbo
            return "large-v3" in dl and "turbo" not in dl
        if name == "turbo":
            return "turbo" in dl
        return _FW_NAME_MAP.get(name, name).lower() in dl

    def get_downloaded_whisper_models(self):
        """Return list of Whisper model names that exist on disk."""
        if self._resolve_engine() == "faster-whisper":
            dirs = self._fw_cached_dirs()
            return [n for n in WHISPER_MODELS
                    if any(self._fw_dir_matches(n, d) for d in dirs)]
        downloaded = []
        for name in WHISPER_MODELS:
            try:
                url = whisper._MODELS[name]
                fname = os.path.basename(url)
                if os.path.exists(os.path.join(self.model_dir, fname)):
                    downloaded.append(name)
            except (KeyError, AttributeError):
                pass
        return downloaded

    def get_downloaded_llm_models(self):
        """Return list of LLM model names whose GGUF files exist on disk."""
        downloaded = []
        for name, info in LOCAL_LLM_MODELS.items():
            if os.path.exists(os.path.join(self.model_dir, info["filename"])):
                downloaded.append(name)
        return downloaded

    def delete_whisper_model(self, name):
        """Delete a Whisper model file from disk. Refuses to delete the active model."""
        if name == self.current_model_name:
            print(f"Cannot delete active Whisper model '{name}'")
            return False
        if self._resolve_engine() == "faster-whisper":
            removed = False
            for d in self._fw_cached_dirs():
                if self._fw_dir_matches(name, d):
                    try:
                        shutil.rmtree(os.path.join(self.model_dir, d))
                        removed = True
                    except OSError as e:
                        print(f"Failed to delete faster-whisper model '{name}': {e}")
            return removed
        try:
            url = whisper._MODELS[name]
            fname = os.path.basename(url)
            path = os.path.join(self.model_dir, fname)
            if os.path.exists(path):
                os.remove(path)
                return True
        except (KeyError, AttributeError, OSError) as e:
            print(f"Failed to delete Whisper model '{name}': {e}")
        return False

    def delete_llm_model(self, name):
        """Delete an LLM GGUF model file from disk and unload if active."""
        info = LOCAL_LLM_MODELS.get(name)
        if not info:
            return False
        # Unload if this is the currently loaded model
        if self.local_llm.current_model_name == name and self.local_llm.is_loaded:
            self.local_llm.unload()
        try:
            path = os.path.join(self.model_dir, info["filename"])
            if os.path.exists(path):
                os.remove(path)
                return True
        except OSError as e:
            print(f"Failed to delete LLM model '{name}': {e}")
        return False

    def _ensure_model_loaded(self):
        """Synchronous reload if model was idle-released (CHG024)."""
        if not self._gpu_released and self.whisper_model is not None:
            return True
        self._gpu_released = False
        self.engine = self._resolve_engine()
        self.on_status(f"Reloading '{self.current_model_name}'...", "#f59e0b")
        try:
            self.whisper_model = self._load_engine_model(self.current_model_name)
            self._last_activity = time.time()
            return True
        except Exception as e:
            self.on_status(f"Reload failed: {e}", "#ef4444")
            return False

    def predownload_all_models(self):
        """Pre-download only Whisper models in the user's selected list."""
        selected = self.settings.get("selected_whisper_models", list(WHISPER_MODELS.keys()))

        def _download_selected():
            while self.model_loading:
                time.sleep(0.5)
            remaining = [m for m in selected if m != self.current_model_name and m in WHISPER_MODELS]
            use_fw = self._resolve_engine() == "faster-whisper"
            for i, name in enumerate(remaining, 1):
                self.on_predownload_progress(name, i, len(remaining))
                try:
                    if use_fw:
                        # Instantiate to trigger the CTranslate2 download, then release
                        _m = self._load_engine_model(name)
                        del _m
                        if DEVICE == "cuda":
                            torch.cuda.empty_cache()
                    else:
                        whisper._download(whisper._MODELS[name], self.model_dir, False)
                except Exception:
                    pass
            self.on_status(f"Selected models cached — '{self.current_model_name}' active", "#10b981")

        threading.Thread(target=_download_selected, daemon=True).start()

    # ------------------------------------------------------------------
    # GPU idle timer (CHG024 / INC002 fix)
    # ------------------------------------------------------------------
    def _start_gpu_idle_timer(self):
        def _check():
            while True:
                time.sleep(30)
                mins = self.settings.get("gpu_idle_release_minutes", 0)
                if mins <= 0 or self._gpu_released or self.is_recording or self.model_loading:
                    continue
                if (time.time() - self._last_activity) / 60 >= mins and self.whisper_model is not None:
                    self.unload_model()

        threading.Thread(target=_check, daemon=True).start()

    # ------------------------------------------------------------------
    # Microphone devices
    # ------------------------------------------------------------------
    @staticmethod
    def get_input_devices():
        devices = sd.query_devices()
        inputs = []
        for i, d in enumerate(devices):
            if d["max_input_channels"] > 0:
                inputs.append((i, f"{d['name']}  ({int(d['default_samplerate'])} Hz)"))
        return inputs

    @staticmethod
    def get_default_input_device_name():
        try:
            dev = sd.query_devices(kind="input")
            return dev["name"] if dev else ""
        except Exception:
            return ""

    def check_mic(self, duration=2.0, on_level=None):
        """Record a short sample and report mic levels (CHG008)."""
        levels = []
        gain = self.settings.get("mic_sensitivity", 1.0)

        def _cb(indata, frames, time_info, status):
            rms = float(np.sqrt(np.mean((indata * gain) ** 2)))
            levels.append(rms)
            if on_level:
                on_level(min(1.0, rms * 10))

        try:
            stream = sd.InputStream(
                device=self.selected_device_index, channels=1,
                samplerate=self.sample_rate, callback=_cb,
            )
            stream.start()
            time.sleep(duration)
            stream.stop()
            stream.close()
        except Exception as e:
            return {"error": str(e)}
        if levels:
            return {"average": float(np.mean(levels)), "peak": float(np.max(levels))}
        return {"error": "No audio captured"}

    # ------------------------------------------------------------------
    # Hotkey management
    # ------------------------------------------------------------------
    def register_hotkey(self):
        try:
            keyboard.add_hotkey(self.current_hotkey, self._hotkey_triggered_internal)
            return True, f"Hotkey active: {self.current_hotkey}", "#10b981"
        except Exception as e:
            return False, f"Hotkey error: {e}", "#ef4444"

    def register_cancel_hotkey(self):
        try:
            keyboard.add_hotkey(self.current_cancel_hotkey, self._cancel_hotkey_triggered_internal)
            return True, f"Cancel hotkey active: {self.current_cancel_hotkey}", "#10b981"
        except Exception as e:
            return False, f"Cancel hotkey error: {e}", "#ef4444"

    def register_pause_hotkey(self):
        try:
            keyboard.add_hotkey(self.current_pause_hotkey, self._pause_hotkey_triggered_internal)
            return True, f"Pause hotkey active: {self.current_pause_hotkey}", "#10b981"
        except Exception as e:
            return False, f"Pause hotkey error: {e}", "#ef4444"

    def register_repaste_hotkey(self):
        """Register re-paste last transcript hotkey (CHG020)."""
        hk = self.settings.get("repaste_hotkey", "alt+shift+z")
        try:
            keyboard.add_hotkey(hk, self._repaste_triggered)
            return True
        except Exception:
            return False

    def register_history_hotkey(self):
        """Register history window hotkey (CHG032)."""
        hk = self.settings.get("history_hotkey", "ctrl+shift+h")
        try:
            keyboard.add_hotkey(hk, lambda: self.on_history_hotkey_triggered())
            return True
        except Exception:
            return False

    def unregister_hotkey(self):
        try:
            keyboard.remove_hotkey(self.current_hotkey)
        except Exception:
            pass

    def unregister_cancel_hotkey(self):
        try:
            keyboard.remove_hotkey(self.current_cancel_hotkey)
        except Exception:
            pass

    def unregister_pause_hotkey(self):
        try:
            keyboard.remove_hotkey(self.current_pause_hotkey)
        except Exception:
            pass

    def unregister_repaste_hotkey(self):
        try:
            keyboard.remove_hotkey(self.settings.get("repaste_hotkey", "alt+shift+z"))
        except Exception:
            pass

    def unregister_history_hotkey(self):
        try:
            keyboard.remove_hotkey(self.settings.get("history_hotkey", "ctrl+shift+h"))
        except Exception:
            pass

    def register_refresh_hotkey(self):
        """Register hotkey that re-registers all hotkeys (useful after sleep/wake)."""
        hk = self.settings.get("refresh_hotkey", "ctrl+alt+z")
        if not hk:
            return False
        try:
            keyboard.add_hotkey(hk, lambda: self.on_refresh_hotkey_triggered())
            debug_logger.log(f"register_refresh_hotkey OK: {hk!r}")
            return True
        except Exception as e:
            debug_logger.log(f"register_refresh_hotkey FAILED {hk!r}: {e}")
            return False

    def unregister_refresh_hotkey(self):
        try:
            keyboard.remove_hotkey(self.settings.get("refresh_hotkey", "ctrl+alt+z"))
        except Exception:
            pass

    def change_hotkey(self, new_hotkey):
        if new_hotkey.strip().lower() == self.current_cancel_hotkey.strip().lower():
            return False, "Start/Stop hotkey cannot be the same as Cancel hotkey."
        self.unregister_hotkey()
        try:
            keyboard.add_hotkey(new_hotkey, self._hotkey_triggered_internal)
            self.current_hotkey = new_hotkey
            return True, None
        except Exception as e:
            try:
                keyboard.add_hotkey(self.current_hotkey, self._hotkey_triggered_internal)
            except Exception:
                pass
            return False, str(e)

    def change_cancel_hotkey(self, new_hotkey):
        if new_hotkey.strip().lower() == self.current_hotkey.strip().lower():
            return False, "Cancel hotkey cannot be the same as Start/Stop hotkey."
        self.unregister_cancel_hotkey()
        try:
            keyboard.add_hotkey(new_hotkey, self._cancel_hotkey_triggered_internal)
            self.current_cancel_hotkey = new_hotkey
            return True, None
        except Exception as e:
            try:
                keyboard.add_hotkey(self.current_cancel_hotkey, self._cancel_hotkey_triggered_internal)
            except Exception:
                pass
            return False, str(e)

    def change_pause_hotkey(self, new_hotkey):
        nh = new_hotkey.strip().lower()
        if nh == self.current_hotkey.strip().lower():
            return False, "Pause hotkey cannot be the same as Start/Stop hotkey."
        if nh == self.current_cancel_hotkey.strip().lower():
            return False, "Pause hotkey cannot be the same as Cancel hotkey."
        self.unregister_pause_hotkey()
        try:
            keyboard.add_hotkey(new_hotkey, self._pause_hotkey_triggered_internal)
            self.current_pause_hotkey = new_hotkey
            return True, None
        except Exception as e:
            try:
                keyboard.add_hotkey(self.current_pause_hotkey, self._pause_hotkey_triggered_internal)
            except Exception:
                pass
            return False, str(e)

    def _hotkey_triggered_internal(self):
        debug_logger.log(f"_hotkey_triggered_internal: enabled={self.hotkey_enabled}, "
                         f"model_loading={self.model_loading}, recording={self.is_recording}")
        if not self.hotkey_enabled or self.model_loading:
            return
        # CHG006: hold mode — start on press, stop on release
        if self.settings.get("hotkey_mode") == "hold":
            if self.is_recording:
                return  # Ignore key-repeat events while recording in hold mode
            self.on_hotkey_triggered()
            threading.Thread(target=self._hold_mode_monitor, daemon=True).start()
        else:
            self.on_hotkey_triggered()

    def _hold_mode_monitor(self):
        """Poll for hotkey release in hold mode (CHG006)."""
        time.sleep(0.35)  # Let keys settle after initial press
        while self.is_recording:
            try:
                if not keyboard.is_pressed(self.current_hotkey):
                    # Double-check after a short delay to avoid false releases
                    time.sleep(0.1)
                    if not keyboard.is_pressed(self.current_hotkey):
                        # CHG6-fix: use dedicated hold_release callback so the
                        # UI directly stops recording instead of toggling.
                        self.on_hold_release()
                        break
            except Exception:
                break
            time.sleep(0.05)

    def _cancel_hotkey_triggered_internal(self):
        if not self.hotkey_enabled or not self.is_recording:
            return
        self.on_cancel_hotkey_triggered()

    def _pause_hotkey_triggered_internal(self):
        if not self.hotkey_enabled or not self.is_recording:
            return
        self.on_pause_hotkey_triggered()

    def _repaste_triggered(self):
        """Re-paste the last transcription (CHG020)."""
        if self._last_transcription:
            self.on_repaste_hotkey_triggered()

    def set_hotkey_enabled(self, enabled):
        self.hotkey_enabled = enabled
        if enabled:
            return f"Hotkey active: {self.current_hotkey}", "#10b981"
        return "Hotkey disabled", "#94a3b8"

    def set_auto_paste(self, enabled):
        self.auto_paste = enabled

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------
    def start_recording(self):
        self.is_recording = True
        self.is_paused = False
        self.audio_data = []
        self._silence_start = None
        self._speech_detected = False

        # CHG015: audio feedback
        if self.settings.get("audio_feedback", True):
            self.audio_feedback.play_start_sound()

        # CHG012: capture selected text for command mode
        if self.settings.get("command_mode", False) and self.settings.get("openai_api_key"):
            try:
                original_clip = pyperclip.paste()
                keyboard.send('ctrl+c')
                time.sleep(0.15)
                selected = pyperclip.paste()
                if selected and selected != original_clip and selected.strip():
                    self._command_context = selected.strip()
                else:
                    self._command_context = None
                if original_clip:
                    pyperclip.copy(original_clip)
            except Exception:
                self._command_context = None
        else:
            self._command_context = None

        gain = self.settings.get("mic_sensitivity", 1.0)
        silence_threshold = 0.005
        silence_timeout = self.settings.get("silence_timeout_seconds", 3)
        do_silence_stop = (
            self.settings.get("silence_auto_stop", False)
            and not self.settings.get("hands_free_mode", False)
        )

        def audio_callback(indata, frames, time_info, status):
            if status:
                print(f"Audio status: {status}")
            if self.is_paused:
                self.audio_level = 0.0
                return
            data = indata.copy()
            if gain != 1.0:
                data = data * gain
            self.audio_data.append(data)
            rms = np.sqrt(np.mean(data ** 2))
            self.audio_level = min(1.0, rms * 10)

            # CHG026: silence detection
            if do_silence_stop:
                if rms >= silence_threshold:
                    self._speech_detected = True
                    self._silence_start = None
                elif self._speech_detected:
                    if self._silence_start is None:
                        self._silence_start = time.time()
                    elif time.time() - self._silence_start >= silence_timeout:
                        self.on_silence_detected()

        self.stream = sd.InputStream(
            device=self.selected_device_index, channels=1,
            samplerate=self.sample_rate, callback=audio_callback,
        )
        self.stream.start()

    def pause_recording(self):
        """Pause capturing audio while keeping the stream and buffered audio alive."""
        if self.is_recording and not self.is_paused:
            self.is_paused = True
            self.audio_level = 0.0
            return True
        return False

    def resume_recording(self):
        """Resume capturing audio after a pause."""
        if self.is_recording and self.is_paused:
            self.is_paused = False
            self._silence_start = None
            return True
        return False

    def toggle_pause(self):
        """Toggle the paused state. Returns the new is_paused value."""
        if self.is_paused:
            self.resume_recording()
        else:
            self.pause_recording()
        return self.is_paused

    def cancel_recording(self):
        self.is_recording = False
        self.is_paused = False
        self.audio_level = 0.0
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass
        self.audio_data = []

    def stop_recording(self):
        """Stop recording and start transcription. Returns False if no usable audio."""
        debug_logger.log("stop_recording called")
        self.is_recording = False
        self.is_paused = False
        self.audio_level = 0.0

        # CHG015: stop sound
        if self.settings.get("audio_feedback", True):
            self.audio_feedback.play_stop_sound()

        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass

        if not self.audio_data:
            return False

        audio_array = np.concatenate(self.audio_data, axis=0)
        if len(audio_array) < int(self.sample_rate * 0.5):
            return False

        self._last_audio = audio_array.copy()  # CHG009: store for retry
        # Persist to disk so retry/playback survives crashes and restarts
        try:
            sf.write(self._last_audio_path, audio_array, self.sample_rate)
        except Exception as e:
            debug_logger.log(f"Failed to save last audio: {e}")
        threading.Thread(target=self._transcribe, args=(audio_array,), daemon=True).start()
        return True

    def retry_transcription(self):
        """Retry the last transcription (CHG009)."""
        if self._last_audio is not None and len(self._last_audio) > 0:
            threading.Thread(target=self._transcribe, args=(self._last_audio,), daemon=True).start()
            return True
        return False

    def has_last_audio(self):
        """Whether audio is available for playback or retry."""
        return self._last_audio is not None and len(self._last_audio) > 0

    def play_last_audio(self, start_frame=0):
        """Play the last recorded audio asynchronously. Returns True if playback started."""
        if not self.has_last_audio():
            return False
        start_frame = max(0, min(start_frame, len(self._last_audio) - 1))
        self._playback_start_time = time.time()
        self._playback_start_frame = start_frame
        audio = self._last_audio[start_frame:] if start_frame > 0 else self._last_audio
        def _play():
            try:
                sd.stop()
                sd.play(audio, samplerate=self.sample_rate, blocking=False)
            except Exception as e:
                debug_logger.log(f"Playback failed: {e}")
        threading.Thread(target=_play, daemon=True).start()
        return True

    def get_playback_frame(self):
        """Estimate current playback frame from elapsed wall time."""
        if self._playback_start_time is None:
            return 0
        elapsed = int((time.time() - self._playback_start_time) * self.sample_rate)
        return self._playback_start_frame + elapsed

    def stop_playback(self):
        try:
            sd.stop()
        except Exception:
            pass
        self._playback_start_time = None

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Shared Whisper helpers (used by mic transcription & file transcription)
    # ------------------------------------------------------------------
    def _build_whisper_kwargs(self):
        """Build the kwargs dict for whisper.transcribe()."""
        # fp16 is an openai-whisper arg; faster-whisper sets precision via
        # compute_type at load time and rejects unknown kwargs.
        kwargs = {} if self.engine == "faster-whisper" else {"fp16": (DEVICE == "cuda")}
        # Encourage proper punctuation
        kwargs["initial_prompt"] = (
            "Hello, welcome. This is a properly punctuated transcript "
            "with correct capitalization, periods, commas, and question marks."
        )
        # condition_on_previous_text=False prevents hallucination cascades in long
        # recordings — each segment is decoded independently, stopping garbage text
        # from feeding forward into subsequent segments.
        kwargs["condition_on_previous_text"] = False
        # CHG007 / CHG021 / CHG8-fix: language
        lang = self.settings.get("language", "English")
        legacy_auto = self.settings.get("auto_detect_language", False)
        if lang == "Auto-Detect" or legacy_auto:
            pass  # let Whisper auto-detect
        else:
            code = SUPPORTED_LANGUAGES.get(lang)
            if code:
                kwargs["language"] = code
        return kwargs

    def _run_faster_whisper(self, model, audio, kwargs):
        """Run faster-whisper transcription. `audio` may be a path or a 16kHz
        mono float32 numpy array. Returns (text, elapsed)."""
        t_start = time.time()
        fw_kwargs = {
            "initial_prompt": kwargs.get("initial_prompt"),
            "condition_on_previous_text": kwargs.get("condition_on_previous_text", False),
        }
        if "language" in kwargs:
            fw_kwargs["language"] = kwargs["language"]
        debug_logger.log("_run_faster_whisper starting transcribe ...")
        segments, _info = model.transcribe(audio, **fw_kwargs)
        text = "".join(seg.text for seg in segments).strip()  # generator → realize here
        elapsed = time.time() - t_start
        debug_logger.log(f"_run_faster_whisper done in {elapsed:.2f}s, text={text[:80]!r}")
        return text, elapsed

    def _run_whisper(self, model, audio_path, kwargs):
        """Run whisper.transcribe with INC001 retry logic. Returns (text, elapsed)."""
        if self.engine == "faster-whisper":
            return self._run_faster_whisper(model, audio_path, kwargs)
        _RETRYABLE = ("key.size", "reshape tensor", "cannot reshape",
                      "expected", "dimension", "size mismatch")
        _CUDA_FATAL = ("cuda error", "cuda", "cudnn", "cublas",
                       "device-side assert", "out of memory")
        t_start = time.time()
        debug_logger.log("_run_whisper starting whisper.transcribe ...")
        for attempt in range(4):
            try:
                if attempt == 1:
                    kwargs["condition_on_previous_text"] = False
                elif attempt == 2:
                    kwargs["fp16"] = False
                    kwargs["condition_on_previous_text"] = False
                elif attempt == 3:
                    kwargs["fp16"] = False
                    kwargs["condition_on_previous_text"] = False
                    if "language" not in kwargs:
                        kwargs["language"] = "en"
                result = model.transcribe(audio_path, **kwargs)
                text = result["text"].strip()
                elapsed = time.time() - t_start
                debug_logger.log(f"_run_whisper done in {elapsed:.2f}s, text={text[:80]!r}")
                return text, elapsed
            except RuntimeError as e:
                err = str(e).lower()
                # CUDA fatal errors — reset GPU and reload model
                if DEVICE == "cuda" and any(k in err for k in _CUDA_FATAL):
                    debug_logger.log(f"_run_whisper CUDA error (attempt {attempt}): {e}")
                    model = self._recover_cuda()
                    if model is None:
                        raise
                    # After recovery, restart from attempt 0 logic (fresh kwargs)
                    kwargs["fp16"] = True
                    kwargs.pop("condition_on_previous_text", None)
                    continue
                if attempt < 3 and any(k in err for k in _RETRYABLE):
                    self.on_status(
                        f"Retry {attempt + 1}/3 — adjusting parameters...",
                        "#f59e0b",
                    )
                    continue
                raise
        return "", time.time() - t_start  # all retries exhausted

    def _recover_cuda(self):
        """Reset CUDA state and reload the Whisper model. Returns model or None."""
        try:
            self.on_status("CUDA error — resetting GPU and reloading model...", "#f59e0b")
            debug_logger.log("_recover_cuda: clearing model and resetting CUDA")
            self.whisper_model = None
            self._fast_model = None
            import gc
            gc.collect()
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            # Some CUDA errors leave the context dirty; synchronize to clear
            try:
                torch.cuda.synchronize()
            except Exception:
                pass
            debug_logger.log("_recover_cuda: reloading model")
            self.whisper_model = self._load_engine_model(self.current_model_name)
            self._last_activity = time.time()
            debug_logger.log("_recover_cuda: model reloaded OK")
            self.on_status("GPU recovered — retrying transcription...", "#f59e0b")
            return self.whisper_model
        except Exception as e:
            debug_logger.log(f"_recover_cuda FAILED: {e}")
            self.on_status(f"GPU recovery failed: {e}", "#ef4444")
            return None

    def _pick_model(self, duration_secs):
        """Pick Whisper model — use fast/tiny for short audio (CHG025)."""
        use_fast = (
            self.settings.get("adaptive_model", False)
            and duration_secs < 3.0
            and self.current_model_name not in ("tiny", "base")
        )
        if use_fast:
            if self._fast_model is None:
                try:
                    self._fast_model = self._load_engine_model("tiny")
                except Exception:
                    use_fast = False
        return self._fast_model if use_fast and self._fast_model else self.whisper_model

    def _postprocess_transcription(self, transcription, t_elapsed, do_paste=True):
        """Shared post-processing: text corrections, history, stats, paste."""
        if not transcription:
            return transcription
        # CHG012 / CHG7: command mode — use OpenAI or local LLM
        use_local = self.settings.get("use_local_llm", False)
        has_ai = bool(self.settings.get("openai_api_key")) or (
            use_local and self.local_llm.is_loaded
        )
        if self._command_context and has_ai:
            cmd_processor = (
                self.openai_processor
                if self.settings.get("openai_api_key")
                else self.local_llm
            )
            transformed = cmd_processor.execute_command(
                self._command_context, transcription,
            )
            if transformed:
                transcription = transformed
            self._command_context = None
        else:
            debug_logger.log("_postprocess entering _process_text ...")
            transcription = self._process_text(transcription)
            debug_logger.log("_postprocess _process_text done")

        self._last_transcription = transcription
        self._save_to_history(transcription)

        # CHG028: stats
        wc = len(transcription.split())
        self.stats.record(t_elapsed, wc)
        self.on_transcription_stats(t_elapsed, wc, self.stats.get_all_time()["words"])

        if do_paste and self.auto_paste:
            debug_logger.log("_postprocess pasting ...")
            self._paste_text(transcription)
            debug_logger.log("_postprocess paste done")

        return transcription

    # ------------------------------------------------------------------
    # Transcribe from microphone recording
    # ------------------------------------------------------------------
    def _transcribe(self, audio_array):
        self.on_status("Transcribing...", "#f59e0b")
        self._last_activity = time.time()
        debug_logger.log("_transcribe START")

        if not self._ensure_model_loaded():
            self.on_transcription_error("Model not available")
            return
        debug_logger.log("_transcribe model loaded OK")

        duration_secs = len(audio_array) / self.sample_rate
        model = self._pick_model(duration_secs)

        try:
            # Feed the recording straight from memory — it is already 16kHz mono
            # float32, which both engines accept, so no temp WAV round-trip.
            audio_input = np.asarray(audio_array, dtype=np.float32).reshape(-1)

            kwargs = self._build_whisper_kwargs()
            transcription, t_elapsed = self._run_whisper(model, audio_input, kwargs)

            transcription = self._postprocess_transcription(
                transcription, t_elapsed, do_paste=True
            )

            debug_logger.log("_transcribe calling on_transcription_complete")
            self.on_transcription_complete(transcription)
            debug_logger.log("_transcribe END")

        except Exception as e:
            debug_logger.log(f"_transcribe EXCEPTION: {e}")
            self.on_transcription_error(str(e))

    # ------------------------------------------------------------------
    # Transcribe from audio file
    # ------------------------------------------------------------------
    def transcribe_file(self, file_path):
        """Transcribe an audio/video file. Called from a background thread."""
        if self.settings.get("speaker_diarization", False):
            self._transcribe_file_diarized(file_path)
            return

        fname = os.path.basename(file_path)
        self.on_status(f"Transcribing {fname}...", "#f59e0b")
        self._last_activity = time.time()
        debug_logger.log(f"transcribe_file START: {file_path}")

        if not self._ensure_model_loaded():
            self.on_transcription_error("Model not available")
            return

        try:
            try:
                info = sf.info(file_path)
                duration_secs = info.duration
            except Exception:
                duration_secs = 999

            model = self._pick_model(duration_secs)
            kwargs = self._build_whisper_kwargs()
            transcription, t_elapsed = self._run_whisper(model, file_path, kwargs)

            transcription = self._postprocess_transcription(
                transcription, t_elapsed, do_paste=False
            )

            debug_logger.log("transcribe_file calling on_transcription_complete")
            self.on_transcription_complete(transcription)
            debug_logger.log("transcribe_file END")

        except Exception as e:
            debug_logger.log(f"transcribe_file EXCEPTION: {e}")
            self.on_transcription_error(str(e))

    def _transcribe_file_diarized(self, file_path):
        """Transcribe file with WhisperX speaker diarization."""
        fname = os.path.basename(file_path)
        debug_logger.log(f"_transcribe_file_diarized START: {file_path}")

        try:
            import whisperx
        except ImportError:
            self.on_status("whisperx not installed — run: pip install whisperx", "#ef4444")
            self.on_transcription_error(
                "whisperx is not installed.\n\nInstall it with:\n  pip install whisperx"
            )
            return

        hf_token = self.settings.get("hf_token", "").strip()
        if not hf_token:
            self.on_transcription_error(
                "Hugging Face token is required for speaker detection.\n"
                "Add it in Settings → Speaker tab."
            )
            return

        num_speakers_setting = self.settings.get("num_speakers", 0)
        num_speakers = None if num_speakers_setting == 0 else num_speakers_setting
        compute_type = "float16" if DEVICE == "cuda" else "int8"

        try:
            self.on_status(f"Loading WhisperX model for {fname}...", "#f59e0b")
            wx_model = whisperx.load_model(
                self.current_model_name, DEVICE,
                compute_type=compute_type,
                download_root=self.model_dir,
            )

            self.on_status("Transcribing audio...", "#f59e0b")
            audio = whisperx.load_audio(file_path)
            result = wx_model.transcribe(audio, batch_size=16 if DEVICE == "cuda" else 4)
            detected_lang = result.get("language", "en")

            if self.settings.get("speaker_align", False):
                self.on_status("Aligning transcript (word-level)...", "#f59e0b")
                model_a, metadata = whisperx.load_align_model(
                    language_code=detected_lang, device=DEVICE
                )
                result = whisperx.align(
                    result["segments"], model_a, metadata, audio, DEVICE,
                    return_char_alignments=False,
                )

            _hf_cache = os.path.join(
                os.path.expanduser("~"), ".cache", "huggingface", "hub",
                "models--pyannote--speaker-diarization-3.1"
            )
            _cached = os.path.isdir(_hf_cache)
            _status_msg = "Detecting speakers..." if _cached else "Detecting speakers (downloading ~65 MB on first run)..."
            self.on_status(_status_msg, "#f59e0b")
            try:
                _DiarizationPipeline = whisperx.DiarizationPipeline
            except AttributeError:
                from whisperx.diarize import DiarizationPipeline as _DiarizationPipeline
            diarize_model = _DiarizationPipeline(
                model_name="pyannote/speaker-diarization-3.1",
                token=hf_token, device=DEVICE
            )
            diarize_segments = diarize_model(audio, num_speakers=num_speakers)
            result = whisperx.assign_word_speakers(diarize_segments, result)

            transcription = self._format_diarized_output(result["segments"])
            if not transcription.strip():
                transcription = "[No speech detected]"

            self._last_transcription = transcription
            self._save_to_history(transcription)
            wc = len(transcription.split())
            self.stats.record(0, wc)
            self.on_transcription_stats(0, wc, self.stats.get_all_time()["words"])
            self.on_transcription_complete(transcription)
            debug_logger.log("_transcribe_file_diarized END")

        except Exception as e:
            debug_logger.log(f"_transcribe_file_diarized EXCEPTION: {e}")
            self.on_transcription_error(str(e))

    def _format_diarized_output(self, segments):
        """Format diarized segments as a labelled conversation."""
        # Build a stable speaker → label mapping in order of first appearance
        speaker_map = {}
        for seg in segments:
            sp = seg.get("speaker")
            if sp and sp not in speaker_map:
                speaker_map[sp] = f"Speaker {len(speaker_map) + 1}"

        lines = []
        current_label = None
        current_parts = []

        for seg in segments:
            sp = seg.get("speaker")
            label = speaker_map.get(sp, "Unknown") if sp else "Unknown"
            text = seg.get("text", "").strip()
            if not text:
                continue
            if label != current_label:
                if current_label is not None and current_parts:
                    lines.append(f"{current_label}: {' '.join(current_parts)}")
                    lines.append("")
                current_label = label
                current_parts = [text]
            else:
                current_parts.append(text)

        if current_label and current_parts:
            lines.append(f"{current_label}: {' '.join(current_parts)}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Text processing pipeline
    # ------------------------------------------------------------------
    def _process_text(self, text):
        processed = text
        debug_logger.log(f"_process_text input: {text[:80]!r}")

        # CHG005 / CHG017: dictionary corrections
        processed = self.dictionary.apply_corrections(processed)

        # CHG010: filler removal
        if self.settings.get("filler_removal", False):
            processed = TextProcessor.remove_fillers(processed)

        # CHG011: backtrack correction
        if self.settings.get("backtrack_correction", False):
            processed = TextProcessor.apply_backtrack(processed)

        # CHG016: snippet replacement
        processed = self.snippets.apply_snippets(processed)

        # CHG004 / CHG7: AI text enhancement — use OpenAI or local LLM
        api_key = self.settings.get("openai_api_key", "")
        use_local = self.settings.get("use_local_llm", False)
        ai_processor = None
        ai_was_used = False
        if api_key:
            self.openai_processor.set_api_key(api_key)
            ai_processor = self.openai_processor
        elif use_local and self.local_llm.is_loaded:
            ai_processor = self.local_llm

        if ai_processor:
            debug_logger.log(f"_process_text AI processor: {type(ai_processor).__name__}")
            if self.settings.get("correct_grammar") or self.settings.get("auto_format"):
                debug_logger.log("_process_text calling ai_processor.process() ...")
                processed = ai_processor.process(
                    processed,
                    correct_grammar=self.settings.get("correct_grammar", False),
                    auto_format=self.settings.get("auto_format", False),
                )
                ai_was_used = True
                debug_logger.log("_process_text ai_processor.process() done")

            # CHG013: context-aware tone
            if self.settings.get("context_aware_tone", False):
                app_name = self.get_foreground_app()
                if app_name:
                    debug_logger.log(f"_process_text adjusting tone for {app_name} ...")
                    processed = ai_processor.adjust_tone(processed, app_name)
                    debug_logger.log("_process_text tone done")

        # CHG019: numbered list formatting — runs after AI so the regex can
        # catch any lists the LLM missed.  If AI already converted ordinals
        # to "1.", "2." etc., the regex guard (>=2 word-markers) won't fire.
        if self.settings.get("numbered_list_format", False):
            processed = TextProcessor.format_numbered_list(processed)

        debug_logger.log(f"_process_text DONE: {processed[:80]!r}")
        return processed.strip()

    # ------------------------------------------------------------------
    # Auto-paste (CHG027: configurable delay)
    # ------------------------------------------------------------------
    def _paste_text(self, text):
        try:
            try:
                original = pyperclip.paste()
            except Exception:
                original = None

            # CHG014 / CHG9-fix: smart text insertion — skip when text is
            # selected (Ctrl+V over a selection should just replace it, not
            # shift-left into surrounding text) or when command mode handled it.
            if self.settings.get("smart_insertion", False) and not self._command_context:
                has_selection = False
                try:
                    keyboard.send('ctrl+c')
                    time.sleep(0.05)
                    clip_now = pyperclip.paste()
                    has_selection = (clip_now != original and bool(clip_now.strip()))
                    if original is not None:
                        pyperclip.copy(original)
                except Exception:
                    pass
                if not has_selection:
                    preceding = self._get_preceding_char()
                    if preceding:
                        text = TextProcessor.adjust_for_insertion(text, preceding)

            pyperclip.copy(text)
            delay = self.settings.get("paste_delay_ms", 100) / 1000.0
            time.sleep(delay)
            keyboard.send('ctrl+v')
            time.sleep(max(delay, 0.15))

            if original is not None:
                pyperclip.copy(original)
        except Exception as e:
            print(f"Auto-paste failed: {e}")

    def _get_preceding_char(self):
        """Try to read the character before cursor in the active app (CHG014)."""
        try:
            original = pyperclip.paste()
            keyboard.send('shift+left')
            time.sleep(0.05)
            keyboard.send('ctrl+c')
            time.sleep(0.05)
            char = pyperclip.paste()
            keyboard.send('right')
            time.sleep(0.05)
            if original:
                pyperclip.copy(original)
            if char and len(char) == 1:
                return char
        except Exception:
            pass
        return None

    def repaste_last(self):
        """Re-paste the last transcription (CHG020)."""
        if self._last_transcription:
            self._paste_text(self._last_transcription)

    def copy_last(self):
        """Copy the last transcription to the clipboard, without pasting.

        Returns True if something was copied, False if there is no last
        transcription yet (or the clipboard write failed).
        """
        if self._last_transcription:
            try:
                pyperclip.copy(self._last_transcription)
                return True
            except Exception as e:
                debug_logger.log(f"copy_last FAILED: {e}")
        return False

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------
    def _save_to_history(self, transcription):
        path = os.path.join(self._history_dir, "transcriptions.txt")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}]\n{transcription}\n{'-' * 60}\n")

    def read_history(self):
        path = os.path.join(self._history_dir, "transcriptions.txt")
        if not os.path.exists(path):
            return "No transcription history yet."
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return "No transcription history yet."
        entries = [e.strip() for e in raw.split("-" * 60) if e.strip()]
        entries.reverse()
        return ("\n" + "-" * 60 + "\n").join(entries)

    def read_history_entries(self):
        path = os.path.join(self._history_dir, "transcriptions.txt")
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return []
        entries = []
        for chunk in raw.split("-" * 60):
            chunk = chunk.strip()
            if not chunk:
                continue
            lines = chunk.split("\n", 1)
            ts = lines[0].strip().strip("[]")
            text = lines[1].strip() if len(lines) > 1 else ""
            entries.append((ts, text))
        return entries

    def delete_history_entries(self, timestamps_to_delete):
        all_entries = self.read_history_entries()
        remaining = [(ts, txt) for ts, txt in all_entries if ts not in timestamps_to_delete]
        path = os.path.join(self._history_dir, "transcriptions.txt")
        if not remaining:
            if os.path.exists(path):
                os.remove(path)
            return
        with open(path, "w", encoding="utf-8") as f:
            for ts, txt in remaining:
                f.write(f"[{ts}]\n{txt}\n{'-' * 60}\n")

    def clear_history(self):
        path = os.path.join(self._history_dir, "transcriptions.txt")
        if os.path.exists(path):
            os.remove(path)

    def export_history(self, filepath, fmt="txt"):
        """Export history to file (CHG029). fmt = 'txt' or 'csv'."""
        entries = self.read_history_entries()
        if fmt == "csv":
            import csv
            with open(filepath, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Timestamp", "Transcription"])
                for ts, txt in entries:
                    writer.writerow([ts, txt])
        else:
            with open(filepath, "w", encoding="utf-8") as f:
                for ts, txt in entries:
                    f.write(f"[{ts}]\n{txt}\n{'-' * 60}\n")

    # ------------------------------------------------------------------
    # System utilities
    # ------------------------------------------------------------------
    @staticmethod
    def get_foreground_app():
        """Get name of focused window (CHG013, CHG031)."""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        except Exception:
            return ""

    @staticmethod
    def set_auto_start(enabled):
        """Add/remove NeuraType from Windows startup (CHG030)."""
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            name = "NeuraType"
            if enabled:
                if _PORTABLE:
                    # Portable: NeuraType.exe is one level above app/
                    exe = os.path.join(os.path.dirname(_BASE_DIR), "NeuraType.exe")
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, f'"{exe}"')
                else:
                    bat = os.path.join(_BASE_DIR, "run.bat")
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, bat)
            else:
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            print(f"Auto-start setting failed: {e}")

    # ------------------------------------------------------------------
    # Hotkey watchdog — re-registers all hotkeys if the keyboard
    # library's internal listener thread dies (common after
    # sleep/wake, long idle, or Windows hook timeout).
    # ------------------------------------------------------------------
    def start_hotkey_watchdog(self):
        """Start a background thread that periodically checks hotkey health."""
        self._hotkey_watchdog_running = True
        threading.Thread(target=self._hotkey_watchdog, daemon=True).start()

    def _hotkey_watchdog(self):
        while self._hotkey_watchdog_running:
            time.sleep(10)
            if not self._hotkey_watchdog_running:
                break
            try:
                listener = keyboard._listener
                needs_restart = False
                if listener is None:
                    needs_restart = True
                elif not getattr(listener, "listening", False):
                    needs_restart = True
                else:
                    lt = getattr(listener, "listening_thread", None)
                    pt = getattr(listener, "processing_thread", None)
                    if lt and not lt.is_alive():
                        needs_restart = True
                    if pt and not pt.is_alive():
                        needs_restart = True

                if needs_restart:
                    debug_logger.log("Hotkey watchdog: listener dead, force-restarting...")
                    keyboard.unhook_all()
                    keyboard.unhook_all_hotkeys()
                    if listener is not None:
                        listener.listening = False
                        for attr in ('blocking_hotkeys', 'nonblocking_hotkeys',
                                     'blocking_keys', 'nonblocking_keys',
                                     'filtered_modifiers', 'modifier_states'):
                            d = getattr(listener, attr, None)
                            if d is not None:
                                try:
                                    d.clear()
                                except Exception:
                                    pass
                        if hasattr(listener, 'handlers'):
                            listener.handlers.clear()
                    self._reregister_all_hotkeys()
            except Exception as e:
                debug_logger.log(f"Hotkey watchdog error: {e}")

    def _reregister_all_hotkeys(self):
        """Re-register every hotkey from scratch."""
        debug_logger.log(f"_reregister_all_hotkeys: start, hotkey={self.current_hotkey!r}, "
                         f"cancel={self.current_cancel_hotkey!r}")
        # Clear any existing hotkey registrations first. The `keyboard` library
        # stacks a new handler on every add_hotkey() call, so without this a
        # repeated re-register makes each hotkey fire multiple times (e.g. the
        # repaste hotkey pasting 3x). Starting from a clean slate keeps exactly
        # one handler per combo.
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        try:
            keyboard.add_hotkey(self.current_hotkey, self._hotkey_triggered_internal)
            debug_logger.log(f"_reregister_all_hotkeys: registered main hotkey OK")
        except Exception as e:
            debug_logger.log(f"_reregister_all_hotkeys: FAILED main hotkey: {e}")
        try:
            keyboard.add_hotkey(self.current_cancel_hotkey, self._cancel_hotkey_triggered_internal)
            debug_logger.log(f"_reregister_all_hotkeys: registered cancel hotkey OK")
        except Exception as e:
            debug_logger.log(f"_reregister_all_hotkeys: FAILED cancel hotkey: {e}")
        try:
            keyboard.add_hotkey(self.current_pause_hotkey, self._pause_hotkey_triggered_internal)
            debug_logger.log(f"_reregister_all_hotkeys: registered pause hotkey OK")
        except Exception as e:
            debug_logger.log(f"_reregister_all_hotkeys: FAILED pause hotkey: {e}")
        try:
            hk = self.settings.get("repaste_hotkey", "alt+shift+z")
            keyboard.add_hotkey(hk, self._repaste_triggered)
            debug_logger.log(f"_reregister_all_hotkeys: registered repaste hotkey OK")
        except Exception as e:
            debug_logger.log(f"_reregister_all_hotkeys: FAILED repaste hotkey: {e}")
        try:
            hk = self.settings.get("history_hotkey", "ctrl+shift+h")
            keyboard.add_hotkey(hk, lambda: self.on_history_hotkey_triggered())
            debug_logger.log(f"_reregister_all_hotkeys: registered history hotkey OK")
        except Exception as e:
            debug_logger.log(f"_reregister_all_hotkeys: FAILED history hotkey: {e}")
        try:
            hk = self.settings.get("refresh_hotkey", "ctrl+alt+z")
            if hk:
                keyboard.add_hotkey(hk, lambda: self.on_refresh_hotkey_triggered())
                debug_logger.log(f"_reregister_all_hotkeys: registered refresh hotkey OK")
        except Exception as e:
            debug_logger.log(f"_reregister_all_hotkeys: FAILED refresh hotkey: {e}")
        debug_logger.log("_reregister_all_hotkeys: done")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def cleanup(self):
        self._hotkey_watchdog_running = False
        self.unregister_hotkey()
        self.unregister_cancel_hotkey()
        self.unregister_pause_hotkey()
        self.unregister_repaste_hotkey()
        self.unregister_history_hotkey()
        self.unregister_refresh_hotkey()
