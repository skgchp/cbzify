#!/usr/bin/env python3
"""
Test suite for CBZify
Tests core functionality including PDF/EPUB detection, conversion logic, and error handling
"""

import unittest
import tempfile
import shutil
import os
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
import io
import sys

# Import the classes we're testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from comic_converter import ComicConverter, BulkProcessor, ConversionProgress


class TestConversionProgress(unittest.TestCase):
    """Test the thread-safe progress tracking"""
    
    def setUp(self):
        self.progress = ConversionProgress()
    
    def test_initial_state(self):
        """Test initial progress state"""
        current, total, stage = self.progress.get_status()
        self.assertEqual(current, 0)
        self.assertEqual(total, 0)
        self.assertEqual(stage, "Initializing")
    
    def test_update_progress(self):
        """Test updating progress values"""
        self.progress.update(current=5, total=10, stage="Testing")
        current, total, stage = self.progress.get_status()
        self.assertEqual(current, 5)
        self.assertEqual(total, 10)
        self.assertEqual(stage, "Testing")
    
    def test_increment(self):
        """Test incrementing current value"""
        self.progress.update(current=5)
        self.progress.increment()
        current, _, _ = self.progress.get_status()
        self.assertEqual(current, 6)


class TestComicConverter(unittest.TestCase):
    """Test the main CBZify functionality"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.source_path = os.path.join(self.temp_dir, "test.pdf")
        self.dest_path = os.path.join(self.temp_dir, "test.cbz")
        
        # Create a dummy source file
        with open(self.source_path, 'w') as f:
            f.write("dummy pdf content")
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_detect_file_type_pdf(self):
        """Test PDF file type detection by extension"""
        converter = ComicConverter(self.source_path, self.dest_path)
        file_type = converter.detect_file_type()
        self.assertEqual(file_type, 'pdf')
    
    def test_detect_file_type_epub(self):
        """Test EPUB file type detection by extension"""
        epub_path = os.path.join(self.temp_dir, "test.epub")
        with open(epub_path, 'w') as f:
            f.write("dummy epub content")
        
        converter = ComicConverter(epub_path, self.dest_path)
        file_type = converter.detect_file_type()
        self.assertEqual(file_type, 'epub')
    
    def test_detect_file_type_by_signature(self):
        """Test file type detection by binary signature"""
        # Create a file with PDF signature but wrong extension
        pdf_content_path = os.path.join(self.temp_dir, "test.unknown")
        with open(pdf_content_path, 'wb') as f:
            f.write(b'%PDF-1.4\nsome pdf content')
        
        converter = ComicConverter(pdf_content_path, self.dest_path)
        file_type = converter.detect_file_type()
        self.assertEqual(file_type, 'pdf')
    
    def test_detect_file_type_unknown(self):
        """Test unknown file type raises error"""
        unknown_path = os.path.join(self.temp_dir, "test.unknown")
        with open(unknown_path, 'wb') as f:
            f.write(b'unknown content')
        
        converter = ComicConverter(unknown_path, self.dest_path)
        with self.assertRaises(ValueError):
            converter.detect_file_type()
    
    def test_source_file_not_found(self):
        """Test error handling for missing source file"""
        nonexistent = os.path.join(self.temp_dir, "nonexistent.pdf")
        with self.assertRaises(FileNotFoundError):
            ComicConverter(nonexistent, self.dest_path)
    
    @patch('comic_converter.zipfile.ZipFile')
    def test_create_cbz_basic(self, mock_zipfile):
        """Test CBZ creation with basic image files"""
        # Create mock image files
        img_files = []
        for i in range(3):
            img_path = Path(self.temp_dir) / f"image_{i:04d}.jpg"
            with open(img_path, 'w') as f:
                f.write(f"mock image {i}")
            img_files.append(img_path)
        
        converter = ComicConverter(self.source_path, self.dest_path)
        
        # Mock the zipfile context manager
        mock_cbz = MagicMock()
        mock_zipfile.return_value.__enter__.return_value = mock_cbz
        
        # Create a real CBZ file to avoid stat() issues
        with open(converter.dest_path, 'w') as f:
            f.write("mock cbz content")
        
        converter.create_cbz(img_files)
        
        # Verify zipfile was created with correct parameters
        mock_zipfile.assert_called_once_with(
            converter.dest_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6
        )
        
        # Verify all images were added
        self.assertEqual(mock_cbz.write.call_count, 3)
    
    def test_create_cbz_no_images(self):
        """Test CBZ creation with no images raises error"""
        converter = ComicConverter(self.source_path, self.dest_path)
        with self.assertRaises(ValueError) as context:
            converter.create_cbz([])
        self.assertIn("No images found", str(context.exception))


class TestBulkProcessor(unittest.TestCase):
    """Test bulk directory processing"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = os.path.join(self.temp_dir, "source")
        self.output_dir = os.path.join(self.temp_dir, "output")
        os.makedirs(self.source_dir)
        
        # Create test files
        self.pdf_file = os.path.join(self.source_dir, "comic1.pdf")
        self.epub_file = os.path.join(self.source_dir, "comic2.epub")
        self.txt_file = os.path.join(self.source_dir, "readme.txt")
        
        for file_path in [self.pdf_file, self.epub_file, self.txt_file]:
            with open(file_path, 'w') as f:
                f.write("dummy content")
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_find_comic_files(self):
        """Test finding supported comic files in directory"""
        processor = BulkProcessor(self.source_dir, self.output_dir)
        comic_files = processor.find_comic_files()
        
        # Should find PDF and EPUB, but not TXT
        self.assertEqual(len(comic_files), 2)
        file_names = [f.name for f in comic_files]
        self.assertIn("comic1.pdf", file_names)
        self.assertIn("comic2.epub", file_names)
        self.assertNotIn("readme.txt", file_names)
    
    def test_find_comic_files_sorted(self):
        """Test that found files are sorted alphabetically"""
        processor = BulkProcessor(self.source_dir, self.output_dir)
        comic_files = processor.find_comic_files()
        
        # Files should be sorted by name
        file_names = [f.name for f in comic_files]
        self.assertEqual(file_names, sorted(file_names, key=str.lower))
    
    def test_get_output_path(self):
        """Test output path generation"""
        processor = BulkProcessor(self.source_dir, self.output_dir)
        source_file = Path(self.pdf_file)
        output_path = processor.get_output_path(source_file)
        
        expected = Path(self.output_dir) / "comic1.cbz"
        self.assertEqual(output_path, expected)
    
    def test_source_directory_not_found(self):
        """Test error handling for missing source directory"""
        nonexistent = os.path.join(self.temp_dir, "nonexistent")
        with self.assertRaises(ValueError):
            BulkProcessor(nonexistent, self.output_dir)
    
    def test_output_directory_creation(self):
        """Test that output directory is created if it doesn't exist"""
        processor = BulkProcessor(self.source_dir, self.output_dir)
        self.assertTrue(os.path.exists(self.output_dir))
        self.assertTrue(os.path.isdir(self.output_dir))


class TestPDFAnalysis(unittest.TestCase):
    """Test PDF content analysis logic"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.source_path = os.path.join(self.temp_dir, "test.pdf")
        self.dest_path = os.path.join(self.temp_dir, "test.cbz")
        
        with open(self.source_path, 'w') as f:
            f.write("dummy pdf")
        
        self.converter = ComicConverter(self.source_path, self.dest_path)
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('comic_converter.check_dependencies')
    def test_analyze_pdf_content_dct_no_text(self, mock_deps):
        """Test PDF analysis with DCT images and no text"""
        mock_pdf_doc = MagicMock()
        mock_pdf_doc.__len__.return_value = 5
        
        # Mock pages with DCT images and no text
        mock_pages = []
        for i in range(5):
            mock_page = MagicMock()
            mock_page.get_text.return_value = ""  # No text
            mock_page.get_images.return_value = [(f"xref_{i}", "dummy")]
            mock_pages.append(mock_page)
        
        mock_pdf_doc.__getitem__.side_effect = lambda i: mock_pages[i]
        
        # Mock image extraction to return JPEG
        with patch('comic_converter.safe_extract_image') as mock_extract:
            mock_extract.return_value = (True, "jpeg", None)
            
            can_use_dct, has_text, total_pages = self.converter.analyze_pdf_content(mock_pdf_doc)
            
            self.assertTrue(can_use_dct)
            self.assertFalse(has_text)
            self.assertEqual(total_pages, 5)
    
    @patch('comic_converter.check_dependencies')
    def test_analyze_pdf_content_with_text(self, mock_deps):
        """Test PDF analysis with text content"""
        mock_pdf_doc = MagicMock()
        mock_pdf_doc.__len__.return_value = 3
        
        # Mock pages with text content
        mock_pages = []
        for i in range(3):
            mock_page = MagicMock()
            if i == 1:  # Second page has text
                mock_page.get_text.return_value = "Some speech bubble text here"
            else:
                mock_page.get_text.return_value = ""
            mock_page.get_images.return_value = [(f"xref_{i}", "dummy")]
            mock_pages.append(mock_page)
        
        mock_pdf_doc.__getitem__.side_effect = lambda i: mock_pages[i]
        
        # Mock image extraction to return JPEG
        with patch('comic_converter.safe_extract_image') as mock_extract:
            mock_extract.return_value = (True, "jpeg", None)
            
            can_use_dct, has_text, total_pages = self.converter.analyze_pdf_content(mock_pdf_doc)
            
            self.assertFalse(can_use_dct)  # Should not use DCT due to text
            self.assertTrue(has_text)
            self.assertEqual(total_pages, 3)
    
    @patch('comic_converter.check_dependencies')
    def test_analyze_pdf_content_no_dct_images(self, mock_deps):
        """Test PDF analysis with non-DCT images"""
        mock_pdf_doc = MagicMock()
        mock_pdf_doc.__len__.return_value = 2
        
        # Mock pages with non-JPEG images
        mock_pages = []
        for i in range(2):
            mock_page = MagicMock()
            mock_page.get_text.return_value = ""
            mock_page.get_images.return_value = [(f"xref_{i}", "dummy")]
            mock_pages.append(mock_page)
        
        mock_pdf_doc.__getitem__.side_effect = lambda i: mock_pages[i]
        
        # Mock image extraction to return PNG (not JPEG)
        with patch('comic_converter.safe_extract_image') as mock_extract:
            mock_extract.return_value = (True, "png", None)
            
            can_use_dct, has_text, total_pages = self.converter.analyze_pdf_content(mock_pdf_doc)
            
            self.assertFalse(can_use_dct)  # Should not use DCT due to non-JPEG images
            self.assertFalse(has_text)
            self.assertEqual(total_pages, 2)


class TestImageDeduplication(unittest.TestCase):
    """Test the xref deduplication fix"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.source_path = os.path.join(self.temp_dir, "test.pdf")
        self.dest_path = os.path.join(self.temp_dir, "test.cbz")
        
        with open(self.source_path, 'w') as f:
            f.write("dummy pdf")
        
        self.converter = ComicConverter(self.source_path, self.dest_path)
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('comic_converter.check_dependencies')
    def test_xref_deduplication(self, mock_deps):
        """Test that duplicate xrefs are properly handled"""
        mock_pdf_doc = MagicMock()
        mock_pdf_doc.__len__.return_value = 3
        
        # Mock pages that all reference the same image (same xref)
        mock_pages = []
        for i in range(3):
            mock_page = MagicMock()
            # All pages reference the same image xref
            mock_page.get_images.return_value = [(100, "dummy")]  # Same xref=100
            mock_pages.append(mock_page)
        
        mock_pdf_doc.__getitem__.side_effect = lambda i: mock_pages[i]
        
        # Mock image extraction
        mock_pdf_doc.extract_image.return_value = {
            "image": b"fake jpeg data",
            "ext": "jpeg"
        }
        
        temp_path = Path(self.temp_dir) / "temp_images"
        temp_path.mkdir()
        
        # Extract images
        image_files = self.converter.extract_pdf_dct_images(mock_pdf_doc, temp_path)
        
        # Should only extract the image once, not three times
        self.assertEqual(len(image_files), 1, "Should only extract unique images once")
        
        # Verify the extracted image exists
        self.assertTrue(image_files[0].exists())


class TestErrorHandling(unittest.TestCase):
    """Test error handling and edge cases"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_invalid_source_path(self):
        """Test handling of invalid source paths"""
        invalid_source = "/nonexistent/path/file.pdf"
        dest_path = os.path.join(self.temp_dir, "output.cbz")
        
        with self.assertRaises(FileNotFoundError):
            ComicConverter(invalid_source, dest_path)
    
    @patch('comic_converter.check_dependencies')
    def test_cbz_creation_failure_cleanup(self, mock_deps):
        """Test that partial CBZ files are cleaned up on failure"""
        source_path = os.path.join(self.temp_dir, "test.pdf")
        dest_path = os.path.join(self.temp_dir, "test.cbz")
        
        with open(source_path, 'w') as f:
            f.write("dummy")
        
        converter = ComicConverter(source_path, dest_path)
        
        # Create the destination file to simulate partial creation
        with open(dest_path, 'w') as f:
            f.write("partial file")
        
        # Mock zipfile to raise an exception
        with patch('comic_converter.zipfile.ZipFile') as mock_zipfile:
            mock_zipfile.side_effect = Exception("Zip creation failed")
            
            with self.assertRaises(RuntimeError):
                converter.create_cbz([Path(source_path)])
            
            # File should be cleaned up
            self.assertFalse(os.path.exists(dest_path))


class TestNewFeatures(unittest.TestCase):
    """Test new DPI and format features"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.source_path = os.path.join(self.temp_dir, "test.pdf")
        self.dest_path = os.path.join(self.temp_dir, "test.cbz")
        
        # Create a dummy source file
        with open(self.source_path, 'w') as f:
            f.write("dummy pdf content")
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_comic_converter_default_parameters(self):
        """Test ComicConverter with default parameters"""
        converter = ComicConverter(self.source_path, self.dest_path)
        self.assertEqual(converter.target_dpi, 300)
        self.assertEqual(converter.image_format, 'png')
        self.assertEqual(converter.quality, 95)
    
    def test_comic_converter_custom_parameters(self):
        """Test ComicConverter with custom parameters"""
        converter = ComicConverter(self.source_path, self.dest_path, 
                                 dpi=450, image_format='jpg', quality=85)
        self.assertEqual(converter.target_dpi, 450)
        self.assertEqual(converter.image_format, 'jpg')
        self.assertEqual(converter.quality, 85)
    
    def test_comic_converter_case_insensitive_format(self):
        """Test that image format is case insensitive"""
        converter = ComicConverter(self.source_path, self.dest_path, image_format='WEBP')
        self.assertEqual(converter.image_format, 'webp')
    
    def test_bulk_processor_default_parameters(self):
        """Test BulkProcessor with default parameters"""
        source_dir = os.path.join(self.temp_dir, "source")
        output_dir = os.path.join(self.temp_dir, "output")
        os.makedirs(source_dir)
        
        processor = BulkProcessor(source_dir, output_dir)
        self.assertEqual(processor.dpi, 300)
        self.assertEqual(processor.image_format, 'png')
        self.assertEqual(processor.quality, 95)
    
    def test_bulk_processor_custom_parameters(self):
        """Test BulkProcessor with custom parameters"""
        source_dir = os.path.join(self.temp_dir, "source")
        output_dir = os.path.join(self.temp_dir, "output")
        os.makedirs(source_dir)
        
        processor = BulkProcessor(source_dir, output_dir, 
                                dpi=200, image_format='webp', quality=80)
        self.assertEqual(processor.dpi, 200)
        self.assertEqual(processor.image_format, 'webp')
        self.assertEqual(processor.quality, 80)
    
    def test_image_format_logic(self):
        """Test image format selection logic"""
        test_cases = [
            ('png', 'png', 'PNG'),
            ('jpg', 'jpg', 'JPEG'),
            ('jpeg', 'jpg', 'JPEG'),
            ('webp', 'webp', 'WebP')
        ]
        
        for input_format, expected_ext, expected_pil_format in test_cases:
            converter = ComicConverter(self.source_path, self.dest_path, 
                                     image_format=input_format)
            
            # Simulate the format detection logic from render_pdf_pages
            if converter.image_format in ['jpg', 'jpeg']:
                ext = 'jpg'
                pil_format = 'JPEG'
            elif converter.image_format == 'webp':
                ext = 'webp'
                pil_format = 'WebP'
            else:
                ext = 'png'
                pil_format = 'PNG'
            
            self.assertEqual(ext, expected_ext, 
                           f"Format {input_format}: expected ext {expected_ext}, got {ext}")
            self.assertEqual(pil_format, expected_pil_format,
                           f"Format {input_format}: expected PIL format {expected_pil_format}, got {pil_format}")


class TestCLIIntegration(unittest.TestCase):
    """Test command-line interface integration"""
    
    def test_help_output(self):
        """Test that help can be displayed without dependencies"""
        import subprocess
        import sys
        
        # Run with --help flag
        result = subprocess.run(
            [sys.executable, os.path.join("src", "comic_converter.py"), "--help"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        self.assertEqual(result.returncode, 0)
        # Check for expected content in help output  
        self.assertIn("Convert EPUB and PDF comics to CBZ format", result.stdout)
        self.assertIn("--workers", result.stdout)
        self.assertIn("--skip-checks", result.stdout)
        self.assertIn("--dpi", result.stdout)
        self.assertIn("--format", result.stdout)
        self.assertIn("--quality", result.stdout)


if __name__ == '__main__':
    # Run the tests
    unittest.main(verbosity=2)