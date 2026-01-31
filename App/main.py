import torch  # Initialize CUDA
from views.console_menu import ConsoleMenu


def main():
    print(f"🔧 CUDA Available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"   CUDA Version: {torch.version.cuda}\n")
    
    menu = ConsoleMenu()
    menu.run()


if __name__ == "__main__":
    main()
    