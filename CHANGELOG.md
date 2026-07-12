# Changelog

A running log of notable changes to NeuraType, newest first.

## 2026-07-11

### Fixed

- **Hotkeys randomly dying (and the refresh hotkey doing nothing).** Root cause was a hotkey collision: the "Refresh Hotkeys" combo defaulted to the same combo as the record hotkey (`ctrl+alt+z`), so every recording press also ran the destructive hotkey-refresh routine. That routine reset the keyboard listener in a way that spawned an *additional* listener thread with an *additional* Windows low-level hook each time — hooks stacked up (a single press eventually fired handlers 10–12×), slowed every keystroke, and Windows then silently removed the timed-out hooks, killing all hotkeys at once. The refresh hotkey couldn't recover because it rode on the same dead hook, and the watchdog couldn't detect it because the listener threads were still alive.
  - Refresh hotkey default changed to `ctrl+alt+r`; conflicting values in saved settings are migrated automatically at startup.
  - Hotkey collisions are now rejected everywhere: settings save resolves duplicates, `change_*` validators check all six hotkeys against each other, and a conflicting refresh combo is skipped at registration.
  - The manual refresh no longer resets the listener (no more hook stacking); it only clears and re-registers handlers.
  - The watchdog now detects the "threads alive but hook silently removed" state by tracking real event flow and, after 60s of silence, injecting a harmless F24 key-up probe — if the hook doesn't see it, the listener is force-restarted. Hotkeys self-heal within ~70 seconds instead of dying until an app restart.

## 2026-06-29

### Changed

- **Switched the transcription engine to [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2) for better memory efficiency.** The app now runs the same Whisper models through a leaner inference engine instead of the reference PyTorch implementation, for lower idle resource use so it sits lighter in the background (less GPU/VRAM pressure on games and other apps).
  - Same model weights, run through CTranslate2 at `float16` — accuracy is unchanged; this is purely an efficiency improvement.
  - Default `float16` compute type preserves full accuracy (no int8 quantization).
  - `openai-whisper` remains available as a fallback engine via the `engine` setting, so the change is reversible.

### Added

- **Idle GPU release** — an optional timer unloads the model and frees GPU memory after a period of inactivity, then reloads it automatically before the next transcription.
- **Tray action: "Copy Last Transcription"** — copies the most recent transcription to the clipboard from the system tray (works while the window is hidden), with a confirmation toast.

### Fixed

- **Repaste hotkey pasting multiple times** — hotkey re-registration stacked duplicate handlers, causing a single press to fire several times. Registrations are now cleared before re-adding, and hotkey refreshes are debounced to prevent runaway re-registration.
- **Recording indicator missing or chopped on secondary monitors** — the floating pill was positioned with Win32 physical-pixel coordinates while Qt expects logical (DPI-scaled) coordinates, which pushed it off-screen on monitors with different display scaling. It now uses Qt's per-screen geometry for the screen under the cursor.
