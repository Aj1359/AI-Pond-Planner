import paramiko
import os
import time

HOST = "10.1.75.51"
PORT_VM1 = 2217
USERNAME = "student"
PASSWORD = "Adityajha123!"
LOCAL_DIR = r"e:\AI pond\pond_planner"

def log(msg):
    print(str(msg).encode('ascii', errors='replace').decode('ascii'), flush=True)

def run_ssh(client, cmd):
    log(f"RUNNING: {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    log(f"STDOUT:\n{out}")
    if err:
        log(f"STDERR:\n{err}")
    return out, err

def main():
    log("Connecting to VM1 via SSH...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT_VM1, username=USERNAME, password=PASSWORD, timeout=15)
    
    # 1. Kill rogue processes
    run_ssh(client, "sudo pkill -9 lb || true")
    run_ssh(client, "sudo pkill -9 nginx || true")
    run_ssh(client, "sudo fuser -k 4217/tcp || true")
    run_ssh(client, "sudo fuser -k 80/tcp || true")
    
    # 2. Make sure dir exists
    run_ssh(client, "mkdir -p ~/AI-Pond-Planner/deploy ~/AI-Pond-Planner/frontend")
    
    # 3. SFTP upload nginx_lb.conf and frontend
    sftp = client.open_sftp()
    
    local_nginx = os.path.join(LOCAL_DIR, "deploy", "nginx_lb.conf")
    log(f"Uploading {local_nginx} to ~/AI-Pond-Planner/deploy/nginx_lb.conf")
    sftp.put(local_nginx, "/home/student/AI-Pond-Planner/deploy/nginx_lb.conf")
    
    local_frontend = os.path.join(LOCAL_DIR, "frontend")
    log("Uploading frontend static files...")
    for root, dirs, files in os.walk(local_frontend):
        rel_path = os.path.relpath(root, local_frontend)
        remote_dir = "/home/student/AI-Pond-Planner/frontend" if rel_path == "." else f"/home/student/AI-Pond-Planner/frontend/{rel_path}".replace("\\", "/")
        try:
            sftp.mkdir(remote_dir)
        except Exception:
            pass
        for f in files:
            local_file = os.path.join(root, f)
            remote_file = f"{remote_dir}/{f}"
            sftp.put(local_file, remote_file)
            
    sftp.close()
    
    # 4. Deploy Nginx
    run_ssh(client, "sudo mkdir -p /var/www/pond_planner/frontend /var/cache/nginx/pond")
    run_ssh(client, "sudo rm -rf /var/www/pond_planner/frontend/*")
    run_ssh(client, "sudo cp -r /home/student/AI-Pond-Planner/frontend/* /var/www/pond_planner/frontend/")
    run_ssh(client, "sudo chmod -R 755 /var/www/pond_planner")
    run_ssh(client, "sudo cp /home/student/AI-Pond-Planner/deploy/nginx_lb.conf /etc/nginx/nginx.conf")
    
    # 5. Test & Restart Nginx
    run_ssh(client, "sudo nginx -t")
    run_ssh(client, "sudo service nginx restart || sudo service nginx start || sudo nginx")
    
    time.sleep(2)
    
    # 6. Verify
    log("=== VERIFICATION ===")
    run_ssh(client, "ss -tulpn | grep -E ':80|:4217'")
    run_ssh(client, "curl -i http://127.0.0.1:4217/ui/")
    run_ssh(client, "curl -i http://127.0.0.1:4217/health")
    
    client.close()
    log("Done!")

if __name__ == "__main__":
    main()
