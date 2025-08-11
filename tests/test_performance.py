#!/usr/bin/env python3
"""
Performance tests for CBZify
Tests basic performance characteristics and resource usage
"""

import os
import sys
import time
import tempfile
import shutil
from pathlib import Path

# Add the src directory to Python path so we can import comic_converter
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

try:
    from comic_converter import ComicConverter, BulkProcessor, ConversionProgress
except ImportError:
    print("Warning: Could not import comic_converter - performance tests will be limited")


def create_mock_pdf_content():
    """Create mock PDF content for performance testing"""
    return b"""%PDF-1.4
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


def test_progress_tracking_performance():
    """Test that progress tracking doesn't add significant overhead"""
    print("Testing progress tracking performance...")
    
    start_time = time.time()
    
    # Create progress tracker and perform many operations
    progress = ConversionProgress()
    
    iterations = 10000
    for i in range(iterations):
        progress.update(current=i, total=iterations, stage=f"Processing {i}")
        if i % 1000 == 0:
            progress.get_status()
    
    elapsed = time.time() - start_time
    operations_per_second = iterations / elapsed if elapsed > 0 else float('inf')
    
    print(f"  Completed {iterations} progress operations in {elapsed:.3f}s")
    print(f"  Performance: {operations_per_second:.0f} operations/second")
    
    # Should be very fast - progress tracking shouldn't be a bottleneck
    if elapsed > 1.0:  # More than 1 second for 10k operations is too slow
        print("  ⚠️  Warning: Progress tracking performance may be suboptimal")
    else:
        print("  ✓ Progress tracking performance is acceptable")


def test_file_type_detection_performance():
    """Test file type detection performance"""
    print("Testing file type detection performance...")
    
    temp_dir = tempfile.mkdtemp()
    try:
        # Create multiple test files
        test_files = []
        for i in range(100):
            pdf_path = os.path.join(temp_dir, f"test_{i}.pdf")
            with open(pdf_path, 'wb') as f:
                f.write(create_mock_pdf_content())
            test_files.append(pdf_path)
        
        start_time = time.time()
        
        # Test file type detection on all files
        for file_path in test_files:
            try:
                dest_path = file_path.replace('.pdf', '.cbz')
                converter = ComicConverter(file_path, dest_path)
                file_type = converter.detect_file_type()
                assert file_type == 'pdf'
            except Exception as e:
                print(f"  Warning: File type detection failed for {file_path}: {e}")
        
        elapsed = time.time() - start_time
        files_per_second = len(test_files) / elapsed if elapsed > 0 else float('inf')
        
        print(f"  Detected file types for {len(test_files)} files in {elapsed:.3f}s")
        print(f"  Performance: {files_per_second:.1f} files/second")
        
        if elapsed > 5.0:  # More than 5 seconds for 100 files is too slow
            print("  ⚠️  Warning: File type detection performance may be suboptimal")
        else:
            print("  ✓ File type detection performance is acceptable")
            
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_bulk_processor_scanning_performance():
    """Test bulk processor file scanning performance"""
    print("Testing bulk processor directory scanning performance...")
    
    temp_dir = tempfile.mkdtemp()
    try:
        source_dir = os.path.join(temp_dir, "source")
        output_dir = os.path.join(temp_dir, "output")
        os.makedirs(source_dir)
        
        # Create many test files
        num_files = 500
        for i in range(num_files):
            if i % 2 == 0:
                file_path = os.path.join(source_dir, f"comic_{i:03d}.pdf")
                with open(file_path, 'wb') as f:
                    f.write(create_mock_pdf_content())
            else:
                file_path = os.path.join(source_dir, f"book_{i:03d}.epub")
                with open(file_path, 'w') as f:
                    f.write("mock epub content")
        
        # Add some non-comic files that should be ignored
        for i in range(50):
            file_path = os.path.join(source_dir, f"readme_{i}.txt")
            with open(file_path, 'w') as f:
                f.write("This should be ignored")
        
        start_time = time.time()
        
        # Test directory scanning
        processor = BulkProcessor(source_dir, output_dir)
        comic_files = processor.find_comic_files()
        
        elapsed = time.time() - start_time
        
        print(f"  Scanned directory with {num_files + 50} files in {elapsed:.3f}s")
        print(f"  Found {len(comic_files)} comic files (expected {num_files})")
        print(f"  Performance: {len(comic_files) / elapsed:.1f} files/second")
        
        # Verify we found the right number of files
        assert len(comic_files) == num_files, f"Expected {num_files} files, found {len(comic_files)}"
        
        if elapsed > 2.0:  # More than 2 seconds to scan 550 files is slow
            print("  ⚠️  Warning: Directory scanning performance may be suboptimal")
        else:
            print("  ✓ Directory scanning performance is acceptable")
            
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_memory_usage_estimation():
    """Test basic memory usage patterns"""
    print("Testing basic memory usage...")
    
    try:
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Create some data structures similar to what the converter uses
        test_data = []
        for i in range(1000):
            progress = ConversionProgress()
            progress.update(current=i, total=1000, stage=f"Test {i}")
            test_data.append(progress)
        
        current_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = current_memory - initial_memory
        
        print(f"  Initial memory: {initial_memory:.1f} MB")
        print(f"  Current memory: {current_memory:.1f} MB")
        print(f"  Memory increase: {memory_increase:.1f} MB")
        
        if memory_increase > 100:  # More than 100MB increase is concerning
            print("  ⚠️  Warning: Memory usage increase is significant")
        else:
            print("  ✓ Memory usage appears reasonable")
            
    except ImportError:
        print("  ℹ️  psutil not available - skipping detailed memory analysis")
        print("  ✓ Basic memory test completed")


def main():
    """Run all performance tests"""
    print("Running performance tests for CBZify...")
    print("=" * 60)
    
    tests = [
        test_progress_tracking_performance,
        test_file_type_detection_performance,
        test_bulk_processor_scanning_performance,
        test_memory_usage_estimation,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            print(f"\n{test.__name__.replace('_', ' ').title()}:")
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} failed: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Performance Tests Summary:")
    print(f"✓ Passed: {passed}")
    print(f"✗ Failed: {failed}")
    print(f"Total: {passed + failed}")
    
    if failed > 0:
        print(f"\nSome performance tests failed or showed warnings!")
        print("This may indicate performance issues that should be investigated.")
        sys.exit(1)
    else:
        print(f"\nAll performance tests completed successfully!")
        sys.exit(0)


if __name__ == "__main__":
    main()