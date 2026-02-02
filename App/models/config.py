from dataclasses import dataclass


@dataclass
class TranscriptionConfig:
    model_size: str = "tiny"
    device_id: int = 10
    use_gpu: bool = False
    language: str = "en"
    
    def __str__(self):
        return f"Model: {self.model_size}, Device: {self.device_id}, GPU: {self.use_gpu}, Lang: {self.language}"