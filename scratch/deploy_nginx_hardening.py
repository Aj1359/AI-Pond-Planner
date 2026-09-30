import subprocess

nginx_conf = """
user www-data;
worker_processes auto;
pid /run/nginx.pid;
include /etc/nginx/modules-enabled/*.conf;

events {
    worker_connections 1024;
}

http {
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    
    # Observability Log Format
    log_format pond '$remote_addr [$time_local] "$request" $status '
                    'rt=$request_time urt=$upstream_response_time '
                    'ua=$upstream_addr cache=$upstream_cache_status';
    access_log /var/log/nginx/pond.log pond;
    error_log /var/log/nginx/error.log;

    # Gzip Settings
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript application/geo+json;

    # Proxy Cache Path
    proxy_cache_path /var/cache/nginx/pond levels=1:2 keys_zone=pond_cache:20m max_size=500m inactive=24h use_temp_path=off;

    # Upstream Hardening
    upstream pond_backends {
        zone pond_backends 64k;
        least_conn;
        server 172.17.0.19:4000 max_fails=3 fail_timeout=10s max_conns=40;
        server 172.17.0.20:4000 max_fails=3 fail_timeout=10s max_conns=40;
        server 172.17.0.21:4001 max_fails=3 fail_timeout=10s max_conns=40;
        keepalive 16;
        keepalive_requests 1000;
        keepalive_timeout 60s;
    }

    server {
        listen 4217;
        server_name _;

        # Frontend
        location /ui/ {
            alias /var/www/pond_planner/frontend/;
            index index.html;
            try_files $uri $uri/ /ui/index.html;
        }

        # Cache boundaries
        location /api/location/boundary {
            proxy_pass http://pond_backends;
            proxy_http_version 1.1;
            proxy_set_header Connection "";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;

            proxy_cache pond_cache;
            proxy_cache_valid 200 6h;
            proxy_cache_lock on;
            proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
            proxy_cache_background_update on;
            add_header X-Cache $upstream_cache_status;
        }

        # General API
        location /api/ {
            proxy_pass http://pond_backends;
            proxy_http_version 1.1;
            proxy_set_header Connection "";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;

            proxy_connect_timeout 2s;
            proxy_send_timeout 15s;
            proxy_read_timeout 30s;

            proxy_next_upstream error timeout http_502 http_503 http_504;
            proxy_next_upstream_tries 2;
            proxy_next_upstream_timeout 10s;
        }

        location / {
            return 301 /ui/;
        }
    }
}
"""

with open("nginx_lb.conf", "w") as f:
    f.write(nginx_conf)

print("Copying Nginx config to VM1...")
subprocess.run(["scp", "-P", "2217", "nginx_lb.conf", "student@10.1.75.51:~/nginx_lb.conf"])

print("Applying Nginx config and reloading...")
ssh_cmd = 'echo "Adityajha123!" | sudo -S cp ~/nginx_lb.conf /etc/nginx/nginx.conf && echo "Adityajha123!" | sudo -S nginx -t && echo "Adityajha123!" | sudo -S service nginx reload'
subprocess.run(["ssh", "student@10.1.75.51", "-p", "2217", ssh_cmd])
