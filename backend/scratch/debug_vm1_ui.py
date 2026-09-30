import paramiko

HOST = "10.1.75.51"
PORT = 2217
USERNAME = "student"
PASSWORD = "Adityajha123!"

def run():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USERNAME, password=PASSWORD, timeout=10)
    
    cmds = [
        "sudo tail -n 25 /var/log/nginx/pond_access.log",
        "sudo tail -n 25 /var/log/nginx/access.log",
        "sudo iptables -L -n -v",
        "curl -i http://localhost:4000/ui/",
        "curl -i http://localhost:4000/health",
        "curl -i http://172.17.0.19:4000/health",
        "curl -i http://10.1.75.51:4217/ui/"
    ]
    
    for cmd in cmds:
        print(f"\n==================== RUNNING: {cmd} ====================")
        stdin, stdout, stderr = client.exec_command(cmd, get_pty=True)
        out = stdout.read().decode('utf-8', errors='ignore')
        err = stderr.read().decode('utf-8', errors='ignore')
        out_str = (out + err).encode('ascii', errors='replace').decode('ascii')
        print(out_str[:1500])
        
    client.close()

if __name__ == "__main__":
    run()
