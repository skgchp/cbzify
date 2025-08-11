# CBZify Developer Documentation 🛠️

> **Development guide for CBZify - Comic converter with intelligent text preservation**

This document provides comprehensive guidance for developers who want to fork, extend,  or understand the CBZify codebase.

## 📁 Project Structure

```
cbzify/
├── 📄 README.md              # User documentation
├── 📄 DEVELOPERS.md          # This file - developer guide
├── 📄 CLAUDE.md              # AI assistant context file
├── 📄 requirements.txt       # Core dependencies
├── 📄 LICENCE.md             # AGPL-3.0 license
│
├── 📂 src/                   # Core application
│   └── 📄 comic_converter.py  # Main conversion engine
│
├── 📂 web/                   # Web interface
│   ├── 📄 app.py             # Flask web application
│   ├── 📄 requirements-web.txt # Web-specific dependencies
│   ├── 📂 templates/         # HTML templates
│   │   └── 📄 index.html
│   └── 📂 static/           # CSS, JavaScript, assets
│       ├── 📂 css/style.css  # Accessible styles
│       └── 📂 js/app.js      # Frontend application
│
├── 📂 docker/                # Docker infrastructure
│   ├── 📄 Dockerfile         # Production distroless container
│   ├── 📄 docker-compose.yml # Development setup
│   ├── 📄 docker-compose.prod.yml # Production configuration
│   ├── 📄 DOCKER.md         # Deployment guide
│   └── 📄 SECURITY.md       # Security documentation
│
├── 📂 docs/                 # Documentation
│   ├── 📄 github-setup.md   # Repository setup guide
│   ├── 📄 spec.md           # Original requirements
│   ├── 📄 issue.md          # Text preservation problem docs
│   └── 📄 to-do.md          # Development task list
│
├── 📂 tests/                # Test suite
│   ├── 📄 test_comic_converter.py
│   ├── 📄 test_integration.py
│   └── 📄 test_performance.py
│
└── 📂 .github/workflows/    # CI/CD pipelines
    ├── 📄 build-and-publish.yml # Container builds (release-driven)
    └── 📄 test.yml             # Test automation
```

## 🚀 Development Setup

### Prerequisites

- Python 3.9+
- Docker (for web development)
- Git

### Local Development Environment

```bash
# Clone repository
git clone https://github.com/skgchp/cbzify.git
cd cbzify

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install core dependencies
pip install -r requirements.txt

# Install web dependencies
pip install -r web/requirements-web.txt

# Install development dependencies (when available)
pip install -r requirements-dev.txt

# Verify CLI functionality
python src/comic_converter.py --help

# Run web development server
cd web && python app.py
```

### Docker Development

```bash
# Build development image (from docker directory)
cd docker
docker-compose build

# Start development services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Or using specific compose file
docker-compose -f docker/docker-compose.yml up -d
```

## 🏗️ Architecture Overview

### Core Components

**ComicConverter Class** (`src/comic_converter.py`)
- Main conversion engine with intelligent PDF analysis
- Handles both PDF and EPUB processing
- Configurable output formats and quality settings
- Multi-threaded processing with progress tracking

**Web Interface** (`web/app.py`)
- Flask-based web application with SocketIO for real-time updates
- Drag-and-drop file upload with 2GB file support
- Accessible, responsive design
- WebSocket-based progress tracking

**Docker Infrastructure** (`Dockerfile`, `docker-compose.yml`)
- Multi-stage production builds
- Security-hardened containers with non-root execution
- Development and production configurations

### Key Design Patterns

**Smart PDF Processing**
```python
def analyze_pdf_content(self, pages_to_check=3):
    """
    Analyzes PDF content structure to determine optimal conversion method:
    - DCT image detection for lossless extraction
    - Text content detection to preserve overlays
    - Early exit optimization for performance
    """
```

**Progress Tracking**
```python
class ConversionProgress:
    """
    Thread-safe progress tracking with WebSocket integration
    - Real-time updates via SocketIO
    - Stage-based progress reporting
    - Concurrent access protection
    """
```

**Library Compatibility**
```python
# Handle different EbookLib versions gracefully
try:
    media_type = item.get_media_type()  # Newer versions
except AttributeError:
    media_type = getattr(item, 'media_type', None)  # Older versions
```

## 🧪 Testing

### Manual Testing

```bash
# Test CLI functionality
python src/comic_converter.py --help

# Test syntax without dependencies
python3 -m py_compile src/comic_converter.py

# Test web interface
cd web && python app.py
# Access http://localhost:8080
```

### Unit Tests (To Be Implemented)

```bash
# Install test dependencies  
pip install -r requirements-dev.txt

# Run unit tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=src --cov-report=term-missing
```

### Docker Testing

```bash
# Build and test Docker image (using docker directory)
docker build -t cbzify:test -f docker/Dockerfile .
docker run -p 8080:8080 cbzify:test

# Test health endpoint
curl http://localhost:8080/status
```

## 🔧 Development Guidelines

### Code Style

- Follow PEP 8 Python style guidelines
- Use type hints where appropriate
- Document complex algorithms and business logic
- Maintain backward compatibility for public APIs

### Error Handling

- Use specific exception types
- Provide user-friendly error messages
- Implement graceful degradation
- Log errors for debugging

### Security Considerations

- Validate all user inputs
- Use secure file handling practices
- Implement proper authentication for production deployments
- Follow Docker security best practices

### Performance Optimization

- Profile code before optimizing
- Use multi-threading appropriately
- Implement caching where beneficial
- Monitor memory usage for large files

## 🔄 CI/CD Pipeline

### GitHub Actions Workflow

The project uses **release-driven** automated CI/CD with the following stages:

1. **Build**: Multi-platform Docker builds (AMD64, ARM64) on releases only
2. **Test**: Syntax validation and basic functionality tests on PRs
3. **Security**: Vulnerability scanning with Trivy and Snyk
4. **Publish**: Push to GitHub Container Registry for releases
5. **Release**: Automated versioning and container tagging

### Workflow Configuration

```yaml
# .github/workflows/build-and-publish.yml
name: Build and Publish Container

# Release-driven: Only builds containers on releases, not every commit
on:
  release:
    types: [ published, prereleased ]
  push:
    tags: [ 'v*' ]
  workflow_dispatch:
  pull_request:
    branches: [ main ]
```

**Key Features:**
- 🏷️ **Release-driven builds**: Containers only built for stable releases
- 🔒 **Security-first**: Distroless containers with vulnerability scanning
- 🌐 **Multi-architecture**: AMD64 and ARM64 support
- 📋 **Smart tagging**: Semantic versioning with multiple tag formats

## 📚 API Documentation

### CLI Interface

```bash
python src/comic_converter.py [OPTIONS] SOURCE DESTINATION

Options:
  --workers INTEGER    Number of worker threads (default: 4, CLI: 1-16, Web: 1-6)
  --dpi INTEGER       Output resolution 50-600 (default: 300)
  --format [png|jpg|jpeg|webp]  Image format (default: png)
  --quality INTEGER   JPEG/WebP quality 1-100 (default: 95)
  --skip-checks       Skip content analysis (consistent performance)
  --fast              [DEPRECATED] Use --skip-checks instead
  --skip-existing     Skip existing files in bulk mode
```

### Web API Endpoints

```python
# File upload
POST /upload
Content-Type: multipart/form-data

# Start conversion  
POST /convert/<session_id>

# Download result
GET /download/<session_id>

# Status check
GET /status
```

### WebSocket Events

```javascript
// Join conversion session
socket.emit('join_session', {session_id: 'uuid'})

// Progress updates
socket.on('progress_update', (data) => {
    // data.percentage, data.stage, etc.
})

// Conversion complete
socket.on('conversion_complete', (data) => {
    // data.filename, data.size_mb, etc.
})
```

## 🐛 Debugging

### Common Development Issues

**Import Errors**
- Ensure virtual environment is activated
- Check PYTHONPATH includes src/ directory
- Verify all dependencies are installed

**Docker Build Issues**
- Clear Docker cache: `docker system prune`
- Check Dockerfile syntax
- Verify file paths exist

**Web Interface Issues**
- Check Flask debug logs
- Verify template paths
- Test WebSocket connections

### Debug Logging

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Performance Profiling

```python
import cProfile
cProfile.run('conversion_function()')
```

## 📦 Dependency Management

### Core Dependencies (`requirements.txt`)

- **PyMuPDF**: PDF processing and rendering
- **EbookLib**: EPUB file handling  
- **Pillow**: Image processing and format conversion

### Web Dependencies (`web/requirements-web.txt`)

- **Flask**: Web framework
- **Flask-SocketIO**: Real-time WebSocket communication
- **Werkzeug**: WSGI utilities
- **Gunicorn**: Production WSGI server

### Development Dependencies (`requirements-dev.txt`)

- **pytest**: Testing framework
- **pytest-cov**: Code coverage
- **black**: Code formatting
- **flake8**: Linting
- **mypy**: Type checking

## 🔐 Security Considerations

### Input Validation

- File type verification
- Size limits enforcement  
- Path traversal prevention
- Content sanitization

### Container Security

- Non-root user execution
- Minimal base images
- Vulnerability scanning
- Secret management

### Web Security

- CSRF protection
- Input sanitization
- Secure headers
- Rate limiting