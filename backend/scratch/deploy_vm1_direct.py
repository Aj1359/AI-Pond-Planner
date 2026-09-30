import os
import paramiko
import time

HOST = "10.1.75.51"
PORT = 2217
USERNAME = "student"
PASSWORD = "Adityajha123!"
LOCAL_DIR = r"e:\AI pond\pond_planner"

def log(msg):
    safe_msg = str(msg).encode('ascii', errors='replace').decode('ascii')
    print(safe_msg, flush=True)

def connect():
    for attempt in range(1, 10):
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(HOST, port=PORT, username=USERNAME, password=PASSWORD, timeout=10)
            log(f"[+] Connected to VM1 (port {PORT}) on attempt {attempt}")
            return client
        except Exception as e:
            log(f"[-] Attempt {attempt} failed: {e}. Retrying in 2s...")
            time.sleep(2)
    return None

def sftp_upload_dir(sftp, local_dir, remote_dir):
    try:
        sftp.mkdir(remote_dir)
    except Exception:
        pass
    
    for root, dirs, files in os.walk(local_dir):
        rel_root = os.path.relpath(root, local_dir)
        r_dir = remote_dir if rel_root == "." else f"{remote_dir}/{rel_root}".replace("\\", "/")
        try:
            sftp.mkdir(r_dir)
        except Exception:
            pass
        
        for f in files:
            if f.endswith(('.zip', '.pdf', '.log', '.aux', '.out', '.toc', '.tex', '.pyc')):
                continue
            l_path = os.path.join(root, f)
            r_path = f"{r_dir}/{f}"
            log(f"   Uploading {f} -> {r_path}")
            sftp.put(l_path, r_path)

def run_cmd(client, cmd):
    log(f"CMD: {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, get_pty=True)
    out = stdout.read().decode('utf-8', errors='ignore')
    log(f"RESULT:\n{out}")
    return out

def main():
    log("=== DEPLOYING FRONTEND & NGINX TO VM1 VIA SFTP ===")
    client = connect()
    if not client:
        log("❌ Failed to connect to VM1!")
        return

    remote_app = "/home/student/AI-Pond-Planner"
    run_cmd(client, f"mkdir -p {remote_app}/deploy {remote_app}/frontend")

    sftp = client.open_sftp()
    
    log("1. Uploading deploy files...")
    sftp_upload_dir(sftp, os.path.join(LOCAL_DIR, "deploy"), f"{remote_app}/deploy")
    
    log("2. Uploading frontend static files...")
    sftp_upload_dir(sftp, os.path.join(LOCAL_DIR, "frontend"), f"{remote_app}/frontend")
    
    sftp.close()

    log("3. Configuring Nginx on VM1...")
    commands = f"""
echo '{PASSWORD}' | sudo -S killall -9 lb 2>/dev/null || true
echo '{PASSWORD}' | sudo -S fuser -k 4217/tcp 2>/dev/null || true
echo '{PASSWORD}' | sudo -S fuser -k 80/tcp 2>/dev/null || true
echo '{PASSWORD}' | sudo -S mkdir -p /var/www/pond_planner/frontend /var/cache/nginx/pond
echo '{PASSWORD}' | sudo -S rm -rf /var/www/pond_planner/frontend/*
echo '{PASSWORD}' | sudo -S cp -r /home/student/AI-Pond-Planner/frontend/* /var/www/pond_planner/frontend/
echo '{PASSWORD}' | sudo -S chmod -R 755 /var/www/pond_planner
echo '{PASSWORD}' | sudo -S cp /home/student/AI-Pond-Planner/deploy/nginx_lb.conf /etc/nginx/nginx.conf
echo '{PASSWORD}' | sudo -S nginx -t
echo '{PASSWORD}' | sudo -S service nginx restart
sleep 1
echo '--- PORT VERIFICATION ---'
ss -tulpn | grep -E ':80|:4217'
echo '--- CURL UI VERIFICATION ---'
curl -i http://127.0.0.1:4217/ui/
"""
    run_cmd(client, commands)
    client.close()
    log("✅ VM1 Deployment Complete!")

if __name__ == "__main__":
    main()
