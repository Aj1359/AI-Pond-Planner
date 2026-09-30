import paramiko
import os
import time

VM1_HOST = "10.1.75.51"
VM1_PORT = 2217
USERNAME = "student"
PASSWORD = "Adityajha123!"
LOCAL_FILE = r"e:\AI pond\pond_planner\backend\app\services\sites.py"

def log(msg):
    print(str(msg).encode('ascii', errors='replace').decode('ascii'), flush=True)

def connect():
    for attempt in range(1, 6):
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(VM1_HOST, port=VM1_PORT, username=USERNAME, password=PASSWORD, timeout=10)
            log(f"[+] Connected on attempt {attempt}")
            return client
        except Exception as e:
            log(f"[-] Attempt {attempt} failed: {e}")
            time.sleep(2)
    return None

client = connect()
if client:
    sftp = client.open_sftp()
    log("Uploading sites.py to VM1...")
    vm1_tmp_path = "sites.py"
    sftp.put(LOCAL_FILE, vm1_tmp_path)
    sftp.close()
    
    commands = [
        "sshpass -p 'Adityajha123!' scp -o StrictHostKeyChecking=no sites.py student@172.17.0.20:/home/student/pond_planner_backend/app/services/sites.py",
        "sshpass -p 'Adityajha123!' ssh -o StrictHostKeyChecking=no student@172.17.0.20 'pkill -9 -f uvicorn || true; sleep 1; cd ~/pond_planner_backend && nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 4000 --workers 2 > ~/backend.log 2>&1 &'"
    ]
    
    for cmd in commands:
        log(f"Running on VM1: {cmd}")
        stdin, stdout, stderr = client.exec_command(cmd)
        log("OUT: " + stdout.read().decode())
        log("ERR: " + stderr.read().decode())
        
    client.close()
    log("Done!")
else:
    log("Failed to connect")
