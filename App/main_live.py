import subprocess
import sys
import time
from Controller import TranscriptionController

print("\nListing available audio devices (WASAPI loopback):\n")

# run: python -m pyaudiowpatch
subprocess.run([sys.executable, "-m", "pyaudiowpatch"])
    
print(
    "\nPlease choose which device to use for loopback recording\n"
    "(Look for WASAPI devices with LOOPBACK = True)\n"
)

device_str = input("Enter device index (number): ")
DEVICE = int(device_str.strip())
controller = TranscriptionController("small", device=DEVICE) #sizes: tiny, base, small, medium, large

print("Recording 10 seconds... (live mode)")
controller.startLive("live.wav")

start = time.time()

while time.time() - start < 10:
    controller.liveTick()  # record one chunk

print("Stopping + transcribing...")

words = controller.stopLiveAndTranscribe()

if len(words) == 0:
    print("No words detected. Likely wrong loopback device (no audio captured). Try device 16 vs 17.")
    sys.exit(0)

for w in words:
    print(f"{w.text} [{w.startTime:.2f} - {w.endTime:.2f}]")
