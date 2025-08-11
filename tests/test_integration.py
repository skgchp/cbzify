#!/usr/bin/env python3
"""
Integration tests for CBZify
Tests end-to-end functionality with mock PDFs and EPUBs
"""

import os
import tempfile
import shutil
import zipfile
from pathlib import Path
import subprocess
import sys

# Add the src directory to Python path so we can import comic_converter
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))


def create_mock_pdf():
    """Create a minimal mock PDF file for testing"""
    # Minimal PDF content (this won't be a real PDF but will have the signature)
    pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj

2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj

3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
>>
endobj

xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer
<<
/Size 4
/Root 1 0 R
>>
startxref
181
%%EOF"""
    return pdf_content


def create_mock_epub():
    """Create a minimal mock EPUB file for testing"""
    temp_dir = tempfile.mkdtemp()
    epub_path = os.path.join(temp_dir, "test.epub")
    
    try:
        with zipfile.ZipFile(epub_path, 'w') as epub:
            # Add mimetype (must be first and uncompressed)
            epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            
            # Add META-INF/container.xml
            container_xml = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>"""
            epub.writestr("META-INF/container.xml", container_xml)
            
            # Add content.opf
            content_opf = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookID" version="3.0">
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:title>Test Comic</dc:title>
        <dc:identifier id="BookID">test-comic-123</dc:identifier>
        <dc:language>en</dc:language>
    </metadata>
    <manifest>
        <item id="page1" href="images/page1.jpg" media-type="image/jpeg"/>
    </manifest>
    <spine>
        <itemref idref="page1"/>
    </spine>
</package>"""
            epub.writestr("OEBPS/content.opf", content_opf)
            
            # Add a mock image
            mock_image = b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xFF\xDB"  # Minimal JPEG header
            epub.writestr("OEBPS/images/page1.jpg", mock_image)
        
        with open(epub_path, 'rb') as f:
            return f.read()
    
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_cli_help():
    """Test that CLI help works without dependencies"""
    print("Testing CLI help functionality...")
    
    try:
        result = subprocess.run(
            [sys.executable, os.path.join("src", "comic_converter.py"), "--help"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0, f"Help command failed: {result.stderr}"
        assert "Convert EPUB and PDF comics to CBZ format" in result.stdout, "Help output missing expected text"
        assert "--workers" in result.stdout, "Help output missing workers option"
        assert "--skip-checks" in result.stdout, "Help output missing skip-checks option"
        assert "--dpi" in result.stdout, "Help output missing DPI option"
        assert "--format" in result.stdout, "Help output missing format option"
        assert "--quality" in result.stdout, "Help output missing quality option"
        print("✓ CLI help test passed")
        
    except subprocess.TimeoutExpired:
        print("✗ CLI help test timed out")
        raise AssertionError("CLI help test timed out")
    except Exception as e:
        print(f"✗ CLI help test failed: {e}")
        raise


def test_file_type_detection():
    """Test file type detection with real file signatures"""
    print("Testing file type detection...")
    
    temp_dir = tempfile.mkdtemp()
    try:
        # Test PDF detection
        pdf_path = os.path.join(temp_dir, "test.pdf")
        with open(pdf_path, 'wb') as f:
            f.write(create_mock_pdf())
        
        # Test EPUB detection  
        epub_path = os.path.join(temp_dir, "test.epub")
        with open(epub_path, 'wb') as f:
            f.write(create_mock_epub())
        
        # Import and test
        from comic_converter import ComicConverter
        
        # Test PDF
        dest_path = os.path.join(temp_dir, "output.cbz")
        converter = ComicConverter(pdf_path, dest_path)
        file_type = converter.detect_file_type()
        assert file_type == "pdf", f"Expected PDF, got {file_type}"
        
        # Test EPUB
        converter = ComicConverter(epub_path, dest_path)
        file_type = converter.detect_file_type()
        assert file_type == "epub", f"Expected EPUB, got {file_type}"
        
        print("✓ File type detection test passed")
        
    except Exception as e:
        print(f"✗ File type detection test failed: {e}")
        raise
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_bulk_processor_directory_scan():
    """Test bulk processor directory scanning"""
    print("Testing bulk processor directory scanning...")
    
    temp_dir = tempfile.mkdtemp()
    try:
        source_dir = os.path.join(temp_dir, "source")
        output_dir = os.path.join(temp_dir, "output")
        os.makedirs(source_dir)
        
        # Create test files
        pdf_content = create_mock_pdf()
        epub_content = create_mock_epub()
        
        with open(os.path.join(source_dir, "comic1.pdf"), 'wb') as f:
            f.write(pdf_content)
        with open(os.path.join(source_dir, "comic2.epub"), 'wb') as f:
            f.write(epub_content)
        with open(os.path.join(source_dir, "readme.txt"), 'w') as f:
            f.write("This should be ignored")
        
        # Test bulk processor
        from comic_converter import BulkProcessor
        
        processor = BulkProcessor(source_dir, output_dir)
        comic_files = processor.find_comic_files()
        
        assert len(comic_files) == 2, f"Expected 2 comic files, found {len(comic_files)}"
        
        file_names = [f.name for f in comic_files]
        assert "comic1.pdf" in file_names, "PDF file not found"
        assert "comic2.epub" in file_names, "EPUB file not found"
        assert "readme.txt" not in file_names, "TXT file should be ignored"
        
        print("✓ Bulk processor test passed")
        
    except Exception as e:
        print(f"✗ Bulk processor test failed: {e}")
        raise
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_progress_tracking():
    """Test progress tracking functionality"""
    print("Testing progress tracking...")
    
    try:
        from comic_converter import ConversionProgress
        
        progress = ConversionProgress()
        
        # Test initial state
        current, total, stage = progress.get_status()
        assert current == 0, f"Expected initial current=0, got {current}"
        assert total == 0, f"Expected initial total=0, got {total}"
        assert stage == "Initializing", f"Expected initial stage='Initializing', got '{stage}'"
        
        # Test updates
        progress.update(current=5, total=10, stage="Processing")
        current, total, stage = progress.get_status()
        assert current == 5, f"Expected current=5, got {current}"
        assert total == 10, f"Expected total=10, got {total}"
        assert stage == "Processing", f"Expected stage='Processing', got '{stage}'"
        
        # Test increment
        progress.increment()
        current, _, _ = progress.get_status()
        assert current == 6, f"Expected current=6 after increment, got {current}"
        
        print("✓ Progress tracking test passed")
        
    except Exception as e:
        print(f"✗ Progress tracking test failed: {e}")
        raise


def test_error_handling():
    """Test error handling for common failure cases"""
    print("Testing error handling...")
    
    temp_dir = tempfile.mkdtemp()
    try:
        from comic_converter import ComicConverter
        
        # Test missing source file
        try:
            ComicConverter("/nonexistent/file.pdf", os.path.join(temp_dir, "out.cbz"))
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError:
            pass  # Expected
        
        # Test unknown file type
        unknown_file = os.path.join(temp_dir, "unknown.xyz")
        with open(unknown_file, 'w') as f:
            f.write("unknown content")
        
        converter = ComicConverter(unknown_file, os.path.join(temp_dir, "out.cbz"))
        try:
            converter.detect_file_type()
            assert False, "Should have raised ValueError for unknown file type"
        except ValueError:
            pass  # Expected
        
        print("✓ Error handling test passed")
        
    except Exception as e:
        print(f"✗ Error handling test failed: {e}")
        raise
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_new_parameter_functionality():
    """Test new DPI and format parameter functionality"""
    print("Testing new DPI and format parameters...")
    
    try:
        from comic_converter import ComicConverter, BulkProcessor
        
        temp_dir = tempfile.mkdtemp()
        source_file = os.path.join(temp_dir, "test.pdf")
        dest_file = os.path.join(temp_dir, "test.cbz")
        
        # Create a dummy PDF file
        with open(source_file, 'wb') as f:
            f.write(create_mock_pdf())
        
        # Test ComicConverter with new parameters
        converter = ComicConverter(source_file, dest_file, dpi=450, image_format='jpg', quality=85)
        assert converter.target_dpi == 450, f"Expected DPI 450, got {converter.target_dpi}"
        assert converter.image_format == 'jpg', f"Expected format jpg, got {converter.image_format}"
        assert converter.quality == 85, f"Expected quality 85, got {converter.quality}"
        
        # Test BulkProcessor with new parameters
        source_dir = os.path.join(temp_dir, "source")
        output_dir = os.path.join(temp_dir, "output")
        os.makedirs(source_dir)
        
        processor = BulkProcessor(source_dir, output_dir, dpi=200, image_format='webp', quality=80)
        assert processor.dpi == 200, f"Expected DPI 200, got {processor.dpi}"
        assert processor.image_format == 'webp', f"Expected format webp, got {processor.image_format}"
        assert processor.quality == 80, f"Expected quality 80, got {processor.quality}"
        
        print("✓ New parameter functionality test passed")
        
    except Exception as e:
        print(f"✗ New parameter functionality test failed: {e}")
        raise
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    """Run all integration tests"""
    print("Running integration tests for CBZify...")
    print("=" * 50)
    
    tests = [
        test_cli_help,
        test_file_type_detection,
        test_bulk_processor_directory_scan,
        test_progress_tracking,
        test_error_handling,
        test_new_parameter_functionality,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} failed with exception: {e}")
            failed += 1
    
    print("\n" + "=" * 50)
    print(f"Integration Tests Summary:")
    print(f"✓ Passed: {passed}")
    print(f"✗ Failed: {failed}")
    print(f"Total: {passed + failed}")
    
    if failed > 0:
        print("\nSome tests failed!")
        sys.exit(1)
    else:
        print("\nAll integration tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()