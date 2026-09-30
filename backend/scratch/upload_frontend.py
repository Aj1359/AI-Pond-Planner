import paramiko
import os
import time

HOST = "10.1.75.51"
PORT = 2217
USERNAME = "student"
PASSWORD = "Adityajha123!"
LOCAL_FILE = r"e:\AI pond\pond_planner\frontend\index.html"

def log(msg):
    print(str(msg).encode('ascii', errors='replace').decode('ascii'), flush=True)

def connect():
    for attempt in range(1, 6):
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(HOST, port=PORT, username=USERNAME, password=PASSWORD, timeout=10)
            log(f"[+] Connected on attempt {attempt}")
            return client
        except Exception as e:
            log(f"[-] Attempt {attempt} failed: {e}")
            time.sleep(2)
    return None

client = connect()
if client:
    sftp = client.open_sftp()
    log("Uploading fixed index.html...")
    sftp.put(LOCAL_FILE, "/home/student/AI-Pond-Planner/frontend/index.html")
    sftp.close()
    
    # Also update the nginx-served copy
    stdin, stdout, stderr = client.exec_command(
        f"echo '{PASSWORD}' | sudo -S cp /home/student/AI-Pond-Planner/frontend/index.html /var/www/pond_planner/frontend/index.html"
    )
    out = stdout.read().decode()
    err = stderr.read().decode()
    log(f"Copy to nginx dir: {out} {err}")
    
    # Verify
    stdin, stdout, stderr = client.exec_command(
        "grep 'const API' /var/www/pond_planner/frontend/index.html"
    )
    log("Verify: " + stdout.read().decode().strip())
    
    client.close()
    log("✅ Done! index.html updated on VM1.")
else:
    log("❌ Failed to connect")
