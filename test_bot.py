import subprocess
import sys
import time

def print_header(text):
    print("\n" + "="*60)
    print(text)
    print("="*60 + "\n")

def run_command(command, description):
    print_header(description)
    print(f"Running: {command}\n")
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        if result.returncode == 0:
            print(f"\n✓ {description} completed successfully")
            return True
        else:
            print(f"\n✗ {description} failed with return code {result.returncode}")
            return False
    
    except subprocess.TimeoutExpired:
        print(f"\n✗ {description} timed out")
        return False
    except Exception as e:
        print(f"\n✗ {description} failed: {str(e)}")
        return False

def main():
    print_header("RASA CHATBOT TESTING SCRIPT")
    
    # Quote the Python executable path for Windows if it contains spaces
    py = f'"{sys.executable}"'
    tests = [
        (f"{py} -m rasa data validate", "Step 1: Validating training data"),
        (f"{py} -m rasa train --domain domain.yml --data data --out models", "Step 2: Training the model (this may take several minutes)"),
        (f"{py} -m rasa test nlu --nlu data/nlu.yml --cross-validation", "Step 3: Testing NLU with cross-validation"),
    ]
    
    results = []
    
    for command, description in tests:
        success = run_command(command, description)
        results.append((description, success))
        
        if not success and "train" in command.lower():
            print("\nTraining failed. Stopping tests.")
            break
        
        time.sleep(2)
    
    print_header("TEST RESULTS SUMMARY")
    for description, success in results:
        status = "✓ PASSED" if success else "✗ FAILED"
        print(f"{status}: {description}")
    
    print("\nNext steps:")
    print("1. Review the model performance in results/")
    print("2. Test interactively: python -m rasa shell")
    print("3. Start action server: python -m rasa run actions")
    print("4. Start bot: python -m rasa run")

if __name__ == "__main__":
    main()