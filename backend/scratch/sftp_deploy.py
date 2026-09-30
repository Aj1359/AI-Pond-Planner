import os
import paramiko
import time

HOST = "10.1.75.51"
PORTS = {
    "VM1_LB": 2217,
    "VM2_BE": 2218,
    "VM3_BE": 2219,
    "VM4_BE": 2220
}
PASSWORD = "Adityajha123!"
USERNAME = "student"
LOCAL_DIR = r"e:\AI pond\pond_planner"

def log(msg):
    safe_msg = str(msg).encode('ascii', errors='replace').decode('ascii')
    print(safe_msg, flush=True)

def connect(port):
    for attempt in range(1, 4):
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(HOST, port=port, username=USERNAME, password=PASSWORD, timeout=6)
            log(f"   [+] Connected to port {port} as '{USERNAME}' (attempt {attempt})")
            return client
        except Exception as e:
            log(f"   [-] Port {port} attempt {attempt} failed: {e}")
            time.sleep(2)
    return None

def sftp_upload_dir(sftp, local_path, remote_path):
    try: sftp.mkdir(remote_path)
    except Exception: pass

    for item in os.listdir(local_path):
        if item in ['.git', '__pycache__', 'venv', '.venv', '.pytest_cache']:
            continue
        l_item = os.path.join(local_path, item)
        r_item = remote_path + "/" + item
        if os.path.isdir(l_item):
            sftp_upload_dir(sftp, l_item, r_item)
        else:
            sftp.put(l_item, r_item)

def run_cmd(client, cmd):
    stdin, stdout, stderr = client.exec_command(cmd, get_pty=True)
    out = stdout.read().decode('utf-8', errors='ignore')
    err = stderr.read().decode('utf-8', errors='ignore')
    return out + err

def deploy_all():
    log("=== FINAL MULTI-NODE DEPLOYMENT ACROSS ALL 4 VMs ===")
    
    # 1. Backends on VM2, VM3, VM4
    for vm_name in ["VM2_BE", "VM3_BE", "VM4_BE"]:
        port = PORTS[vm_name]
        log(f"\n---> [{vm_name}] Connecting on port {port}...")
        client = connect(port)
        if not client:
            log(f"   [!] Skipping {vm_name} due to connection timeout.")
            continue
        
        remote_app = f"/home/{USERNAME}/AI-Pond-Planner"
        log(f"   Uploading latest files to {remote_app}...")
        sftp = client.open_sftp()
        sftp_upload_dir(sftp, LOCAL_DIR, remote_app)
        sftp.close()
        
        log(f"   Executing deploy_backend.sh with nohup...")
        cmd = f"cd {remote_app}/deploy && nohup bash deploy_backend.sh > /dev/null 2>&1 &"
        out = run_cmd(client, cmd)
        log(f"   {vm_name} Output:\n{out[-350:]}")
        client.close()

    # 2. Load Balancer & Frontend on VM1
    port = PORTS["VM1_LB"]
    log(f"\n---> [VM1_LB] Connecting on port {port}...")
    client = connect(port)
    if client:
        remote_app = f"/home/{USERNAME}/AI-Pond-Planner"
        log(f"   Uploading latest files to {remote_app}...")
        sftp = client.open_sftp()
        sftp_upload_dir(sftp, LOCAL_DIR, remote_app)
        sftp.close()
        
        log(f"   Executing deploy_lb.sh with sudo...")
        cmd = f"cd {remote_app}/deploy && echo '{PASSWORD}' | sudo -S bash deploy_lb.sh"
        out = run_cmd(client, cmd)
        log(f"   VM1_LB Output:\n{out[-400:]}")
        client.close()

    log("\n=== ALL DEPLOYMENTS FINISHED! ===")

if __name__ == "__main__":
    deploy_all()
