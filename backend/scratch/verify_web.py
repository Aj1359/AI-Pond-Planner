import urllib.request

try:
    req = urllib.request.urlopen("http://10.1.75.51:4217/ui/", timeout=5)
    print(f"UI Status: {req.getcode()}")
except Exception as e:
    print(f"UI error: {e}")

try:
    req = urllib.request.urlopen("http://10.1.75.51:4217/health", timeout=5)
    print(f"Health Status: {req.getcode()}")
    print(req.read().decode('utf-8'))
except Exception as e:
    print(f"Health error: {e}")
