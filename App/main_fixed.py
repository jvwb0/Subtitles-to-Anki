from Controller import TranscriptionController

controller = TranscriptionController("small", device=10)
words = controller.transcribeWav("drake.wav")

for w in words:
    print(f"{w.text} [{w.startTime:.2f}-{w.endTime:.2f}]")