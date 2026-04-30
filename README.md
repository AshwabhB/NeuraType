# NeuraType

Offline speech-to-text for Windows with a global hotkey. Press a key combo from any app, speak, press again — your words are transcribed and pasted automatically. Powered by [OpenAI Whisper](https://github.com/openai/whisper), running entirely on your machine.

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

**For GPU acceleration (CUDA 12.6):**

```bash
pip install torch==2.10.0+cu126 --index-url https://download.pytorch.org/whl/cu126
```

Skip the line above if you only have a CPU — the app will fall back automatically.

### 4. Download a Whisper model

Models are not included in this repository. Download one and place it in the `models/` folder.

| Model | File | Size | Notes |
|---|---|---|---|
| tiny | `tiny.pt` | 75 MB | Fastest, lower accuracy |
| base | `base.pt` | 145 MB | Good for simple dictation |
| small | `small.pt` | 484 MB | Balanced |
| medium | `medium.pt` | 1.5 GB | Higher accuracy |
| **turbo** | `large-v3-turbo.pt` | 1.6 GB | **Recommended** — best speed/accuracy |
| large | `large-v3.pt` | 3.1 GB | Highest accuracy, slow on CPU |

Download links (official Whisper releases):

```
https://openaipublic.azureedge.net/main/whisper/models/tiny.pt
https://openaipublic.azureedge.net/main/whisper/models/base.pt
https://openaipublic.azureedge.net/main/whisper/models/small.pt
https://openaipublic.azureedge.net/main/whisper/models/medium.pt
https://openaipublic.azureedge.net/main/whisper/models/large-v3-turbo.pt
https://openaipublic.azureedge.net/main/whisper/models/large-v3.pt
```

Place the downloaded `.pt` file inside the `models/` folder:

```
neuratype/
└── models/
    └── large-v3-turbo.pt   ← here
```

### 5. Run the app

**Right-click your terminal and choose "Run as administrator"**, then:

```bash
venv\Scripts\activate
python speech_to_text_app.py
```


## Usage

| Action | Default hotkey |
|---|---|
| Start / stop recording | `Ctrl + Shift + Alt` |
| Cancel recording | `Ctrl + Shift + Space` |
| Show history | `Ctrl + Shift + H` |
| Repaste last transcription | `Alt + Shift + Z` |

1. Open any app and click into a text field.
2. Press the hotkey — a recording indicator appears.
3. Speak your message.
4. Press the hotkey again — transcription is processed and pasted.

All hotkeys are configurable from the app's settings panel.

## Optional: OpenAI API key

Some features (grammar correction, context-aware formatting) use the OpenAI API. If you want these, add your key in the app's settings panel after first launch. The key is stored in `settings.json`, which is excluded from git.

## Privacy

All transcription runs locally. No audio ever leaves your machine. The OpenAI API is only contacted if you explicitly enable AI-powered features.

## Troubleshooting

**Hotkey does nothing** — make sure you launched the app as Administrator.

**`keyboard` library error on startup** — same cause; run as Administrator.

**Transcription is slow** — install the CUDA version of torch (step 3 above) and use the `turbo` model.

**Wrong microphone** — select the correct input device from the dropdown in the app.

**Auto-paste doesn't work** — some apps block programmatic paste. Disable auto-paste in settings and copy from the app manually.
