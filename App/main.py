import time
from Controller import TranscriptionController

controller = TranscriptionController("small", device=10)

print("Recording 10 seconds...")
controller.startCapture("live.wav")

start = time.time()
last_print = start

while time.time() - start < 10:
    controller.recorder.readChunk()  # record one chunk

    # print elapsed every 0.5 sec so you see it running
    now = time.time()
    if now - last_print >= 0.5:
        print(f"elapsed: {now - start:.1f}s")
        last_print = now

print("Stopping + transcribing...")
words = controller.stopAndTranscribe()

for w in words:
    print(f"{w.text} [{w.startTime:.2f} - {w.endTime:.2f}]")
