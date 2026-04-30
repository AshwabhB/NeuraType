import sys
print(f"Python executable: {sys.executable}")

packages = ["numpy", "sounddevice", "soundfile", "whisper", "torch"]
for p in packages:
    try:
        __import__(p)
        print(f"{p}: OK")
    except ImportError as e:
        print(f"{p}: MISSING ({e})")
    except Exception as e:
        print(f"{p}: ERROR ({e})")
