import paramiko
import os
import time

VM1_HOST = "10.1.75.51"
VM1_PORT = 2217
USERNAME = "student"
PASSWORD = "Adityajha123!"

def log(msg):
    print(str(msg).encode('ascii', errors='replace').decode('ascii'), flush=True)

try:
    # Connect to VM1
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(VM1_HOST, port=VM1_PORT, username=USERNAME, password=PASSWORD, timeout=10)
    
    # Create a python script ON VM1 that connects to VM3 and uploads the file
    vm1_script = """
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("172.17.0.20", username="student", password="Adityajha123!")
sftp = client.open_sftp()
sftp.put("sites.py", "/home/student/pond_planner_backend/app/services/sites.py")
sftp.close()

stdin, stdout, stderr = client.exec_command("pkill -9 -f uvicorn || true; sleep 1; cd ~/pond_planner_backend && nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 4000 --workers 2 > ~/backend.log 2>&1 &")
print(stdout.read().decode())
print(stderr.read().decode())
client.close()
print("Success!")
"""
    
    sftp = client.open_sftp()
    with sftp.file("deploy_to_vm3.py", "w") as f:
        f.write(vm1_script)
    sftp.close()
    
    # Run the script on VM1
    stdin, stdout, stderr = client.exec_command("python3 deploy_to_vm3.py")
    log("OUT: " + stdout.read().decode())
    log("ERR: " + stderr.read().decode())
    
    client.close()
    log("✅ Deployment to VM3 Complete!")
except Exception as e:
    log(f"Error: {e}")
