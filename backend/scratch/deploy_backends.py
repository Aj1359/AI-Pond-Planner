import os
import paramiko
import time

HOST = "10.1.75.51"
USERNAME = "student"
PASSWORD = "Adityajha123!"
LOCAL_BACKEND = r"e:\AI pond\pond_planner\backend"

# VM3=2219, can add VM2=2218, VM4=2220 if they come online
BACKEND_VMS = [
    ("VM3", 2219),
    # ("VM2", 2218),
    # ("VM4", 2220),
]

SKIP_DIRS = {'.git', '__pycache__', 'venv', '.venv', '.pytest_cache', 'scratch', 'models', '.pytest_cache'}
SKIP_EXTS = {'.pyc', '.zip', '.log', '.aux', '.out', '.toc', '.tex', '.pth', '.bin', '.pt'}

def log(msg):
    print(str(msg).encode('ascii', errors='replace').decode('ascii'), flush=True)

def connect(port):
    for attempt in range(1, 6):
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(HOST, port=port, username=USERNAME, password=PASSWORD, timeout=10)
            log(f"[+] Connected on port {port} (attempt {attempt})")
            return client
        except Exception as e:
            log(f"[-] Attempt {attempt} failed: {e}")
            time.sleep(3)
    return None

def sftp_upload_dir(sftp, local_dir, remote_dir):
    try:
        sftp.mkdir(remote_dir)
    except Exception:
        pass

    for item in os.listdir(local_dir):
        if item in SKIP_DIRS:
            continue
        l_path = os.path.join(local_dir, item)
        r_path = f"{remote_dir}/{item}"
        if os.path.isdir(l_path):
            sftp_upload_dir(sftp, l_path, r_path)
        else:
            ext = os.path.splitext(item)[1].lower()
            if ext in SKIP_EXTS:
                continue
            log(f"   -> {r_path}")
            sftp.put(l_path, r_path)

def run_cmd(client, cmd):
    log(f"CMD: {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, get_pty=False, timeout=30)
    out = stdout.read().decode('utf-8', errors='ignore')
    err = stderr.read().decode('utf-8', errors='ignore')
    if out: log(f"OUT: {out.strip()}")
    if err: log(f"ERR: {err.strip()}")
    return out

def deploy_backend(vm_name, port):
    log(f"\n=== Deploying backend to {vm_name} (port {port}) ===")
    client = connect(port)
    if not client:
        log(f"[!] Could not connect to {vm_name}")
        return

    remote_dir = "/home/student/pond_planner_backend"
    log(f"Uploading backend to {remote_dir}...")
    sftp = client.open_sftp()
    sftp_upload_dir(sftp, LOCAL_BACKEND, remote_dir)
    sftp.close()
    log("Upload complete!")

    # Kill old uvicorn, install deps, start fresh
    cmds = [
        "pkill -9 -f uvicorn || true",
        "sleep 1",
        f"cd {remote_dir} && pip install -r requirements.txt -q 2>&1 | tail -5",
        f"cd {remote_dir} && nohup python3 -m uvicorn main:app --host 0.0.0.0 --port 4000 --workers 2 > ~/backend.log 2>&1 &",
        "sleep 3",
        "curl -s http://127.0.0.1:4000/health",
    ]
    for cmd in cmds:
        run_cmd(client, cmd)

    client.close()
    log(f"✅ {vm_name} backend deployment done!")

if __name__ == "__main__":
    for vm_name, port in BACKEND_VMS:
        deploy_backend(vm_name, port)
    log("\n=== ALL BACKENDS DEPLOYED ===")
