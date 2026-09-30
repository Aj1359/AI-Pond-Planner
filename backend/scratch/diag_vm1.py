import paramiko

HOST = "10.1.75.51"
USERNAME = "student"
PASSWORD = "Adityajha123!"

def ssh(port, cmd):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(HOST, port=port, username=USERNAME, password=PASSWORD, timeout=10)
        stdin, stdout, stderr = client.exec_command(cmd, get_pty=True)
        out = stdout.read().decode('utf-8', errors='ignore')
        return out.encode('ascii', errors='replace').decode('ascii')
    except Exception as e:
        return f"ERROR: {e}"
    finally:
        client.close()

print("=== VM1 Nginx config (live on server) ===")
print(ssh(2217, "sudo cat /etc/nginx/nginx.conf"))

print("\n=== VM1 Nginx status ===")
print(ssh(2217, "sudo service nginx status"))

print("\n=== VM1 listening ports ===")
print(ssh(2217, "sudo ss -tulpn"))

print("\n=== /var/www/pond_planner/frontend/ files ===")
print(ssh(2217, "ls -la /var/www/pond_planner/frontend/"))

print("\n=== curl http://127.0.0.1:4217/ui/ ===")
print(ssh(2217, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:4217/ui/"))

print("\n=== curl http://127.0.0.1:80/ui/ ===")
print(ssh(2217, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:80/ui/"))

print("\n=== Nginx error log ===")
print(ssh(2217, "sudo tail -20 /var/log/nginx/pond_error.log"))

print("\n=== Backend VM2 health ===")
print(ssh(2218, "curl -s http://localhost:4000/health | head -c 200"))

print("\n=== Backend VM3 health ===")
print(ssh(2219, "curl -s http://localhost:4000/health | head -c 200"))

print("\n=== Backend VM4 health ===")
print(ssh(2220, "curl -s http://localhost:4000/health | head -c 200"))
