import subprocess
import sys
from Controller import TranscriptionController


def main():
    print("\nListing available audio devices (WASAPI loopback):\n")
    subprocess.run([sys.executable, "-m", "pyaudiowpatch"])

    print(
        "\nPlease choose which device to use for loopback recording\n"
        "(Look for WASAPI devices with LOOPBACK = True)\n"
    )

    device = int(input("Enter device index (number): ").strip())

    # Choose model size for speed vs accuracy
    model_choice = input("Model size (tiny/base/small/medium) [tiny]: ").strip().lower()
    if model_choice == "":
        model_choice = "tiny"

    use_gpu_input = input("Use GPU if available? (y/N): ").strip().lower()
    use_gpu = use_gpu_input.startswith("y")

    print(f"Using model={model_choice}, device_index={device}, use_gpu={use_gpu}")

    print("Loading Whisper model... (this may take 30+ seconds on first run)")
    controller = TranscriptionController(model_choice, device=device, use_gpu=use_gpu)
    print("✓ Model loaded!")

    print("Recording 10 seconds... (live mode)")
    print("🎤 Make sure audio is PLAYING while recording!\n")

    # Lower-latency settings: smaller window, more frequent ticks
    # For CPU: use smaller window + more frequent checks
    controller.runLiveSession(
        durationSec=10.0,
        windowSec=2.0,      # balance window for CPU speed
        tickSleep=0.1,      # check less frequently to let CPU catch up
        saveWav=True,       # save audio for verification
        onWords=printWords
    )

    print("\n✅ Done! Saved live_*.wav for verification.")

def printWords(words):
    """Print new words as they're transcribed, without duplicates."""
    output = " ".join(w.text for w in words)
    if output.strip():
        print(output, end=" ", flush=True)


if __name__ == "__main__":
    main()
