#!/usr/bin/env python3
"""
CBZify Web Interface
A Flask-based web UI for the CBZify comic converter
"""

import os
import sys
import uuid
import shutil
import tempfile
import zipfile
from pathlib import Path
from datetime import datetime
from threading import Thread
import json

from flask import Flask, render_template, request, jsonify, send_file, session
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename

# Import our existing conversion classes
# Handle both Docker (where comic_converter.py is in same dir) and local dev (where it's in src/)
try:
    # Try Docker path first (comic_converter.py in same directory)
    from comic_converter import ComicConverter, BulkProcessor, ConversionProgress, check_dependencies
except ImportError:
    # Fall back to local development path
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from src.comic_converter import ComicConverter, BulkProcessor, ConversionProgress, check_dependencies

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = 'cbzify-web-interface-secret-key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['DOWNLOAD_FOLDER'] = 'downloads'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024  # 2GB max file size

# Initialize SocketIO for real-time updates
socketio = SocketIO(app, cors_allowed_origins="*")

# Ensure upload and download directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['DOWNLOAD_FOLDER'], exist_ok=True)

# Store active conversions
active_conversions = {}

# Allowed file extensions
ALLOWED_EXTENSIONS = {'.pdf', '.epub'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS

def get_file_size_mb(file_path):
    """Get file size in MB"""
    return os.path.getsize(file_path) / (1024 * 1024)

class WebConversionProgress(ConversionProgress):
    """Extended progress class that emits WebSocket updates"""
    
    def __init__(self, session_id):
        super().__init__()
        self.session_id = session_id
        
    def update(self, current=None, total=None, stage=None):
        super().update(current, total, stage)
        # Emit progress update via WebSocket
        self._emit_progress_update()
        
    def increment(self):
        super().increment()
        # Emit progress update after incrementing
        self._emit_progress_update()
        
    def _emit_progress_update(self):
        """Helper method to emit progress updates via WebSocket"""
        current_val, total_val, stage_val = self.get_status()
        progress_data = {
            'session_id': self.session_id,
            'current': current_val,
            'total': total_val,
            'stage': stage_val,
            'percentage': (current_val / total_val * 100) if total_val > 0 else 0
        }
        print(f"Emitting progress update to room {self.session_id}: {progress_data}")
        socketio.emit('progress_update', progress_data, room=self.session_id)

def convert_file_async(session_id, source_path, dest_path, settings):
    """Convert a file asynchronously with progress updates"""
    try:
        # Apply memory-aware worker scaling for large documents
        requested_workers = settings.get('workers', 4)
        safe_workers = calculate_safe_workers(source_path, requested_workers)
        
        if safe_workers < requested_workers:
            print(f"Memory-aware scaling: reduced workers from {requested_workers} to {safe_workers} for large document")
        
        # Create converter with web-enabled progress tracking
        print(f"Creating converter for {session_id} with {safe_workers} workers")
        converter = ComicConverter(
            source_path=source_path,
            dest_path=dest_path,
            max_workers=safe_workers,
            skip_checks=settings.get('skip_checks', False),
            dpi=settings.get('dpi', 300),
            image_format=settings.get('format', 'png'),
            quality=settings.get('quality', 95)
        )
        
        # Replace progress tracker with web-enabled version
        converter.progress = WebConversionProgress(session_id)
        
        # Start conversion
        converter.convert()
        
        # Mark conversion as completed (keep in active_conversions for download)
        if session_id in active_conversions:
            active_conversions[session_id]['status'] = 'completed'
        
        # Notify completion
        file_size = get_file_size_mb(dest_path)
        conversion_info = active_conversions.get(session_id, {})
        display_name = conversion_info.get('display_filename', Path(dest_path).name)
        
        socketio.emit('conversion_complete', {
            'session_id': session_id,
            'success': True,
            'filename': display_name,
            'size_mb': round(file_size, 2)
        }, room=session_id)
        
    except Exception as e:
        # Notify error
        socketio.emit('conversion_error', {
            'session_id': session_id,
            'error': str(e)
        }, room=session_id)
        
        # Clean up failed conversions only
        if session_id in active_conversions:
            del active_conversions[session_id]

@app.route('/')
def index():
    """Main interface"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    """Handle file uploads"""
    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400
    
    files = request.files.getlist('files')
    settings = {
        'dpi': int(request.form.get('dpi', 300)),
        'format': request.form.get('format', 'png'),
        'quality': int(request.form.get('quality', 95)),
        'workers': int(request.form.get('workers', 4)),
        'skip_checks': request.form.get('skip_checks') == 'true'
    }
    
    # Validate settings
    if not (50 <= settings['dpi'] <= 600):
        return jsonify({'error': 'DPI must be between 50 and 600'}), 400
    if not (1 <= settings['quality'] <= 100):
        return jsonify({'error': 'Quality must be between 1 and 100'}), 400
    if not (1 <= settings['workers'] <= 6):
        return jsonify({'error': 'Workers must be between 1 and 6 for container environments'}), 400
    
    print(f"Upload settings: {settings['workers']} workers, {settings['dpi']} DPI, {settings['format']} format, quality {settings['quality']}, skip_checks: {settings['skip_checks']}")
    
    uploaded_files = []
    errors = []
    
    for file in files:
        if file.filename == '':
            continue
            
        if file and allowed_file(file.filename):
            try:
                # Generate unique session ID for this conversion
                session_id = str(uuid.uuid4())
                
                # Secure filename and preserve original name
                original_filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                # Use session ID for internal storage but preserve original name for output
                internal_filename = f"{timestamp}_{session_id[:8]}_{original_filename}"
                
                # Save uploaded file with internal name
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], internal_filename)
                file.save(upload_path)
                
                # Prepare output path - use original filename for CBZ
                output_filename = Path(original_filename).stem + '.cbz'
                internal_output_path = os.path.join(app.config['DOWNLOAD_FOLDER'], f"{timestamp}_{session_id[:8]}_{output_filename}")
                
                # Store both internal and display paths
                display_filename = output_filename
                
                # Store conversion info
                active_conversions[session_id] = {
                    'source': upload_path,
                    'dest': internal_output_path,
                    'original_filename': original_filename,
                    'output_filename': output_filename,
                    'display_filename': display_filename,
                    'settings': settings,
                    'status': 'queued'
                }
                
                uploaded_files.append({
                    'session_id': session_id,
                    'filename': original_filename,
                    'size_mb': round(get_file_size_mb(upload_path), 2)
                })
                
            except Exception as e:
                errors.append(f"Error uploading {file.filename}: {str(e)}")
        else:
            errors.append(f"File {file.filename} is not supported (only PDF and EPUB allowed)")
    
    return jsonify({
        'uploaded_files': uploaded_files,
        'errors': errors
    })

@app.route('/convert/<session_id>', methods=['POST'])
def start_conversion(session_id):
    """Start conversion for a specific file"""
    if session_id not in active_conversions:
        return jsonify({'error': 'Conversion not found'}), 404
    
    conversion_info = active_conversions[session_id]
    if conversion_info['status'] != 'queued':
        return jsonify({'error': 'Conversion already in progress'}), 400
    
    conversion_info['status'] = 'converting'
    
    # Start conversion in background thread
    thread = Thread(target=convert_file_async, args=(
        session_id,
        conversion_info['source'],
        conversion_info['dest'],
        conversion_info['settings']
    ))
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'started'})

@app.route('/download/<session_id>')
def download_file(session_id):
    """Download converted file"""
    print(f"Download request for session: {session_id}")
    print(f"Active conversions: {list(active_conversions.keys())}")
    
    if session_id not in active_conversions:
        return jsonify({'error': 'File not found'}), 404
    
    conversion_info = active_conversions[session_id]
    output_path = conversion_info['dest']
    print(f"Looking for file: {output_path}")
    print(f"File exists: {os.path.exists(output_path)}")
    
    if not os.path.exists(output_path):
        print(f"File not found at path: {output_path}")
        return jsonify({'error': 'Converted file not ready'}), 404
    
    try:
        response = send_file(
            output_path,
            as_attachment=True,
            download_name=conversion_info.get('display_filename', conversion_info['output_filename']),
            mimetype='application/zip'
        )
        
        # Clean up successful downloads to prevent memory growth
        # Only remove completed conversions after successful download
        if conversion_info.get('status') == 'completed':
            del active_conversions[session_id]
            print(f"Cleaned up completed conversion: {session_id}")
        
        return response
        
    except Exception as e:
        print(f"Download error: {e}")
        return jsonify({'error': 'Download failed'}), 500

@app.route('/status')
def get_status():
    """Get status of all conversions"""
    status_info = {}
    for session_id, info in active_conversions.items():
        status_info[session_id] = {
            'filename': info['original_filename'],
            'status': info['status'],
            'ready_for_download': os.path.exists(info['dest']) if 'dest' in info else False
        }
    return jsonify(status_info)

@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection"""
    print(f"Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection"""
    print(f"Client disconnected: {request.sid}")

@socketio.on('join_session')
def handle_join_session(data):
    """Join a conversion session for progress updates"""
    session_id = data.get('session_id')
    print(f"Client {request.sid} joining session: {session_id}")
    if session_id:
        # Join the room for this conversion session
        from flask_socketio import join_room
        join_room(session_id)
        print(f"Client {request.sid} joined room: {session_id}")
        emit('joined_session', {'session_id': session_id})

def calculate_safe_workers(source_path, requested_workers):
    """Calculate memory-safe worker count based on document size"""
    try:
        # Import here to avoid circular imports and handle missing dependencies
        import fitz
        
        # Get document info
        doc = fitz.open(source_path)
        page_count = len(doc)
        doc.close()
        
        # Memory-aware scaling rules for containers:
        # - Each PDF page rendering uses ~50-200MB RAM
        # - PNG format uses more memory than JPEG
        # - Container memory limits are typically 512MB-4GB
        
        # Conservative scaling based on page count
        if page_count <= 20:
            # Small documents: allow full worker count
            return min(requested_workers, 6)
        elif page_count <= 50:
            # Medium documents: cap at 4 workers
            return min(requested_workers, 4)
        elif page_count <= 100:
            # Large documents: cap at 3 workers
            return min(requested_workers, 3)
        else:
            # Very large documents: cap at 2 workers to prevent OOM
            return min(requested_workers, 2)
            
    except Exception as e:
        print(f"Warning: Could not analyze document for worker scaling: {e}")
        # If we can't analyze, be conservative
        return min(requested_workers, 3)

def cleanup_old_files():
    """Clean up old upload and download files"""
    # This could be run periodically to clean up old files
    pass

def cleanup_old_sessions():
    """Clean up old completed sessions to prevent memory growth"""
    from datetime import datetime, timedelta
    
    # Remove completed sessions older than 1 hour
    cutoff_time = datetime.now() - timedelta(hours=1)
    sessions_to_remove = []
    
    for session_id, info in active_conversions.items():
        if info.get('status') == 'completed':
            # If we stored creation time, we could check it
            # For now, just clean up if we have too many completed sessions
            sessions_to_remove.append(session_id)
    
    # Keep only the 10 most recent completed sessions
    if len(sessions_to_remove) > 10:
        for session_id in sessions_to_remove[:-10]:
            del active_conversions[session_id]
            print(f"Auto-cleaned old completed session: {session_id}")

if __name__ == '__main__':
    # Check dependencies
    try:
        check_dependencies()
        print("✓ All dependencies available")
    except SystemExit:
        print("✗ Missing dependencies. Please install: pip install -r requirements.txt")
        sys.exit(1)
    
    print("🚀 Starting CBZify Web Interface...")
    print("📁 Upload folder:", os.path.abspath(app.config['UPLOAD_FOLDER']))
    print("📁 Download folder:", os.path.abspath(app.config['DOWNLOAD_FOLDER']))
    print("🌐 Open your browser to: http://localhost:8080")
    
    # Run the app
    socketio.run(app, debug=True, host='0.0.0.0', port=8080, allow_unsafe_werkzeug=True)