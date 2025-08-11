# CBZify Docker Deployment Guide

This guide covers production deployment of CBZify using secure, distroless containers.

## 🐳 Container Images

CBZify uses a multi-stage, distroless Docker build for maximum security and minimal attack surface.

### Image Features

✅ **Distroless Base**: Built on `gcr.io/distroless/python3-debian12:nonroot`  
✅ **Rootless Execution**: Runs as non-root user (`nonroot`)  
✅ **Minimal Attack Surface**: No shell, package managers, or unnecessary binaries  
✅ **Multi-Architecture**: Supports `linux/amd64` and `linux/arm64`  
✅ **Vulnerability Scanning**: Automated security scanning with Trivy and Snyk  

## 📦 GitHub Container Registry

Images are automatically built and published to GitHub Container Registry:

```bash
# Pull latest image
docker pull ghcr.io/skgchp/cbzify:latest

# Pull specific version
docker pull ghcr.io/skgchp/cbzify:v1.0.0
```

## 🚀 Quick Start

### Development
```bash
# Run with docker-compose (development)
docker-compose up -d
```

### Production
```bash
# Run with production configuration
docker-compose -f docker-compose.prod.yml up -d
```

### Manual Docker Run
```bash
docker run -d \
  --name cbzify \
  --restart unless-stopped \
  --security-opt no-new-privileges:true \
  -p 8080:8080 \
  -v cbzify-uploads:/app/uploads \
  -v cbzify-downloads:/app/downloads \
  ghcr.io/skgchp/cbzify:latest
```

## 🔒 Security Features

### Container Security
- **Non-root execution**: Runs as `nonroot` user (UID/GID 65532)
- **No shell access**: Distroless image contains no shell or debug tools
- **Read-only filesystem**: Application runs with minimal write permissions
- **Capability dropping**: No additional capabilities granted
- **No new privileges**: `no-new-privileges:true` prevents privilege escalation

### Network Security
- **Non-privileged port**: Uses port 8080 (no root required)
- **Isolated networking**: Custom Docker networks for production
- **Health checks**: Built-in health monitoring

### Resource Limits
```yaml
deploy:
  resources:
    limits:
      memory: 2G      # Maximum memory usage
      cpus: '2.0'     # Maximum CPU cores
    reservations:
      memory: 512M    # Reserved memory
      cpus: '0.5'     # Reserved CPU
```

## 🏗️ Building from Source

### Prerequisites
- Docker with BuildKit enabled
- Multi-platform build support (for ARM64)

### Build Commands
```bash
# Build for current platform
docker build -t cbzify .

# Build for multiple platforms
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t cbzify:latest .

# Build with security scanning
docker build -t cbzify . && \
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy:latest image cbzify:latest
```

## 📊 Monitoring & Observability

### Health Checks
The container includes built-in health checks:
```bash
# Check container health
docker ps
# Look for "healthy" status

# Manual health check
curl http://localhost:8080/status
```

### Logs
```bash
# View container logs
docker logs cbzify

# Follow logs in real-time
docker logs -f cbzify

# View structured logs (JSON)
docker logs cbzify 2>&1 | jq .
```

### Metrics
Monitor these key metrics:
- **Memory usage**: Should stay under 2GB limit
- **CPU usage**: Should be minimal when idle
- **Disk I/O**: Spikes during file conversion
- **Network**: HTTP request patterns

## 🔄 Updates & Maintenance

### Updating
```bash
# Pull latest image
docker pull ghcr.io/skgchp/cbzify:latest

# Recreate container
docker-compose -f docker-compose.prod.yml up -d --force-recreate
```

### Backup
```bash
# Backup volumes
docker run --rm \
  -v cbzify-uploads:/source:ro \
  -v $(pwd):/backup \
  alpine:latest \
  tar czf /backup/cbzify-backup.tar.gz -C /source .
```

### Cleanup
```bash
# Remove old images
docker image prune -a

# Remove unused volumes
docker volume prune

# Clean up everything
docker system prune -a --volumes
```

## 🛡️ Security Best Practices

### Host Security
1. **Keep Docker updated**: Use latest stable Docker version
2. **Limit host access**: Restrict SSH and other services
3. **Use TLS**: Deploy behind reverse proxy with HTTPS
4. **Monitor logs**: Set up centralized logging
5. **Regular updates**: Keep container images updated

### Container Security
1. **Read-only root**: Mount root filesystem as read-only when possible
2. **Secrets management**: Use Docker secrets for sensitive data
3. **Network isolation**: Use custom networks instead of default bridge
4. **Resource limits**: Always set memory and CPU limits
5. **Security scanning**: Regularly scan images for vulnerabilities

### Example Secure Configuration
```yaml
services:
  cbzify:
    image: ghcr.io/skgchp/cbzify:latest
    read_only: true
    tmpfs:
      - /tmp:noexec,nosuid,size=100m
    security_opt:
      - no-new-privileges:true
      - seccomp:unconfined
    cap_drop:
      - ALL
    networks:
      - cbzify-internal
```

## 🔍 Vulnerability Scanning

Images are automatically scanned for vulnerabilities using:
- **Trivy**: Comprehensive vulnerability scanner
- **Snyk**: Commercial-grade security scanning
- **GitHub Security Advisories**: Automated dependency alerts

View scan results in the GitHub Security tab of your repository.

## 📞 Support

For deployment issues:
1. Check container logs: `docker logs cbzify`
2. Verify health status: `curl http://localhost:8080/status`
3. Test file permissions: Ensure volumes are writable
4. Review resource usage: `docker stats cbzify`

## 🚨 Emergency Procedures

### Container Won't Start
```bash
# Check logs
docker logs cbzify

# Test image manually
docker run -it --rm --entrypoint="" \
  ghcr.io/skgchp/cbzify:latest \
  python3 -c "import app; print('OK')"
```

### High Resource Usage
```bash
# Check resource usage
docker stats cbzify

# Restart with lower limits
docker update --memory 1G --cpus 1.0 cbzify
docker restart cbzify
```

### Security Incident
```bash
# Immediately stop container
docker stop cbzify

# Preserve evidence
docker logs cbzify > incident-logs.txt
docker inspect cbzify > incident-config.json

# Rotate secrets and recreate
docker rm cbzify
# Update configuration and restart
```