# Changelog

A running log of notable changes to NeuraType, newest first.

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
