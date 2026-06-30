# NeuraType

Offline speech-to-text for Windows with a global hotkey. Press a key combo from any app, speak, press again — your words are transcribed and pasted automatically. Powered by [OpenAI Whisper](https://github.com/openai/whisper) models, accelerated with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2), running entirely on your machine.

## Features

- **Global hotkey dictation** — transcribe into any app without switching windows
- **File transcription** — drag and drop or open any audio/video file
- **Speaker detection** — identifies and labels multiple speakers in file transcription (optional, see below)
- **Local AI text processing** — grammar correction, auto-formatting, filler word removal
- **History** — searchable log of all transcriptions
- Fully offline — no audio ever leaves your machine

## Requirements

- Windows 10/11
- Python 3.11
- Administrator privileges (required for global hotkeys)
- [ffmpeg](https://ffmpeg.org/download.html) — must be on your PATH
- A Whisper model file (see below)
- NVIDIA GPU recommended for fast transcription (CPU works but is slower)

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/neuratype.git
cd neuratype
```

### 2. Create a virtual environment

```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r pip-requirements.txt
```

**For GPU acceleration (CUDA 12.1):**

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

Skip the line above if you only have a CPU — the app will fall back automatically.

### 4. Choose a Whisper model

NeuraType uses the **faster-whisper (CTranslate2)** engine by default. Models are **downloaded automatically** on first use into the `models/` folder — there is no manual download step. Just select a model in the app and start transcribing; the first run fetches it.

| Model | Size | Notes |
|---|---|---|
| tiny | ~39 MB | Fastest, basic accuracy |
| base | ~74 MB | Fast, decent accuracy |
| small | ~244 MB | Moderate speed, good accuracy |
| medium | ~769 MB | Slower, very good accuracy |
| **turbo** | ~1.5 GB | **Recommended** — best speed/accuracy |
| large | ~1.5 GB | Slowest, best accuracy |

> **Using the `openai-whisper` fallback engine?** That engine uses OpenAI's original `.pt` model files instead of the CTranslate2 format. They also download automatically on first use, or you can drop a `.pt` file into the `models/` folder manually. Switch engines with the `engine` setting (`faster-whisper` or `openai-whisper`).

### 5. Run the app

**Right-click your terminal and choose "Run as administrator"**, then:

```bash
venv\Scripts\activate
python speech_to_text_app.py
```


## Usage

| Action | Default hotkey |
|---|---|
| Start / stop recording | `Ctrl + Win` |
| Cancel recording | `Ctrl + Shift + Space` |
| Show history | `Ctrl + Shift + H` |
| Repaste last transcription | `Alt + Shift + Z` |
| Refresh hotkeys | `Ctrl + Alt + Z` |

1. Open any app and click into a text field.
2. Press the hotkey — a recording indicator appears.
3. Speak your message.
4. Press the hotkey again — transcription is processed and pasted.

All hotkeys are configurable from the app's settings panel.

## Optional: Speaker Detection (File Transcription)

NeuraType can identify and label individual speakers in audio/video files, formatting output as a conversation:

```
Speaker 1: Hello, how are you?

Speaker 2: I'm doing well, thanks for asking.
```

This uses [WhisperX](https://github.com/m-bain/whisperX) and [pyannote.audio](https://github.com/pyannote/pyannote-audio). Setup is a one-time process:

### Step 1 — Install WhisperX

```bash
venv\Scripts\pip install whisperx
```

Then reinstall CUDA torch (whisperx overwrites it with a CPU build):

```bash
venv\Scripts\pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121 --force-reinstall --no-deps
```

Skip the second command if you are on CPU only.

### Step 2 — Accept model licenses on Hugging Face

Create a free account at [huggingface.co](https://huggingface.co), then visit and click **Agree** on both of these pages:

- [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
- [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)

### Step 3 — Generate a Hugging Face token

Go to [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) → **New token** → Role: **Read** → **Generate**.

Copy the token (starts with `hf_...`).

### Step 4 — Enable in NeuraType

Open **Settings → Speaker tab**:
- Check **Enable speaker detection**
- Paste your token into the **Hugging Face Token** field
- Set **Number of Speakers** (or leave on Auto-detect)
- Click **OK**

The diarization models (~65 MB total) download automatically on the first file transcription. Subsequent runs are instant.

> Speaker detection only applies to **file transcription** — microphone recording is unaffected.

## Optional: OpenAI API key

Some features (grammar correction, context-aware formatting) use the OpenAI API. If you want these, add your key in the app's settings panel after first launch. The key is stored in `settings.json`, which is excluded from git.

## Privacy

All transcription runs locally. No audio ever leaves your machine. The OpenAI API is only contacted if you explicitly enable AI-powered features. The Hugging Face token is used only to verify model license acceptance — no audio is sent to Hugging Face.

## Troubleshooting

**Hotkey does nothing** — make sure you launched the app as Administrator.

**`keyboard` library error on startup** — same cause; run as Administrator.

**Transcription is slow** — install the CUDA version of torch (step 3 above) and use the `turbo` model.

**Wrong microphone** — select the correct input device from the dropdown in the app.

**Auto-paste doesn't work** — some apps block programmatic paste. Disable auto-paste in settings and copy from the app manually.

**Speaker detection shows CPU mode after installing WhisperX** — whisperx overwrites your CUDA torch. Run the force-reinstall command in Step 1 above, then restart the app.

**Speaker detection 403 error** — your Hugging Face token is missing or you haven't accepted the model licenses. Complete Steps 2–4 above.
