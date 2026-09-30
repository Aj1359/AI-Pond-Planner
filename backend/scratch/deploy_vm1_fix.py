import paramiko
import os

HOST = "10.1.75.51"
PORT_VM1 = 2217
USERNAME = "student"
PASSWORD = "Adityajha123!"
LOCAL_DIR = r"e:\AI pond\pond_planner"

def log(msg):
    print(str(msg).encode('ascii', errors='replace').decode('ascii'), flush=True)

def sftp_upload_dir(sftp, local_path, remote_path):
    try: sftp.mkdir(remote_path)
    except: pass
    for item in os.listdir(local_path):
        if item in ['.git', '__pycache__', 'venv', '.venv', '.pytest_cache', 'node_modules']:
            continue
        l = os.path.join(local_path, item)
        r = remote_path + "/" + item
        if os.path.isdir(l):
            sftp_upload_dir(sftp, l, r)
        else:
            sftp.put(l, r)

log("Connecting to VM1 on port 2217...")
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, port=PORT_VM1, username=USERNAME, password=PASSWORD, timeout=15)
log("[+] Connected to VM1!")

log("Uploading files to VM1...")
sftp = client.open_sftp()
sftp_upload_dir(sftp, LOCAL_DIR, f"/home/{USERNAME}/AI-Pond-Planner")
sftp.close()
log("[+] Upload done.")

log("Running deploy_lb.sh on VM1...")
cmd = f"cd /home/{USERNAME}/AI-Pond-Planner/deploy && echo '{PASSWORD}' | sudo -S bash deploy_lb.sh 2>&1"
stdin, stdout, stderr = client.exec_command(cmd, get_pty=True)
out = stdout.read().decode('utf-8', errors='ignore').encode('ascii', errors='replace').decode('ascii')
log(out)

log("Checking listening ports on VM1...")
stdin2, stdout2, _ = client.exec_command("ss -tulpn | grep -E ':80|:4217'", get_pty=True)
log(stdout2.read().decode('utf-8', errors='ignore'))

log("Testing curl on VM1...")
stdin3, stdout3, _ = client.exec_command("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:4217/ui/ ; echo '' ; curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:80/ui/", get_pty=True)
log("4217 then 80: " + stdout3.read().decode('utf-8', errors='ignore'))

client.close()
log("=== VM1 DEPLOY COMPLETE ===")
