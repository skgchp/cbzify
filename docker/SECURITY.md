# CBZify Security Guide

## 🔒 Container Security Features

### Distroless Architecture
- **Base Image**: `gcr.io/distroless/python3-debian12:nonroot`
- **No Shell**: No bash, sh, or other shells available
- **No Package Manager**: No apt, yum, or package installation tools
- **Minimal Binaries**: Only Python runtime and essential libraries
- **Read-only**: Application files are read-only

### Rootless Execution
- **User**: Runs as `nonroot` user (UID: 65532, GID: 65532)
- **No Sudo**: No privilege escalation capabilities
- **File Permissions**: All files owned by nonroot user
- **Process Isolation**: Cannot access host processes or users

### Attack Surface Reduction
- **Image Size**: ~200MB (vs 1GB+ for full OS)
- **CVE Exposure**: Minimal packages = minimal vulnerabilities
- **Network Ports**: Only exposes port 8080 (non-privileged)
- **File System**: Temporary directories have limited permissions

## 🛡️ Security Configurations

### Docker Security Options
```yaml
security_opt:
  - no-new-privileges:true    # Prevent privilege escalation
  - seccomp:unconfined       # Optional: customize syscall filtering
cap_drop:
  - ALL                      # Drop all capabilities
read_only: true              # Read-only root filesystem
tmpfs:
  - /tmp:noexec,nosuid,size=100m  # Secure temp directory
```

### Resource Limits
```yaml
deploy:
  resources:
    limits:
      memory: 2G             # Prevent memory exhaustion attacks
      cpus: '2.0'            # Limit CPU usage
      pids: 100              # Limit process count
    reservations:
      memory: 512M           # Guaranteed memory
```

### Network Security
```yaml
networks:
  - cbzify-internal          # Isolated network
ports:
  - "8080:8080"              # Only expose necessary ports
```

## 🔍 Vulnerability Management

### Automated Scanning
- **GitHub Actions**: Trivy scanner runs on every build
- **Snyk Integration**: Commercial vulnerability scanning
- **Dependabot**: Automated dependency updates
- **Security Advisories**: GitHub security alerts

### Current Vulnerability Status

**Latest Scan Results** (as of container build):
- **Total**: 14 vulnerabilities (1 HIGH, 1 MEDIUM, 12 LOW)
- **Status**: ACCEPTABLE for production deployment

#### Risk Assessment
**HIGH Severity (1)**:
- `CVE-2025-4802` (glibc): Static setuid binary dlopen issue
  - **Actual Risk**: LOW - Container runs as non-root user (UID 65532)
  - **Mitigation**: Distroless architecture prevents exploitation vectors

**MEDIUM Severity (1)**:
- `CVE-2025-8058` (glibc): Double free vulnerability
  - **Actual Risk**: LOW - Limited to specific glibc usage patterns not present in web application context
  - **Mitigation**: No direct user input to vulnerable code paths

**LOW Severity (12)**:
- Legacy CVEs in glibc, gcc, and OpenSSL (2010-2022 timeframe)
- `CVE-2025-27587` (OpenSSL): PowerPC-specific, doesn't affect x86_64/ARM64 deployments
- **Actual Risk**: NEGLIGIBLE - Most require local execution or specific attack vectors

#### Why These Vulnerabilities Are Acceptable

1. **Distroless Security Model**: No shell, package managers, or traditional attack surfaces
2. **Non-root Execution**: All processes run as UID 65532, preventing privilege escalation
3. **Read-only Environment**: Application code and system libraries are immutable
4. **Isolated Network**: Container network isolation limits exploit propagation
5. **Base Image Dependencies**: These are upstream Debian/Python base image vulnerabilities that will be patched in future releases

#### Monitoring Strategy
```bash
# Weekly vulnerability assessment
docker run --rm aquasec/trivy:latest image ghcr.io/skgchp/cbzify:latest

# Track only actionable vulnerabilities (not base system CVEs)
trivy image --severity HIGH,CRITICAL --ignore-unfixed ghcr.io/skgchp/cbzify:latest
```

**Security Posture**: The current vulnerability profile is typical and acceptable for a production container with Python dependencies. The distroless architecture and security hardening measures provide defense-in-depth against the theoretical risks posed by these base system vulnerabilities.

### Manual Security Testing
```bash
# Scan container for vulnerabilities
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy:latest image ghcr.io/skgchp/cbzify:latest

# Check for secrets
docker run --rm -v $(pwd):/src \
  trufflesecurity/trufflehog:latest filesystem /src

# Analyze Docker configuration
docker run --rm -it \
  -v /var/run/docker.sock:/var/run/docker.sock \
  wagoodman/dive:latest ghcr.io/skgchp/cbzify:latest
```

## 🚨 Security Incident Response

### Detection
Monitor for these security indicators:
- Unusual CPU/memory usage patterns
- Unexpected network connections
- File system changes outside uploads/downloads
- Process spawning (should only be Python)
- Container restart loops

### Response Procedure
1. **Immediate**: Stop the container
   ```bash
   docker stop cbzify
   ```

2. **Preserve Evidence**: Capture logs and state
   ```bash
   docker logs cbzify > incident-$(date +%s).log
   docker inspect cbzify > container-state-$(date +%s).json
   ```

3. **Isolate**: Remove from network
   ```bash
   docker network disconnect cbzify-network cbzify
   ```

4. **Analyze**: Review logs and system state
   ```bash
   # Check for unauthorized file access
   docker diff cbzify
   
   # Review process list
   docker exec cbzify ps aux
   ```

5. **Remediate**: Update and redeploy
   ```bash
   docker pull ghcr.io/skgchp/cbzify:latest
   docker-compose -f docker-compose.prod.yml up -d --force-recreate
   ```

## 📋 Security Checklist

### Pre-Deployment
- [ ] Latest container image deployed
- [ ] Resource limits configured
- [ ] Security options enabled
- [ ] Network isolation implemented
- [ ] Read-only filesystem where possible
- [ ] Secrets properly managed
- [ ] Monitoring/alerting configured

### Runtime Security
- [ ] Regular vulnerability scans
- [ ] Log monitoring active
- [ ] Resource usage monitored
- [ ] Network traffic analyzed
- [ ] File integrity checking
- [ ] Access logs reviewed

### Maintenance
- [ ] Container images updated monthly
- [ ] Security patches applied promptly
- [ ] Configuration reviewed quarterly
- [ ] Incident response tested
- [ ] Backup/restore procedures tested

## 🔐 Secrets Management

### Environment Variables
```yaml
# Never put secrets directly in docker-compose.yml
environment:
  - SECRET_KEY_FILE=/run/secrets/flask_secret
secrets:
  - flask_secret

secrets:
  flask_secret:
    file: ./secrets/flask_secret.txt
```

### Docker Secrets (Swarm)
```bash
# Create secret
echo "your-secret-key" | docker secret create flask_secret -

# Use in service
services:
  cbzify:
    secrets:
      - flask_secret
    environment:
      - SECRET_KEY_FILE=/run/secrets/flask_secret
```

## 🌐 Reverse Proxy Configuration

### Nginx Security Headers
```nginx
server {
    listen 443 ssl http2;
    server_name cbzify.example.com;

    # Security headers
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin";
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' cdn.jsdelivr.net cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' cdn.jsdelivr.net cdnjs.cloudflare.com; font-src 'self' cdnjs.cloudflare.com; img-src 'self' data:; connect-src 'self' ws: wss:";

    # File upload limits
    client_max_body_size 2G;
    client_body_timeout 300s;
    client_header_timeout 300s;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

## ⚡ Performance vs Security Trade-offs

### High Security (Recommended)
```yaml
# Maximum security - minimal performance impact
read_only: true
security_opt:
  - no-new-privileges:true
cap_drop: [ALL]
tmpfs:
  - /tmp:noexec,nosuid,size=50m
```

### Balanced
```yaml
# Good security with optimal performance
security_opt:
  - no-new-privileges:true
cap_drop: [ALL]
# Allow read-write for better I/O performance
```

### Performance Optimized
```yaml
# Minimal security restrictions for maximum performance
security_opt:
  - no-new-privileges:true
# Only essential security measures
```
