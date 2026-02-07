import subprocess
import sys
import os
import shutil

def run_command(command, cwd=None):
    """Helper function to run shell commands."""
    try:
        print(f"Executing: {' '.join(command)} in {cwd if cwd else os.getcwd()}")
        result = subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {' '.join(command)}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        sys.exit(1)
    except FileNotFoundError:
        print(f"Error: Command not found. Make sure {' '.join(command).split(' ')[0]} is installed and in your PATH.")
        sys.exit(1)

def check_command(command_name):
    """Checks if a command is available in the system's PATH."""
    if shutil.which(command_name):
        return True
    else:
        print(f"Error: '{command_name}' not found. Please install it and add to your system PATH.")
        sys.exit(1)

def install_backend_dependencies():
    """Installs backend Python dependencies."""
    print("Installing backend Python dependencies...")
    check_command("pip")
    run_command([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], cwd="backend")
    print("Backend dependencies installed successfully.")

def install_frontend_dependencies():
    """Installs frontend Node.js dependencies and builds the project."""
    print("Installing frontend Node.js dependencies...")
    check_command("npm")
    run_command(["npm", "install"], cwd="frontend")
    print("Frontend dependencies installed successfully.")

    print("Building frontend project...")
    run_command(["npm", "run", "build"], cwd="frontend")
    print("Frontend built successfully.")

def install_launcher_dependencies():
    """Installs launcher Python dependencies."""
    print("Installing launcher Python dependencies...")
    check_command("pip")
    run_command([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], cwd="launcher")
    print("Launcher dependencies installed successfully.")

def main():
    """Main function to orchestrate the installation."""
    print("Starting system installation...")

    # Set current working directory to the project root
    script_dir = os.path.dirname(__file__)
    project_root = os.path.abspath(os.path.join(script_dir, os.pardir))
    os.chdir(project_root)
    print(f"Changed current directory to: {os.getcwd()}")

    install_backend_dependencies()
    install_frontend_dependencies()
    install_launcher_dependencies()

    print("
System installation completed successfully!")

if __name__ == "__main__":
    main()
