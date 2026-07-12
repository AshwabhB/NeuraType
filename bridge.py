"""JS <-> Python bridge for the NeuraType web UI.

Three pieces:
  EventDispatcher — single thread funnelling Python events into the webview
                    via evaluate_js. Coalesces audio-level, buffers state
                    events while the window is hidden, replays on ui_ready.
  Controller      — recording orchestration shared by hotkeys, tray and UI
                    (toggle debounce, model-reload guard, indicator hooks).
  Api             — the js_api object exposed as window.pywebview.api.
"""

import json
import os
import queue
import threading
import time

import backend as be
from backend import (
    DEVICE,
    GPU_INFO,
    LOCAL_LLM_MODELS,
    SUPPORTED_LANGUAGES,
    WHISPER_MODELS,
    TranscriberBackend,
    debug_logger,
    is_first_boot,
    load_settings,
    mark_first_boot_done,
    save_settings,
)

APP_VERSION = "2.0.0"

# Events whose latest payload is replayed to the UI on ui_ready (Ctrl+R
# reload, hide/show) so the page never comes up blank.
_STATE_EVENTS = {
    "status", "model-loaded", "model-load-failed", "recording-state",
    "download-progress", "stats",
}
# High-frequency events that are dropped while the window is hidden.
_TRANSIENT_EVENTS = {"audio-level", "mic-check-level"}


class EventDispatcher:
    """Serialises all Python->JS traffic through one daemon thread."""

    def __init__(self):
        self._q = queue.Queue()
        self._window = None
        self._visible = True
        self._last_state = {}
        self._lock = threading.Lock()
        self._level_payload = None
        self._level_queued = False
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="nt-dispatcher")
        self._thread.start()

    def attach(self, window):
        self._window = window

    def set_visible(self, visible):
        self._visible = visible

    def emit(self, name, payload=None):
        payload = payload if payload is not None else {}
        if name in _STATE_EVENTS:
            with self._lock:
                self._last_state[name] = payload
        if name == "audio-level":
            if not self._visible:
                return
            with self._lock:
                self._level_payload = payload
                if self._level_queued:
                    return  # coalesce: one marker in queue at a time
                self._level_queued = True
            self._q.put(("audio-level", None))
            return
        if name in _TRANSIENT_EVENTS and not self._visible:
            return
        self._q.put((name, payload))

    def replay_state(self):
        """Re-emit last known state events (called on ui_ready)."""
        with self._lock:
            items = list(self._last_state.items())
        for name, payload in items:
            self._q.put((name, payload))

    def _run(self):
        while True:
            name, payload = self._q.get()
            if name == "audio-level":
                with self._lock:
                    payload = self._level_payload
                    self._level_queued = False
            window = self._window
            if window is None:
                continue
            if not self._visible and name in _TRANSIENT_EVENTS:
                continue
            try:
                window.evaluate_js(
                    "window.__nt && window.__nt.emit(%s, %s)"
                    % (json.dumps(name), json.dumps(payload))
                )
            except Exception as e:
                # Window mid-hide/teardown — drop the event, state replay
                # will restore anything important on next ui_ready.
                debug_logger.log(f"dispatcher: evaluate_js failed for {name}: {e}")


class LevelPump:
    """Pushes backend.audio_level to the UI ~30fps while recording."""

    INTERVAL = 0.033

    def __init__(self, backend, dispatcher):
        self._backend = backend
        self._dispatcher = dispatcher
        self._active = threading.Event()
        threading.Thread(target=self._run, daemon=True, name="nt-levelpump").start()

    def start(self):
        self._active.set()

    def stop(self):
        self._active.clear()

    def _run(self):
        while True:
            self._active.wait()
            self._dispatcher.emit("audio-level", {"v": round(self._backend.audio_level, 4)})
            time.sleep(self.INTERVAL)


class Controller:
    """Owns the backend and orchestrates recording state.

    Hotkeys, tray menu and UI buttons all route through here so the
    debounce/guard logic lives in exactly one place (ported from the old
    NeuraTypeWindow._toggle_recording / _toggle_pause).
    """

    def __init__(self, dispatcher):
        self.dispatcher = dispatcher
        self.window = None          # set by app.py after window creation
        self.indicator = None       # set in Phase 3 (native pill overlay)
        self.tray = None            # set in Phase 3
        self._toggle_busy = False
        self._pause_busy = False
        self._last_refresh = 0.0

        d = dispatcher
        self.backend = TranscriberBackend(
            on_status=lambda text, color: d.emit("status", {"text": text, "color": color}),
            on_model_loaded=self._on_model_loaded,
            on_model_load_failed=lambda err: d.emit("model-load-failed", {"error": err}),
            on_transcription_complete=self._on_transcription_complete,
            on_transcription_error=self._on_transcription_error,
            on_hotkey_triggered=self.toggle_recording,
            on_cancel_hotkey_triggered=self.cancel_recording,
            on_predownload_progress=lambda name, idx, total: d.emit(
                "download-progress", {"model": name, "index": idx, "total": total}),
            on_hold_release=self._stop_if_recording,
            on_silence_detected=self._stop_if_recording,
            on_history_hotkey_triggered=self._on_history_hotkey,
            on_repaste_hotkey_triggered=lambda: None,  # backend pastes internally
            on_transcription_stats=lambda elapsed, words, total: d.emit(
                "stats", {"elapsed": elapsed, "words": words, "totalWords": total}),
            on_refresh_hotkey_triggered=self.refresh_hotkeys,
            on_pause_hotkey_triggered=self.toggle_pause,
        )
        self.level_pump = LevelPump(self.backend, dispatcher)

    # -- recording state machine ---------------------------------------

    def _emit_state(self, state, detail=""):
        self.dispatcher.emit("recording-state", {"state": state, "detail": detail})

    def toggle_recording(self):
        if self._toggle_busy:
            return
        self._toggle_busy = True
        threading.Timer(0.3, lambda: setattr(self, "_toggle_busy", False)).start()

        if self.backend.model_loading:
            self.dispatcher.emit("toast", {
                "kind": "warn", "text": "Model is still loading — try again in a moment"})
            return
        if not self.backend.is_recording:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        b = self.backend
        # If the GPU idle timer released the model, kick off an async reload
        # instead of blocking the hotkey thread.
        if b._gpu_released or b.whisper_model is None:
            if not b.model_loading:
                b.reload_model()
            self.dispatcher.emit("toast", {
                "kind": "warn", "text": "Model is reloading — try again in a moment"})
            return
        try:
            b.start_recording()
        except Exception as e:
            self.dispatcher.emit("toast", {"kind": "error",
                                           "text": f"Failed to start recording: {e}"})
            return
        self._emit_state("recording")
        self.level_pump.start()
        if self.indicator is not None and self.backend.settings.get("recording_indicator", True):
            self.indicator.show()

    def stop_recording(self):
        self.level_pump.stop()
        if self.indicator is not None:
            self.indicator.hide()
        self._emit_state("transcribing")
        stopped = self.backend.stop_recording()
        if not stopped:
            self._emit_state("idle")

    def _stop_if_recording(self):
        if self.backend.is_recording:
            self.stop_recording()

    def cancel_recording(self):
        if not self.backend.is_recording:
            return
        self.level_pump.stop()
        if self.indicator is not None:
            self.indicator.hide()
        self.backend.cancel_recording()
        self._emit_state("idle", "cancelled")
        self.dispatcher.emit("toast", {"kind": "info", "text": "Recording cancelled"})

    def toggle_pause(self):
        if not self.backend.is_recording:
            return
        if self._pause_busy:
            return
        self._pause_busy = True
        threading.Timer(0.3, lambda: setattr(self, "_pause_busy", False)).start()
        paused = self.backend.toggle_pause()
        if paused:
            self.level_pump.stop()
            if self.indicator is not None:
                self.indicator.set_paused(True)
            self._emit_state("paused")
        else:
            self.level_pump.start()
            if self.indicator is not None:
                self.indicator.set_paused(False)
            self._emit_state("recording")

    # -- backend callback handlers --------------------------------------

    def _on_model_loaded(self, model_name):
        self.dispatcher.emit("model-loaded", {
            "model": model_name,
            "device": "GPU" if DEVICE == "cuda" else "CPU",
        })
        self._emit_state("idle")

    def _on_transcription_complete(self, text):
        self._emit_state("idle")
        self.dispatcher.emit("transcription", {"text": text})

    def _on_transcription_error(self, error):
        self._emit_state("idle", "error")
        self.dispatcher.emit("transcription-error", {"error": error})

    def _on_history_hotkey(self):
        self.show_window()
        self.dispatcher.emit("navigate", {"view": "history"})

    # -- window control (tray/instance hooks land here in Phase 3) ------

    def show_window(self):
        if self.window is not None:
            try:
                self.window.show()
                self.window.restore()
            except Exception:
                pass
            self.dispatcher.set_visible(True)
            self.dispatcher.replay_state()

    def hide_window(self):
        if self.window is not None:
            self.dispatcher.set_visible(False)
            try:
                self.window.hide()
            except Exception:
                pass

    def quit_app(self):
        try:
            self.backend.cleanup()
        except Exception:
            pass
        if self.indicator is not None:
            try:
                self.indicator.destroy()
            except Exception:
                pass
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception:
                pass
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception:
                pass

    # -- hotkey maintenance ----------------------------------------------

    def refresh_hotkeys(self):
        """Nuke and re-register all global hotkeys (ported from old UI)."""
        now = time.time()
        if now - self._last_refresh < 1.0:
            return
        self._last_refresh = now
        try:
            import keyboard
            keyboard.unhook_all()
            listener = getattr(keyboard, "_listener", None)
            if listener is not None:
                if hasattr(listener, "blocking_hotkeys"):
                    listener.blocking_hotkeys.clear()
                if hasattr(listener, "nonblocking_hotkeys"):
                    listener.nonblocking_hotkeys.clear()
                for attr in ("blocking_keys", "nonblocking_keys"):
                    table = getattr(listener, attr, None)
                    if table is not None:
                        try:
                            table.clear()
                        except Exception:
                            pass
                if hasattr(listener, "handlers"):
                    listener.handlers.clear()
            self.backend._reregister_all_hotkeys()
            # If the OS-level hook is dead, re-registering handlers alone
            # can't revive it — force the watchdog to probe on its next tick.
            self.backend._last_kb_event = 0.0
            self.dispatcher.emit("toast", {"kind": "success", "text": "Hotkeys refreshed"})
        except Exception as e:
            self.dispatcher.emit("toast", {"kind": "error",
                                           "text": f"Hotkey refresh failed: {e}"})


class Api:
    """Exposed to JS as window.pywebview.api — every method returns JSON-able data."""

    def __init__(self, controller):
        self._c = controller
        self._mic_check_active = False

    @property
    def _b(self):
        return self._c.backend

    # -- lifecycle -------------------------------------------------------

    def ui_ready(self):
        """Called by JS once the page has booted; replays state so reloads
        and hide/show cycles never leave a blank UI."""
        self._c.dispatcher.replay_state()
        return self.get_system_info()

    def hide_to_tray(self):
        self._c.hide_window()
        return True

    def quit_app(self):
        threading.Thread(target=self._c.quit_app, daemon=True).start()
        return True

    # -- system info -----------------------------------------------------

    def get_system_info(self):
        b = self._b
        return {
            "version": APP_VERSION,
            "device": "GPU" if DEVICE == "cuda" else "CPU",
            "gpuInfo": GPU_INFO,
            "engine": b.engine,
            "model": b.current_model_name,
            "modelLoading": b.model_loading,
            "isRecording": b.is_recording,
            "isPaused": b.is_paused,
            "hotkey": b.current_hotkey,
            "firstBoot": is_first_boot(),
            "hasLastAudio": b.has_last_audio(),
        }

    # -- recording -------------------------------------------------------

    def start_recording(self):
        if not self._b.is_recording:
            self._c.toggle_recording()
        return True

    def stop_recording(self):
        if self._b.is_recording:
            self._c.stop_recording()
        return True

    def toggle_recording(self):
        self._c.toggle_recording()
        return True

    def cancel_recording(self):
        self._c.cancel_recording()
        return True

    def toggle_pause(self):
        self._c.toggle_pause()
        return self._b.is_paused

    def retry_transcription(self):
        ok = self._b.retry_transcription()
        if ok:
            self._c._emit_state("transcribing")
        return ok

    def transcribe_file(self):
        """Open a native file dialog and start file transcription."""
        import webview
        b = self._b
        if b._gpu_released or b.whisper_model is None:
            if not b.model_loading:
                b.reload_model()
            return {"ok": False, "reason": "model-reloading"}
        result = self._c.window.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=(
                "Audio/Video Files (*.mp3;*.wav;*.m4a;*.mp4;*.flac;*.ogg;*.webm;*.wma;*.aac;*.mkv;*.avi;*.mov)",
                "All files (*.*)",
            ),
        )
        if not result:
            return {"ok": False, "reason": "cancelled"}
        path = result[0]
        self._c._emit_state("transcribing", os.path.basename(path))
        threading.Thread(target=b.transcribe_file, args=(path,), daemon=True).start()
        return {"ok": True, "file": os.path.basename(path)}

    # -- playback ---------------------------------------------------------

    def play_last_audio(self, start_frame=0):
        return self._b.play_last_audio(int(start_frame))

    def stop_playback(self):
        self._b.stop_playback()
        return True

    def get_playback_state(self):
        b = self._b
        total = int(len(b._last_audio)) if b._last_audio is not None else 0
        return {
            "frame": b.get_playback_frame(),
            "total": total,
            "sampleRate": b.sample_rate,
        }

    # -- clipboard ----------------------------------------------------------

    def copy_last(self):
        return self._b.copy_last()

    def repaste_last(self):
        self._b.repaste_last()
        return True

    # -- models -------------------------------------------------------------

    def get_models(self):
        b = self._b
        return {
            "whisper": [
                {"name": k, "size": v["size"], "desc": v["desc"]}
                for k, v in WHISPER_MODELS.items()
            ],
            "llm": [
                {"name": k, "size": v["size"], "desc": v["desc"]}
                for k, v in LOCAL_LLM_MODELS.items()
            ],
            "downloadedWhisper": b.get_downloaded_whisper_models(),
            "downloadedLlm": b.get_downloaded_llm_models(),
            "current": b.current_model_name,
            "currentLlm": b.local_llm.current_model_name,
        }

    def load_model(self, name):
        self._b.load_model(name)
        return True

    def unload_model(self):
        self._b.unload_model()
        return True

    def reload_model(self):
        self._b.reload_model()
        return True

    def delete_model(self, kind, name):
        if kind == "llm":
            return self._b.delete_llm_model(name)
        return self._b.delete_whisper_model(name)

    def predownload_models(self):
        self._b.predownload_all_models()
        return True

    # -- audio devices --------------------------------------------------------

    def get_input_devices(self):
        return {
            "devices": TranscriberBackend.get_input_devices(),
            "default": TranscriberBackend.get_default_input_device_name(),
            "selected": self._b.settings.get("mic_device_name"),
        }

    def start_mic_check(self, duration=2.0):
        if self._mic_check_active:
            return False
        self._mic_check_active = True

        def run():
            try:
                result = self._b.check_mic(
                    duration=float(duration),
                    on_level=lambda v: self._c.dispatcher.emit(
                        "mic-check-level", {"v": round(float(v), 4)}),
                )
                self._c.dispatcher.emit("mic-check-done", result if isinstance(result, dict)
                                        else {"error": str(result)})
            except Exception as e:
                self._c.dispatcher.emit("mic-check-done", {"error": str(e)})
            finally:
                self._mic_check_active = False

        threading.Thread(target=run, daemon=True).start()
        return True

    # -- settings ----------------------------------------------------------

    def get_settings(self):
        return dict(self._b.settings)

    def get_languages(self):
        return list(SUPPORTED_LANGUAGES.keys())

    def set_setting(self, key, value):
        """Write one setting and live-apply where the backend supports it."""
        b = self._b
        b.settings[key] = value
        save_settings(b.settings)
        try:
            if key == "hotkey":
                b.change_hotkey(value)
            elif key == "cancel_hotkey":
                b.change_cancel_hotkey(value)
            elif key == "pause_hotkey":
                b.change_pause_hotkey(value)
            elif key == "hotkey_enabled":
                b.set_hotkey_enabled(bool(value))
            elif key == "auto_paste":
                b.set_auto_paste(bool(value))
            elif key == "auto_start":
                TranscriberBackend.set_auto_start(bool(value))
            elif key == "debug_logging":
                debug_logger.set_enabled(bool(value))
            elif key == "openai_api_key":
                b.openai_processor.set_api_key(value)
            elif key == "local_llm_model":
                b.local_llm.set_model(value)
            elif key == "mic_device_name":
                devices = TranscriberBackend.get_input_devices()
                for idx, name in enumerate(devices):
                    if name == value:
                        b.selected_device_index = idx
                        break
            elif key == "model":
                b.load_model(value)
            elif key in ("repaste_hotkey", "history_hotkey", "refresh_hotkey"):
                self._c.refresh_hotkeys()
        except Exception as e:
            debug_logger.log(f"set_setting live-apply failed for {key}: {e}")
            return {"ok": False, "error": str(e)}
        return {"ok": True}

    def refresh_hotkeys(self):
        self._c.refresh_hotkeys()
        return True

    def validate_openai_key(self, key):
        try:
            from openai import OpenAI
            client = OpenAI(api_key=key)
            client.models.list()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # -- dictionary / snippets ------------------------------------------------

    def dictionary_get(self):
        d = self._b.dictionary
        return {"words": d.get_allowed_words(), "corrections": d.get_corrections()}

    def dictionary_add(self, word):
        self._b.dictionary.add_word(word)
        return self.dictionary_get()

    def dictionary_remove(self, word):
        self._b.dictionary.remove_word(word)
        return self.dictionary_get()

    def snippets_get(self):
        return self._b.snippets.get_all()

    def snippets_add(self, trigger, replacement):
        self._b.snippets.add_snippet(trigger, replacement)
        return self.snippets_get()

    def snippets_remove(self, trigger):
        self._b.snippets.remove_snippet(trigger)
        return self.snippets_get()

    # -- history -----------------------------------------------------------

    def history_page(self, offset=0, limit=50, query="", sort="newest"):
        entries = self._b.read_history_entries()  # [(ts, text)] oldest-first
        if sort == "newest":
            entries = list(reversed(entries))
        if query:
            q = query.lower()
            entries = [(ts, txt) for ts, txt in entries if q in txt.lower() or q in ts.lower()]
        total = len(entries)
        page = entries[offset:offset + limit]
        return {
            "total": total,
            "entries": [{"ts": ts, "text": txt} for ts, txt in page],
        }

    def history_delete(self, timestamps):
        self._b.delete_history_entries(set(timestamps))
        return True

    def history_clear(self):
        self._b.clear_history()
        return True

    def history_export(self, fmt="txt"):
        import webview
        default_name = "neuratype_history.csv" if fmt == "csv" else "neuratype_history.txt"
        result = self._c.window.create_file_dialog(
            webview.SAVE_DIALOG, save_filename=default_name)
        if not result:
            return {"ok": False, "reason": "cancelled"}
        path = result if isinstance(result, str) else result[0]
        self._b.export_history(path, fmt)
        return {"ok": True, "path": path}

    # -- stats -----------------------------------------------------------

    def get_stats(self):
        s = self._b.stats
        return {
            "allTime": s.get_all_time(),
            "today": s.get_today(),
            "session": s.get_session(),
            "daily": s._data.get("daily", {}),
        }

    # -- first boot ---------------------------------------------------------

    def complete_first_boot(self, whisper_models, llm_models):
        b = self._b
        b.settings["selected_whisper_models"] = whisper_models
        b.settings["selected_llm_models"] = llm_models
        if llm_models:
            b.settings["use_local_llm"] = True
        save_settings(b.settings)
        mark_first_boot_done()
        b.predownload_all_models()
        return True
