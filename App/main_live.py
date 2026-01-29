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

    controller = TranscriptionController("small", device=device)

    print("Recording 10 seconds... (live mode)")
    words = controller.runLiveSession(
        durationSec=10.0,
        windowSec=2.0,
        tickSleep=0.25,
        filename="live.wav"
    )

    if len(words) == 0:
        print("No words detected. Likely wrong loopback device (no audio captured). Try device 16 vs 17.")
        return

    for w in words:
        print(f"{w.text} [{w.startTime:.2f} - {w.endTime:.2f}]")


if __name__ == "__main__":
    main()
