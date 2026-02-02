class Word:
    def __init__(self, text: str, startTime: float, endTime: float):
        self.text = text.strip()
        self.startTime = float(startTime)
        self.endTime = float(endTime)