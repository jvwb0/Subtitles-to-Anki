import time
from Controller import TranscriptionController

controller = TranscriptionController("small", device=10)

print("Recording 10 seconds... (live mode)")
controller.startLive("live.wav")

start = time.time()
last_print = start

while time.time() - start < 10:
    controller.liveTick()  # record one chunk

    # print elapsed every 0.5 sec so you see it running
start = time.time()
while time.time() - start < 10:
    controller.liveTick()  # record one chunk

print("Stopping + transcribing...")
words = controller.stopLiveAndTranscribe()
for w in words:
    print(f"{w.text} [{w.startTime:.2f} - {w.endTime:.2f}]")
