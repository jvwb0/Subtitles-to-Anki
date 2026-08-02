import torch
from views.gui_app import TranscriberGUI


def main():
    print(f"🔧 CUDA Available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"   CUDA Version: {torch.version.cuda}\n")
    
    app = TranscriberGUI()
    app.run()


if __name__ == "__main__":
    main()
