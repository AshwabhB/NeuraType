import sys
print(f"Python executable: {sys.executable}")

try:
    import torch
    print(f"torch: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA device: {torch.cuda.get_device_name(0)}")
except ImportError:
    print("torch: MISSING")

try:
    import whisper
    print(f"whisper module file: {whisper.__file__}")
except ImportError:
    print("whisper: MISSING")
