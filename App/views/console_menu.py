import subprocess
import sys
from models.config import TranscriptionConfig
from controllers.app_controller import AppController


class ConsoleMenu:
    def __init__(self):
        self.controller = None
        self.config = None
    
    def run(self):
        print("\n" + "="*50)
        print("  🎤  LIVE TRANSCRIBER")
        print("="*50)
        
        while True:
            print("\n📋 MENU:")
            print("  [1] Live Transcription")
            print("  [2] Transcribe WAV File")
            print("  [3] Exit")
            
            choice = input("\nSelect option: ").strip()
            
            if choice == "1":
                self._live_mode()
            elif choice == "2":
                self._wav_mode()
            elif choice == "3":
                print("👋 Goodbye!")
                break
            else:
                print("❌ Invalid choice")
    
    def _configure(self):
        print("\n⚙️  CONFIGURATION")
        print("-"*50)
        
        subprocess.run([sys.executable, "-m", "pyaudiowpatch"])
        
        device = int(input("\nDevice index: ").strip())
        model = input("Model (tiny/base/small/medium) [tiny]: ").strip().lower() or "tiny"
        language = input("Language (en/es/fr) [en]: ").strip().lower() or "en"
        use_gpu = input("Use GPU? (y/N): ").strip().lower().startswith("y")
        
        self.config = TranscriptionConfig(model, device, use_gpu, language)
        self.controller = AppController(self.config)
    
    def _live_mode(self):
        if not self.controller:
            self._configure()
        
        print("\n🎙️  LIVE TRANSCRIPTION")
        print("Choose mode:")
        print("  [1] Timed recording (specify duration)")
        print("  [2] Manual recording (press Enter to stop)")
        
        mode = input("\nMode: ").strip()
        
        if mode == "1":
            duration = float(input("Duration (seconds) [10]: ").strip() or "10")
            print(f"\n🔴 Recording for {duration}s...\n")
            
            self.controller.run_live_session(
                duration_sec=duration,
                window_sec=2.0,
                tick_sleep=0.1,
                save_wav=True,
                on_words_callback=self._print_words
            )
        
        elif mode == "2":
            print("\n🔴 Recording... (Press ENTER to stop)\n")
            
            self.controller.run_manual_session(
                window_sec=2.0,
                tick_sleep=0.1,
                save_wav=True,
                on_words_callback=self._print_words
            )
        
        else:
            print("❌ Invalid mode")
            return
        
        print("\n✅ Done!")
    
    def _wav_mode(self):
        if not self.controller:
            self._configure()
        
        print("\n📁 WAV FILE TRANSCRIPTION")
        filename = input("File path: ").strip()
        
        try:
            words = self.controller.transcribe_wav(filename)
            print(f"\n📝 {len(words)} words:\n")
            for w in words:
                print(f"  {w.text} [{w.startTime:.2f}s - {w.endTime:.2f}s]")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    @staticmethod
    def _print_words(words):
        output = " ".join(w.text for w in words)
        if output.strip():
            print(output, end=" ", flush=True)