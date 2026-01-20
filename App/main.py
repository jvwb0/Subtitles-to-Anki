from Controller import TranscriptionController

controller = TranscriptionController("small") #model size can be: tiny, base, small, medium, large
words = controller.transcribeWav("brasilmeme.wav") #path to audio file

for w in words:
    print(f"{w.text} [{w.startTime:.2f} - {w.endTime:.2f}]")
