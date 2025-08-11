#!/usr/bin/env python3
"""
CBZify - Converts EPUB and PDF comics to CBZ format

This program converts comic files from EPUB or PDF format to CBZ (Comic Book Zip) format.
It automatically detects the source file type and applies the appropriate conversion method.

For PDFs:
- Detects if images are stored as DCT streams (JPEG) for direct extraction
- Falls back to page rendering for non-DCT content
- Provides feedback about PDF type to user

For EPUBs:
- Extracts images from the EPUB structure
- Maintains proper page order

Features:
- Command line interface with source and destination arguments
- Detailed progress reporting
- Multithreaded processing for improved performance
- Graceful error handling with user-friendly messages
- Targets 300 DPI and 216x279mm output for lossy conversions
"""

import argparse
import os
import sys
import zipfile
import tempfile
import shutil
import mimetypes
import io
import time
from pathlib import Path
from typing import List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
import threading
from dataclasses import dataclass, field

# Import libraries will be checked later to allow --help to work
fitz = None
ebooklib = None
epub = None
Image = None


def check_dependencies():
    """Check and import required dependencies"""
    global fitz, ebooklib, epub, Image
    
    try:
        import fitz as _fitz
        fitz = _fitz
    except ImportError:
        print("Error: PyMuPDF (fitz) is required. Install with: pip install PyMuPDF")
        sys.exit(1)

    try:
        import ebooklib as _ebooklib
        from ebooklib import epub as _epub
        ebooklib = _ebooklib
        epub = _epub
    except ImportError:
        print("Error: EbookLib is required. Install with: pip install EbookLib")
        sys.exit(1)

    try:
        from PIL import Image as _Image
        Image = _Image
    except ImportError:
        print("Error: Pillow is required. Install with: pip install Pillow")
        sys.exit(1)


def validate_dependencies():
    """Validate that dependencies have been loaded"""
    if fitz is None or ebooklib is None or epub is None or Image is None:
        raise RuntimeError("Dependencies not properly loaded. Call check_dependencies() first.")


def safe_extract_image(pdf_doc, xref, timeout_seconds=5):
    """
    Safely extract image with timeout protection
    Returns (success, image_ext, error_msg)
    """
    def extract_worker():
        try:
            base_image = pdf_doc.extract_image(xref)
            return True, base_image["ext"], None
        except Exception as e:
            return False, None, str(e)
    
    # Use ThreadPoolExecutor for timeout
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(extract_worker)
            success, ext, error = future.result(timeout=timeout_seconds)
            return success, ext, error
    except TimeoutError:
        return False, None, f"Timeout after {timeout_seconds} seconds"
    except Exception as e:
        return False, None, str(e)


@dataclass
class ConversionProgress:
    """Thread-safe progress tracking"""
    current: int = 0
    total: int = 0
    stage: str = "Initializing"
    _lock: threading.Lock = field(default_factory=threading.Lock)
    
    def update(self, current: int = None, total: int = None, stage: str = None):
        with self._lock:
            if current is not None:
                self.current = current
            if total is not None:
                self.total = total
            if stage is not None:
                self.stage = stage
    
    def increment(self):
        with self._lock:
            self.current += 1
    
    def get_status(self) -> Tuple[int, int, str]:
        with self._lock:
            return self.current, self.total, self.stage


class BulkProcessor:
    """Bulk processing manager for multiple files"""
    
    def __init__(self, source_dir: str, output_dir: str, max_workers: int = 4, skip_checks: bool = False,
                 dpi: int = 300, image_format: str = 'png', quality: int = 95):
        self.source_dir = Path(source_dir)
        self.output_dir = Path(output_dir)
        self.max_workers = max_workers
        self.skip_checks = skip_checks
        self.dpi = dpi
        self.image_format = image_format
        self.quality = quality
        self.supported_extensions = {'.pdf', '.epub'}
        self.skip_existing = False
        
        if not self.source_dir.exists() or not self.source_dir.is_dir():
            raise ValueError(f"Source directory does not exist or is not a directory: {source_dir}")
        
        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def find_comic_files(self) -> List[Path]:
        """Find all supported comic files in the source directory"""
        comic_files = []
        
        for file_path in self.source_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in self.supported_extensions:
                comic_files.append(file_path)
        
        # Sort by name for consistent processing order
        comic_files.sort(key=lambda x: x.name.lower())
        return comic_files
    
    def get_output_path(self, source_file: Path) -> Path:
        """Generate output CBZ path for a source file"""
        # Change extension to .cbz and put in output directory
        cbz_name = source_file.stem + '.cbz'
        return self.output_dir / cbz_name
    
    def process_all(self) -> Tuple[int, int]:
        """
        Process all comic files in the directory
        Returns (successful_count, total_count)
        """
        comic_files = self.find_comic_files()
        
        if not comic_files:
            print(f"No supported comic files found in: {self.source_dir}")
            print(f"Supported formats: {', '.join(self.supported_extensions)}")
            return 0, 0
        
        print(f"Found {len(comic_files)} comic files to process")
        print(f"Source directory: {self.source_dir}")
        print(f"Output directory: {self.output_dir}")
        print("-" * 60)
        
        successful = 0
        failed_files = []
        
        for i, source_file in enumerate(comic_files, 1):
            print(f"\n[{i}/{len(comic_files)}] Processing: {source_file.name}")
            
            try:
                output_path = self.get_output_path(source_file)
                
                # Skip if output file already exists (only if skip_existing is True)
                if output_path.exists():
                    if self.skip_existing:
                        print(f"  Skipping - output file already exists: {output_path.name}")
                        successful += 1  # Count as successful since we're intentionally skipping
                        continue
                    else:
                        print(f"  Warning - output file exists, will overwrite: {output_path.name}")
                        # Continue processing to overwrite
                
                # Create converter and process file
                converter = ComicConverter(str(source_file), str(output_path), self.max_workers, self.skip_checks,
                                         self.dpi, self.image_format, self.quality)
                converter.convert()
                successful += 1
                print(f"  ✓ Successfully converted to: {output_path.name}")
                
            except Exception as e:
                print(f"  ✗ Failed to convert {source_file.name}: {e}")
                failed_files.append((source_file.name, str(e)))
                continue
        
        # Summary
        print("\n" + "=" * 60)
        print(f"Bulk processing completed!")
        print(f"Successfully converted: {successful}/{len(comic_files)} files")
        
        if failed_files:
            print(f"\nFailed files:")
            for filename, error in failed_files:
                print(f"  - {filename}: {error}")
        
        return successful, len(comic_files)


class ComicConverter:
    """Main comic conversion class"""
    
    # Target specifications for lossy conversion
    TARGET_DPI = 300
    TARGET_WIDTH_MM = 216
    TARGET_HEIGHT_MM = 279
    
    # Convert mm to pixels at target DPI
    TARGET_WIDTH_PX = int((TARGET_WIDTH_MM / 25.4) * TARGET_DPI)
    TARGET_HEIGHT_PX = int((TARGET_HEIGHT_MM / 25.4) * TARGET_DPI)
    
    def __init__(self, source_path: str, dest_path: str, max_workers: int = 4, skip_checks: bool = False, 
                 dpi: int = 300, image_format: str = 'png', quality: int = 95):
        self.source_path = Path(source_path)
        self.dest_path = Path(dest_path)
        self.max_workers = max_workers
        self.skip_checks = skip_checks
        self.target_dpi = dpi
        self.image_format = image_format.lower()
        self.quality = quality
        self.progress = ConversionProgress()
        
        # Validate input file exists
        if not self.source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")
        
        # Ensure destination directory exists
        self.dest_path.parent.mkdir(parents=True, exist_ok=True)
    
    def detect_file_type(self) -> str:
        """Detect if source file is PDF or EPUB"""
        self.progress.update(stage="Detecting file type")
        
        # Check file extension first
        ext = self.source_path.suffix.lower()
        if ext == '.pdf':
            return 'pdf'
        elif ext == '.epub':
            return 'epub'
        
        # Fallback to mime type detection
        mime_type, _ = mimetypes.guess_type(str(self.source_path))
        if mime_type == 'application/pdf':
            return 'pdf'
        elif mime_type == 'application/epub+zip':
            return 'epub'
        
        # Try to detect by file signature
        try:
            with open(self.source_path, 'rb') as f:
                header = f.read(10)
                if header.startswith(b'%PDF'):
                    return 'pdf'
                elif header.startswith(b'PK\x03\x04'):  # ZIP signature
                    # Could be EPUB, but we'll classify as unknown for now
                    # and let the main conversion handle it
                    pass
        except Exception as e:
            print(f"Warning: Could not read file header: {e}")
        
        raise ValueError(f"Unable to determine file type for: {self.source_path}")
    
    def analyze_pdf_content(self, pdf_doc) -> Tuple[bool, bool, int]:
        """
        Analyze PDF content to determine the best extraction method
        Returns (has_dct_images, has_text_content, total_pages)
        """
        self.progress.update(stage="Analyzing PDF structure")
        
        total_pages = len(pdf_doc)
        print(f"Analyzing PDF with {total_pages} pages for content structure...")
        
        dct_image_count = 0
        total_images = 0
        pages_checked = 0
        text_content_found = False
        
        # Limit analysis to first 3-5 pages for speed - this is usually enough to determine pattern
        max_pages_to_check = min(5, total_pages)
        
        # Overall timeout for the entire analysis
        start_time = time.time()
        max_analysis_time = 15  # 15 seconds max for analysis
        
        for page_num in range(max_pages_to_check):
            # Check overall timeout
            if time.time() - start_time > max_analysis_time:
                print(f"  Analysis timeout after {max_analysis_time} seconds - using fallback classification")
                break
                
            try:
                page = pdf_doc[page_num]
                
                # Check for text content on this page
                if not text_content_found:
                    try:
                        page_text = page.get_text().strip()
                        if page_text and len(page_text) > 10:  # Ignore minimal text like page numbers
                            text_content_found = True
                            print(f"  Text content detected on page {page_num + 1}")
                    except Exception as e:
                        # Some PDFs might have issues with text extraction
                        pass
                
                # Check images on this page
                image_list = page.get_images()
                
                if len(image_list) == 0:
                    continue
                
                # Only show progress for first page or every few pages
                if page_num == 0 or page_num % 2 == 0:
                    print(f"  Checking page {page_num + 1}/{max_pages_to_check} ({len(image_list)} images)...")
                
                for img_index, img in enumerate(image_list):
                    total_images += 1
                    xref = img[0]
                    
                    # Use safe extraction with shorter timeout for faster analysis
                    success, image_ext, error = safe_extract_image(pdf_doc, xref, timeout_seconds=2)
                    
                    if success and image_ext:
                        # Check if it's a JPEG (DCT stream)
                        if image_ext in ["jpeg", "jpg"]:
                            dct_image_count += 1
                        # Don't print every single image type for performance
                    else:
                        # Only warn on timeout errors, not format errors
                        if error and "Timeout" in error:
                            print(f"      Warning: Image analysis timeout on page {page_num + 1}")
                        continue
                
                pages_checked += 1
                
                # Early exit if we have a clear pattern (more aggressive)
                if pages_checked >= 2 and total_images > 0:
                    dct_ratio = dct_image_count / total_images
                    if dct_ratio >= 0.8 and not text_content_found:
                        print(f"  Early detection: {dct_image_count}/{total_images} images are DCT, no text - safe for DCT extraction")
                        break
                    elif dct_ratio == 0 and pages_checked >= 2:
                        print(f"  Early detection: No DCT images found in first {pages_checked} pages - will render pages")
                        break
                    elif text_content_found and dct_ratio > 0:
                        print(f"  Early detection: DCT images found but text content present - must render pages")
                        break
                        
            except Exception as e:
                print(f"  Error processing page {page_num + 1}: {e}")
                continue
        
        # Determine final classification - DCT extraction is only safe if:
        # 1. Most images are DCT/JPEG format, AND
        # 2. No significant text content is found (text would be lost)
        if total_images == 0:
            print("  No images found during analysis - will render pages as fallback")
            can_use_dct = False
        else:
            has_sufficient_dct = dct_image_count > 0 and (dct_image_count >= total_images * 0.8)
            can_use_dct = has_sufficient_dct and not text_content_found
        
        elapsed_time = time.time() - start_time
        print(f"Content analysis complete in {elapsed_time:.1f}s:")
        print(f"  - DCT images: {dct_image_count}/{total_images}")
        print(f"  - Text content: {'Yes' if text_content_found else 'No'}")
        
        if can_use_dct:
            print(f"PDF classification: DCT-based (safe to extract images directly)")
        else:
            reason = "contains text overlays" if text_content_found else "insufficient DCT images"
            print(f"PDF classification: Must render pages ({reason})")
        
        return can_use_dct, text_content_found, total_pages
    
    def extract_pdf_dct_images(self, pdf_doc, temp_dir: Path) -> List[Path]:
        """Extract DCT (JPEG) images directly from PDF, avoiding duplicates"""
        self.progress.update(stage="Extracting DCT images from PDF")
        
        image_files = []
        page_count = len(pdf_doc)
        self.progress.update(total=page_count)
        extracted_xrefs = set()  # Track already extracted image xrefs
        
        def extract_page_images(page_num: int) -> List[Tuple[int, Path, int]]:
            """Extract images from a single page, avoiding duplicates"""
            page = pdf_doc[page_num]
            image_list = page.get_images()
            
            page_images = []
            for img_index, img in enumerate(image_list):
                xref = img[0]
                
                # Skip if we've already extracted this image
                if xref in extracted_xrefs:
                    continue
                    
                try:
                    base_image = pdf_doc.extract_image(xref)
                    image_ext = base_image["ext"]
                    
                    if image_ext in ["jpeg", "jpg"]:
                        image_bytes = base_image["image"]
                        
                        # Save image with page number for sorting
                        img_filename = f"page_{page_num:04d}_{img_index:02d}.{image_ext}"
                        img_path = temp_dir / img_filename
                        
                        with open(img_path, "wb") as img_file:
                            img_file.write(image_bytes)
                        
                        # Mark this xref as extracted
                        extracted_xrefs.add(xref)
                        page_images.append((page_num, img_path, xref))
                
                except Exception as e:
                    print(f"Warning: Could not extract image {img_index} from page {page_num}: {e}")
            
            self.progress.increment()
            current, total, stage = self.progress.get_status()
            if current % 10 == 0 or current == total:
                print(f"Progress: {current}/{total} pages processed")
            
            return page_images
        
        # Extract images sequentially to handle deduplication properly
        all_images = []
        for page_num in range(page_count):
            try:
                page_images = extract_page_images(page_num)
                all_images.extend(page_images)
            except Exception as e:
                print(f"Error processing page {page_num}: {e}")
        
        # Sort by page number and return just the paths
        all_images.sort(key=lambda x: x[0])
        image_files = [img_path for _, img_path, _ in all_images]
        
        print(f"Extracted {len(image_files)} DCT images from PDF")
        return image_files
    
    def render_pdf_pages(self, pdf_doc, temp_dir: Path) -> List[Path]:
        """Render PDF pages as images"""
        self.progress.update(stage="Rendering PDF pages")
        
        page_count = len(pdf_doc)
        self.progress.update(total=page_count)
        image_files = []
        
        # Calculate zoom to achieve target DPI
        # PyMuPDF default is 72 DPI, so zoom = target_dpi / 72
        zoom = self.target_dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        
        def render_page(page_num: int) -> Tuple[int, Path]:
            """Render a single page"""
            page = pdf_doc[page_num]
            
            # Render page to image
            pix = page.get_pixmap(matrix=mat)
            
            # Convert to PIL Image  
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            
            # The zoom factor already ensures we get the target DPI
            # The resulting dimensions will be equivalent to 216x279mm at target DPI
            # but scaled proportionally to maintain the source aspect ratio
            
            # Determine file extension and format
            if self.image_format in ['jpg', 'jpeg']:
                ext = 'jpg'
                pil_format = 'JPEG'
            elif self.image_format == 'webp':
                ext = 'webp'
                pil_format = 'WebP'
            else:  # default to PNG
                ext = 'png'
                pil_format = 'PNG'
            
            # Save image with appropriate format and quality
            img_filename = f"page_{page_num:04d}.{ext}"
            img_path = temp_dir / img_filename
            
            # Save with format-specific options
            if pil_format == 'PNG':
                img.save(img_path, pil_format, optimize=True)
            elif pil_format == 'JPEG':
                # Convert RGBA to RGB for JPEG (JPEG doesn't support transparency)
                if img.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'RGBA':
                        background.paste(img, mask=img.split()[-1])  # Use alpha channel as mask
                    else:
                        background.paste(img)
                    img = background
                img.save(img_path, pil_format, quality=self.quality, optimize=True)
            elif pil_format == 'WebP':
                img.save(img_path, pil_format, quality=self.quality, optimize=True)
            
            # Note: Progress will be updated by main thread when future completes
            
            return page_num, img_path
        
        # Render pages using thread pool
        rendered_pages = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(render_page, page_num): page_num 
                      for page_num in range(page_count)}
            
            for future in as_completed(futures):
                try:
                    page_num, img_path = future.result()
                    rendered_pages.append((page_num, img_path))
                    
                    # Update progress after each page completion
                    self.progress.increment()
                    current, total, stage = self.progress.get_status()
                    if current % 5 == 0 or current == total:
                        print(f"Progress: {current}/{total} pages rendered")
                        
                except Exception as e:
                    page_num = futures[future]
                    print(f"Error rendering page {page_num}: {e}")
                    # Still increment progress for failed pages to maintain count
                    self.progress.increment()
        
        # Sort by page number and return paths
        rendered_pages.sort(key=lambda x: x[0])
        image_files = [img_path for _, img_path in rendered_pages]
        
        print(f"Rendered {len(image_files)} pages from PDF")
        return image_files
    
    def extract_epub_images(self, temp_dir: Path) -> List[Path]:
        """Extract images from EPUB file"""
        self.progress.update(stage="Extracting images from EPUB")
        
        try:
            book = epub.read_epub(str(self.source_path))
        except Exception as e:
            raise ValueError(f"Could not open EPUB file: {e}")
        
        image_files = []
        image_items = []
        
        # Collect all image items
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_IMAGE:
                image_items.append(item)
        
        self.progress.update(total=len(image_items))
        print(f"Found {len(image_items)} images in EPUB")
        
        # Extract and process images
        for i, item in enumerate(image_items):
            try:
                # Get image data
                image_data = item.get_content()
                
                # Determine file extension - handle different ebooklib versions
                try:
                    # Try get_media_type() first (newer versions)
                    media_type = item.get_media_type()
                except AttributeError:
                    # Fall back to media_type attribute (older versions)
                    media_type = getattr(item, 'media_type', None)
                
                if media_type == 'image/jpeg':
                    ext = 'jpg'
                elif media_type == 'image/png':
                    ext = 'png'
                elif media_type == 'image/gif':
                    ext = 'gif'
                elif media_type == 'image/webp':
                    ext = 'webp'
                else:
                    # Try to determine from filename
                    original_name = item.get_name()
                    ext = Path(original_name).suffix[1:] if Path(original_name).suffix else 'jpg'
                
                # Create filename with proper sorting
                img_filename = f"image_{i:04d}.{ext}"
                img_path = temp_dir / img_filename
                
                # Process image in memory to avoid redundant I/O
                try:
                    # Load image directly from memory buffer
                    img_bytes = io.BytesIO(image_data)
                    with Image.open(img_bytes) as img:
                        # Preserve original image dimensions by default (no auto-resizing)
                        # This preserves the original artwork quality and dimensions
                        # Note: Advanced resizing options can be added later if needed
                        img.save(img_path, optimize=True, quality=95)
                
                except Exception as e:
                    print(f"Warning: Could not process image {i+1}: {e}")
                    # Fallback: save original image data if processing fails
                    with open(img_path, 'wb') as f:
                        f.write(image_data)
                
                image_files.append(img_path)
                self.progress.increment()
                
                if (i + 1) % 10 == 0:
                    print(f"Progress: {i+1}/{len(image_items)} images extracted")
            
            except Exception as e:
                print(f"Error extracting image {i+1}: {e}")
                continue
        
        print(f"Successfully extracted {len(image_files)} images from EPUB")
        return image_files
    
    def create_cbz(self, image_files: List[Path]) -> None:
        """Create CBZ file from image files"""
        self.progress.update(stage="Creating CBZ file", current=0, total=len(image_files))
        
        if not image_files:
            raise ValueError("No images found to create CBZ file")
        
        # Ensure images are properly sorted
        image_files.sort()
        
        try:
            with zipfile.ZipFile(self.dest_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as cbz:
                for i, img_path in enumerate(image_files):
                    # Use original filename but with proper numbering
                    cbz_filename = f"{i+1:04d}_{img_path.name}"
                    cbz.write(img_path, cbz_filename)
                    
                    self.progress.increment()
                    if (i + 1) % 10 == 0:
                        print(f"Progress: {i+1}/{len(image_files)} images added to CBZ")
            
            print(f"Successfully created CBZ file: {self.dest_path}")
            print(f"CBZ contains {len(image_files)} pages")
            
            # Show file size
            file_size = self.dest_path.stat().st_size
            size_mb = file_size / (1024 * 1024)
            print(f"CBZ file size: {size_mb:.1f} MB")
        
        except Exception as e:
            if self.dest_path.exists():
                self.dest_path.unlink()  # Clean up partial file
            raise RuntimeError(f"Failed to create CBZ file: {e}")
    
    def convert(self) -> None:
        """Main conversion method"""
        try:
            # Validate dependencies are loaded
            validate_dependencies()
            
            # Detect file type
            file_type = self.detect_file_type()
            print(f"Detected file type: {file_type.upper()}")
            
            # Create temporary directory for images
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                image_files = []
                
                if file_type == 'pdf':
                    # Open PDF document
                    self.progress.update(stage="Opening PDF")
                    print("Opening PDF document...")
                    try:
                        pdf_doc = fitz.open(str(self.source_path))
                        print(f"PDF opened successfully - {len(pdf_doc)} pages detected")
                    except Exception as e:
                        raise RuntimeError(f"Failed to open PDF: {e}")
                    
                    try:
                        total_pages = len(pdf_doc)
                        
                        # Check for DCT images unless skip_checks is enabled
                        if self.skip_checks:
                            print(f"Skip checks: Skipping content analysis - rendering all pages")
                            print(f"Total pages: {total_pages}")
                            print(f"Target resolution: {self.target_dpi} DPI")
                            print(f"Target dimensions: {self.TARGET_WIDTH_MM}x{self.TARGET_HEIGHT_MM}mm")
                            print(f"Image format: {self.image_format.upper()}")
                            image_files = self.render_pdf_pages(pdf_doc, temp_path)
                        else:
                            can_use_dct, has_text, total_pages = self.analyze_pdf_content(pdf_doc)
                            
                            if can_use_dct:
                                print(f"PDF has DCT images and no text overlays - extracting images directly")
                                print(f"Total pages: {total_pages}")
                                image_files = self.extract_pdf_dct_images(pdf_doc, temp_path)
                            else:
                                if has_text:
                                    print(f"PDF contains text overlays - rendering complete pages to preserve text")
                                else:
                                    print(f"PDF does not contain extractable DCT images - rendering pages")
                                print(f"Total pages: {total_pages}")
                                print(f"Target resolution: {self.target_dpi} DPI")
                                print(f"Target dimensions: {self.TARGET_WIDTH_MM}x{self.TARGET_HEIGHT_MM}mm")
                                print(f"Image format: {self.image_format.upper()}")
                                image_files = self.render_pdf_pages(pdf_doc, temp_path)
                    
                    finally:
                        pdf_doc.close()
                
                elif file_type == 'epub':
                    print("Processing EPUB file")
                    image_files = self.extract_epub_images(temp_path)
                
                # Create CBZ file
                if image_files:
                    self.create_cbz(image_files)
                else:
                    raise ValueError("No images were extracted from the source file")
        
        except Exception as e:
            print(f"Conversion failed: {e}")
            raise


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Convert EPUB and PDF comics to CBZ format. Supports both single file and bulk directory processing.",
        epilog="Examples:\n"
               "Single file conversion:\n"
               "  %(prog)s comic.pdf comic.cbz\n"
               "  %(prog)s book.epub book.cbz\n"
               "  %(prog)s --workers 8 large_comic.pdf output.cbz\n\n"
               "Bulk directory processing:\n"
               "  %(prog)s /path/to/comics/ /path/to/output/\n"
               "  %(prog)s --workers 8 ./input_folder/ ./cbz_output/\n"
               "  %(prog)s --skip-checks --workers 12 ~/Downloads/comics/ ~/Comics/CBZ/",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('source', 
                       help='Source file (PDF/EPUB) or directory containing comic files')
    parser.add_argument('destination', 
                       help='Destination CBZ file or output directory for bulk processing')
    parser.add_argument('--workers', '-w', 
                       type=int, 
                       default=4,
                       help='Number of worker threads (default: 4)')
    parser.add_argument('--skip-existing',
                       action='store_true',
                       help='Skip files that already have corresponding CBZ outputs (bulk processing only)')
    parser.add_argument('--skip-checks', '-s',
                       action='store_true',
                       help='Skip content analysis and always render pages (consistent performance)')
    # Keep --fast as deprecated alias for backward compatibility
    parser.add_argument('--fast', '-f',
                       action='store_true',
                       help=argparse.SUPPRESS)  # Hidden deprecated option
    parser.add_argument('--dpi',
                       type=int,
                       default=300,
                       help='DPI for rendered pages (default: 300)')
    parser.add_argument('--format',
                       choices=['png', 'jpg', 'jpeg', 'webp'],
                       default='png',
                       help='Image format for rendered pages (default: png, options: png, jpg, jpeg, webp)')
    parser.add_argument('--quality',
                       type=int,
                       default=95,
                       help='JPEG/WebP quality (1-100, default: 95, only applies to jpg/jpeg/webp formats)')
    parser.add_argument('--version', 
                       action='version', 
                       version='CBZify 1.0')
    
    args = parser.parse_args()
    
    try:
        # Check dependencies first
        check_dependencies()
        
        # Validate arguments
        if not os.path.exists(args.source):
            print(f"Error: Source '{args.source}' does not exist")
            sys.exit(1)
        
        if args.workers < 1:
            print("Error: Number of workers must be at least 1")
            sys.exit(1)
        
        if args.dpi < 50 or args.dpi > 600:
            print("Error: DPI must be between 50 and 600")
            sys.exit(1)
            
        if args.quality < 1 or args.quality > 100:
            print("Error: Quality must be between 1 and 100")
            sys.exit(1)
        
        # Handle backward compatibility for --fast flag
        skip_checks = args.skip_checks or args.fast
        if args.fast:
            print("Warning: --fast flag is deprecated, use --skip-checks instead")
        
        # Show configuration
        print("CBZify v1.0")
        print("-" * 50)
        print(f"Source: {args.source}")
        print(f"Destination: {args.destination}")
        print(f"Workers: {args.workers}")
        print(f"DPI: {args.dpi}")
        print(f"Image format: {args.format.upper()}")
        if args.format in ['jpg', 'jpeg', 'webp']:
            print(f"Quality: {args.quality}")
        if skip_checks:
            print("Skip checks: Enabled (skipping content analysis)")
        
        # Determine if we're doing single file or bulk processing
        source_path = Path(args.source)
        
        if source_path.is_file():
            # Single file processing
            print("Mode: Single file conversion")
            if args.skip_existing:
                print("Note: --skip-existing flag is ignored for single file conversion")
            print("-" * 50)
            
            converter = ComicConverter(args.source, args.destination, args.workers, skip_checks,
                                      args.dpi, args.format, args.quality)
            converter.convert()
            
            print("-" * 50)
            print("Conversion completed successfully!")
            
        elif source_path.is_dir():
            # Bulk directory processing
            print("Mode: Bulk directory processing")
            if args.skip_existing:
                print("Skip existing: Enabled")
            print("-" * 50)
            
            # Update BulkProcessor to handle all new parameters
            processor = BulkProcessor(args.source, args.destination, args.workers, skip_checks,
                                     args.dpi, args.format, args.quality)
            processor.skip_existing = args.skip_existing
            successful, total = processor.process_all()
            
            print("-" * 50)
            if successful == total and total > 0:
                print("All files converted successfully!")
            elif successful > 0:
                print(f"Conversion completed with {total - successful} failures.")
            else:
                print("No files were converted successfully.")
                sys.exit(1)
        
        else:
            print(f"Error: Source '{args.source}' is neither a file nor a directory")
            sys.exit(1)
    
    except KeyboardInterrupt:
        print("\nConversion cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()