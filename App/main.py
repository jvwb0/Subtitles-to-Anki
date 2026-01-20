from Controller import TranscriptionController

controller = TranscriptionController("small")
words = controller.transcribeWav("brasilmeme.wav")

for w in words:
    print(f"{w.text} [{w.startTime:.2f} - {w.endTime:.2f}]")
