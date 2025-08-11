// CBZify Web Interface JavaScript

class CBZifyApp {
    constructor() {
        this.socket = io();
        this.uploadQueue = [];
        this.activeConversions = new Map();
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.setupSocketListeners();
        this.setupDropZone();
    }
    
    setupEventListeners() {
        // Browse button
        document.getElementById('browse-btn').addEventListener('click', () => {
            document.getElementById('file-input').click();
        });
        
        // File input change
        document.getElementById('file-input').addEventListener('change', (e) => {
            this.handleFileSelect(e.target.files);
        });
        
        // Convert all button
        document.getElementById('convert-all-btn').addEventListener('click', () => {
            this.convertAllFiles();
        });
        
        // Clear queue button
        document.getElementById('clear-queue-btn').addEventListener('click', () => {
            this.clearQueue();
        });
        
        // Help link
        document.getElementById('help-link').addEventListener('click', (e) => {
            e.preventDefault();
            const helpModal = new bootstrap.Modal(document.getElementById('helpModal'));
            helpModal.show();
        });
        
        // Settings form changes
        document.getElementById('format').addEventListener('change', (e) => {
            const qualityInput = document.getElementById('quality');
            const qualityHelp = qualityInput.nextElementSibling;
            
            if (e.target.value === 'png') {
                qualityInput.disabled = true;
                qualityHelp.textContent = 'PNG is lossless (quality not applicable)';
            } else {
                qualityInput.disabled = false;
                qualityHelp.textContent = 'JPEG/WebP quality (1-100)';
            }
        });
    }
    
    setupSocketListeners() {
        this.socket.on('connect', () => {
            console.log('Connected to server with socket ID:', this.socket.id);
        });
        
        this.socket.on('joined_session', (data) => {
            console.log('Successfully joined session:', data.session_id);
        });
        
        this.socket.on('progress_update', (data) => {
            console.log('Progress update received:', data);
            this.updateProgress(data);
        });
        
        this.socket.on('conversion_complete', (data) => {
            console.log('Conversion complete:', data);
            this.handleConversionComplete(data);
        });
        
        this.socket.on('conversion_error', (data) => {
            console.log('Conversion error:', data);
            this.handleConversionError(data);
        });
        
        this.socket.on('disconnect', () => {
            console.log('Disconnected from server');
        });
    }
    
    setupDropZone() {
        const dropZone = document.getElementById('drop-zone');
        
        // Prevent default drag behaviors
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, this.preventDefaults, false);
            document.body.addEventListener(eventName, this.preventDefaults, false);
        });
        
        // Highlight drop zone when item is dragged over
        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, () => {
                dropZone.classList.add('drag-over');
            }, false);
        });
        
        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, () => {
                dropZone.classList.remove('drag-over');
            }, false);
        });
        
        // Handle dropped files
        dropZone.addEventListener('drop', (e) => {
            const files = e.dataTransfer.files;
            this.handleFileSelect(files);
        }, false);
        
        // Click to browse
        dropZone.addEventListener('click', () => {
            document.getElementById('file-input').click();
        });
        
        // Keyboard navigation support for drop zone
        dropZone.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                document.getElementById('file-input').click();
            }
        });
    }
    
    preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    handleFileSelect(files) {
        const fileArray = Array.from(files);
        const validFiles = fileArray.filter(file => this.isValidFile(file));
        
        if (validFiles.length > 0) {
            this.addFilesToQueue(validFiles);
        }
        
        // Show errors for invalid files
        const invalidFiles = fileArray.filter(file => !this.isValidFile(file));
        if (invalidFiles.length > 0) {
            this.showNotification(
                `Skipped ${invalidFiles.length} unsupported files. Only PDF and EPUB are supported.`,
                'warning'
            );
        }
    }
    
    isValidFile(file) {
        const allowedTypes = ['.pdf', '.epub'];
        const extension = '.' + file.name.split('.').pop().toLowerCase();
        return allowedTypes.includes(extension) && file.size <= 2 * 1024 * 1024 * 1024; // 2GB
    }
    
    async addFilesToQueue(files) {
        const formData = new FormData();
        const settingsForm = document.getElementById('settings-form');
        const formDataSettings = new FormData(settingsForm);
        
        // Add files to form data
        files.forEach(file => formData.append('files', file));
        
        // Add settings to form data
        for (let [key, value] of formDataSettings.entries()) {
            if (key === 'skip_checks') {
                formData.append(key, document.getElementById('skip_checks').checked);
            } else {
                formData.append(key, value);
            }
        }
        
        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            
            if (response.ok) {
                result.uploaded_files.forEach(fileInfo => {
                    this.uploadQueue.push(fileInfo);
                    this.renderQueueItem(fileInfo);
                });
                
                this.showUploadQueue();
                
                if (result.errors.length > 0) {
                    result.errors.forEach(error => {
                        this.showNotification(error, 'warning');
                    });
                }
            } else {
                this.showNotification(result.error || 'Upload failed', 'error');
            }
        } catch (error) {
            this.showNotification('Upload failed: ' + error.message, 'error');
        }
    }
    
    renderQueueItem(fileInfo) {
        const queueContainer = document.getElementById('upload-queue');
        const fileExtension = fileInfo.filename.split('.').pop().toLowerCase();
        
        const queueItem = document.createElement('div');
        queueItem.className = 'file-queue-item fade-in';
        queueItem.id = `queue-item-${fileInfo.session_id}`;
        
        queueItem.innerHTML = `
            <div class="d-flex align-items-center" role="listitem" aria-label="File: ${fileInfo.filename}">
                <div class="file-icon ${fileExtension}" aria-hidden="true">
                    <i class="fas fa-file-${fileExtension === 'pdf' ? 'pdf' : 'lines'}"></i>
                </div>
                <div class="flex-grow-1">
                    <h3 class="h6 mb-1">${fileInfo.filename}</h3>
                    <div class="text-muted">${fileInfo.size_mb} MB</div>
                    <div class="progress mt-2" style="display: none;" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
                        <div class="progress-bar" style="width: 0%">
                            <span class="sr-only">0% complete</span>
                        </div>
                    </div>
                    <div class="conversion-status mt-2" style="display: none;" aria-live="polite">
                        <span class="text-muted">Ready for conversion</span>
                    </div>
                </div>
                <div class="text-end">
                    <button class="btn btn-primary btn-sm convert-btn" 
                            onclick="app.convertFile('${fileInfo.session_id}')"
                            aria-label="Convert ${fileInfo.filename}">
                        <i class="fas fa-play me-1" aria-hidden="true"></i>Convert
                    </button>
                    <button class="btn btn-outline-danger btn-sm ms-1 remove-btn"
                            onclick="app.removeFromQueue('${fileInfo.session_id}')"
                            aria-label="Remove ${fileInfo.filename} from queue">
                        <i class="fas fa-times" aria-hidden="true"></i>
                        <span class="sr-only">Remove</span>
                    </button>
                </div>
            </div>
        `;
        
        queueContainer.appendChild(queueItem);
    }
    
    showUploadQueue() {
        document.getElementById('upload-queue-container').style.display = 'block';
    }
    
    async convertFile(sessionId) {
        try {
            const response = await fetch(`/convert/${sessionId}`, {
                method: 'POST'
            });
            
            if (response.ok) {
                // Join the session for real-time updates
                console.log('Joining session for progress updates:', sessionId);
                this.socket.emit('join_session', { session_id: sessionId });
                
                const queueItem = document.getElementById(`queue-item-${sessionId}`);
                queueItem.classList.add('converting');
                
                const convertBtn = queueItem.querySelector('.convert-btn');
                convertBtn.disabled = true;
                convertBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Converting';
                
                const progressBar = queueItem.querySelector('.progress');
                const statusDiv = queueItem.querySelector('.conversion-status');
                progressBar.style.display = 'block';
                statusDiv.style.display = 'block';
                
                this.activeConversions.set(sessionId, { queueItem, startTime: Date.now() });
            } else {
                const result = await response.json();
                this.showNotification(result.error || 'Conversion failed to start', 'error');
            }
        } catch (error) {
            this.showNotification('Conversion failed: ' + error.message, 'error');
        }
    }
    
    updateProgress(data) {
        const sessionId = data.session_id;
        if (!this.activeConversions.has(sessionId)) return;
        
        const { queueItem } = this.activeConversions.get(sessionId);
        const progressBar = queueItem.querySelector('.progress-bar');
        const statusDiv = queueItem.querySelector('.conversion-status span');
        
        progressBar.style.width = `${data.percentage}%`;
        progressBar.textContent = `${Math.round(data.percentage)}%`;
        progressBar.setAttribute('aria-valuenow', Math.round(data.percentage));
        
        if (statusDiv) {
            statusDiv.textContent = `${data.stage} (${data.current}/${data.total})`;
            statusDiv.className = 'text-info'; // Update color to show active progress
        }
    }
    
    handleConversionComplete(data) {
        const sessionId = data.session_id;
        if (!sessionId || !this.activeConversions.has(sessionId)) return;
        
        const { queueItem } = this.activeConversions.get(sessionId);
        queueItem.classList.remove('converting');
        queueItem.classList.add('completed');
        
        const convertBtn = queueItem.querySelector('.convert-btn');
        convertBtn.innerHTML = `<i class="fas fa-download me-1"></i>Download`;
        convertBtn.className = 'btn btn-success btn-sm ms-2';
        convertBtn.disabled = false;
        convertBtn.onclick = () => this.downloadFile(sessionId);
        
        const progressBar = queueItem.querySelector('.progress-bar');
        progressBar.style.width = '100%';
        progressBar.className = 'progress-bar bg-success';
        
        const statusDiv = queueItem.querySelector('.conversion-status span');
        if (statusDiv) {
            statusDiv.textContent = `Completed • ${data.size_mb} MB • ${data.filename}`;
            statusDiv.className = 'text-success';
        }
        
        // Debug: Log session ID for download troubleshooting
        console.log(`Conversion completed for session ${sessionId}, file: ${data.filename}`);
        
        this.activeConversions.delete(sessionId);
        this.showResultsSection();
        
        this.showNotification(`✓ ${data.filename} converted successfully`, 'success');
    }
    
    handleConversionError(data) {
        const sessionId = data.session_id;
        if (!sessionId || !this.activeConversions.has(sessionId)) return;
        
        const { queueItem } = this.activeConversions.get(sessionId);
        queueItem.classList.remove('converting');
        queueItem.classList.add('error');
        
        const convertBtn = queueItem.querySelector('.convert-btn');
        convertBtn.innerHTML = '<i class="fas fa-redo me-1"></i>Retry';
        convertBtn.className = 'btn btn-warning btn-sm';
        convertBtn.disabled = false;
        // Update onclick to retry the same session
        convertBtn.onclick = () => this.retryConversion(sessionId);
        
        const statusDiv = queueItem.querySelector('.conversion-status span');
        if (statusDiv) {
            statusDiv.textContent = `Error: ${data.error}`;
            statusDiv.className = 'text-danger';
        }
        
        this.activeConversions.delete(sessionId);
        
        this.showNotification(`✗ Conversion failed: ${data.error}`, 'error');
    }
    
    retryConversion(sessionId) {
        // Reset the queue item to queued state
        const queueItem = document.getElementById(`queue-item-${sessionId}`);
        if (!queueItem) return;
        
        // Reset visual state
        queueItem.classList.remove('error');
        
        const convertBtn = queueItem.querySelector('.convert-btn');
        convertBtn.innerHTML = '<i class="fas fa-play me-1"></i>Convert';
        convertBtn.className = 'btn btn-primary btn-sm';
        convertBtn.onclick = () => this.convertFile(sessionId);
        
        const progressBar = queueItem.querySelector('.progress');
        const progressBarInner = queueItem.querySelector('.progress-bar');
        const statusDiv = queueItem.querySelector('.conversion-status span');
        
        // Reset progress
        progressBar.style.display = 'none';
        progressBarInner.style.width = '0%';
        progressBarInner.textContent = '0%';
        progressBarInner.className = 'progress-bar';
        
        // Reset status
        if (statusDiv) {
            statusDiv.textContent = 'Ready for conversion';
            statusDiv.className = 'text-muted';
        }
        
        // Show user feedback
        this.showNotification('Conversion reset. Click Convert to try again.', 'info');
    }

    downloadFile(sessionId) {
        window.open(`/download/${sessionId}`, '_blank');
    }
    
    removeFromQueue(sessionId) {
        const queueItem = document.getElementById(`queue-item-${sessionId}`);
        if (queueItem) {
            queueItem.remove();
        }
        
        this.uploadQueue = this.uploadQueue.filter(item => item.session_id !== sessionId);
        
        if (this.uploadQueue.length === 0) {
            document.getElementById('upload-queue-container').style.display = 'none';
        }
    }
    
    convertAllFiles() {
        this.uploadQueue.forEach(fileInfo => {
            const queueItem = document.getElementById(`queue-item-${fileInfo.session_id}`);
            const convertBtn = queueItem.querySelector('.convert-btn');
            
            // Only convert if button still shows "Convert" (not already converting or completed)
            if (convertBtn && convertBtn.textContent.trim().startsWith('Convert')) {
                this.convertFile(fileInfo.session_id);
            }
        });
    }
    
    clearQueue() {
        if (confirm('Are you sure you want to clear the entire queue?')) {
            this.uploadQueue.forEach(fileInfo => {
                this.removeFromQueue(fileInfo.session_id);
            });
            
            this.uploadQueue = [];
            document.getElementById('upload-queue-container').style.display = 'none';
        }
    }
    
    showResultsSection() {
        document.getElementById('results-container').style.display = 'block';
    }
    
    announceToScreenReader(message) {
        // Announce message to screen readers
        const announcements = document.getElementById('status-announcements');
        if (announcements) {
            announcements.textContent = message;
        }
    }

    showNotification(message, type = 'info') {
        // Announce to screen readers
        this.announceToScreenReader(message);
        
        // Create Bootstrap toast notification
        const toastContainer = this.getOrCreateToastContainer();
        
        const toastElement = document.createElement('div');
        toastElement.className = `toast align-items-center text-white bg-${this.getBootstrapColor(type)} border-0`;
        toastElement.setAttribute('role', 'alert');
        toastElement.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" 
                        data-bs-dismiss="toast"></button>
            </div>
        `;
        
        toastContainer.appendChild(toastElement);
        
        const toast = new bootstrap.Toast(toastElement);
        toast.show();
        
        // Remove toast element after it's hidden
        toastElement.addEventListener('hidden.bs.toast', () => {
            toastElement.remove();
        });
    }
    
    getOrCreateToastContainer() {
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
            container.style.zIndex = '1050';
            document.body.appendChild(container);
        }
        return container;
    }
    
    getBootstrapColor(type) {
        const colorMap = {
            'success': 'success',
            'error': 'danger',
            'warning': 'warning',
            'info': 'info'
        };
        return colorMap[type] || 'info';
    }
}

// Initialize the app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.app = new CBZifyApp();
});