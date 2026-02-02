import torch
from views.console_menu import ConsoleMenu
from views.gui_app import TranscriberGUI  # ← Add this


def main():
    print(f"🔧 CUDA Available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"   CUDA Version: {torch.version.cuda}\n")
    
    # Choose interface
    print("Choose interface:")
    print("  [1] Console (CLI)")
    print("  [2] GUI")
    
    choice = input("Select: ").strip()
    
    if choice == "2":
        app = TranscriberGUI()
        app.run()
    else:
        menu = ConsoleMenu()
        menu.run()


if __name__ == "__main__":
    main()