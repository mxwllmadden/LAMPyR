import subprocess, sys
result = subprocess.run([sys.executable, '-m', 'pip', 'list'], capture_output=True, text=True)
print(result.stdout)
