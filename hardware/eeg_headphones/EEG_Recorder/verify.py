"""
Verification script to test all application components.
"""

import sys
import os

# Setup paths
sys.path.insert(0, '.')
sys.path.insert(0, '..')

def test_imports():
    """Test all module imports."""
    print("\n=== IMPORT VERIFICATION ===\n")
    
    tests = [
        ("Signal Processor", "from core.signal_processor import SignalProcessor"),
        ("Device Manager", "from core.device_manager import DeviceManager"),
        ("Calibration Manager", "from core.calibration_manager import CalibrationManager"),
        ("Recording Worker", "from core.recording_worker import RecordingWorker"),
        ("Export Manager", "from core.export_manager import ExportManager"),
        ("GUI Main Window", "import os; os.environ['QT_QPA_PLATFORM'] = 'offscreen'; from ui.main_window import MainWindow"),
    ]
    
    passed = 0
    failed = 0
    
    for name, import_stmt in tests:
        try:
            exec(import_stmt)
            print(f"✓ {name:30} - OK")
            passed += 1
        except Exception as e:
            print(f"✗ {name:30} - FAILED: {e}")
            failed += 1
    
    print(f"\nResults: {passed}/{len(tests)} passed\n")
    return failed == 0

def test_device_manager():
    """Test DeviceManager functionality."""
    print("\n=== DEVICE MANAGER TEST ===\n")
    
    try:
        from core.device_manager import DeviceManager
        
        mgr = DeviceManager()
        print("✓ DeviceManager instantiated")
        
        assert hasattr(mgr, 'scan_devices'), "Missing scan_devices method"
        print("✓ scan_devices method exists")
        
        assert hasattr(mgr, 'connect_device'), "Missing connect_device method"
        print("✓ connect_device method exists")
        
        assert mgr.is_connected() == False, "Should not be connected initially"
        print("✓ Initial state: disconnected")
        
        print("\n✓ DeviceManager: OK\n")
        return True
    except Exception as e:
        print(f"\n✗ DeviceManager test failed: {e}\n")
        return False

def test_calibration_manager():
    """Test CalibrationManager functionality."""
    print("\n=== CALIBRATION MANAGER TEST ===\n")
    
    try:
        from core.calibration_manager import CalibrationManager
        
        mgr = CalibrationManager()
        print("✓ CalibrationManager instantiated")
        
        assert not mgr.is_calibrating, "Should not start calibrating"
        print("✓ Initial state: not calibrating")
        
        mgr.start_calibration()
        assert mgr.is_calibrating, "Should be calibrating after start"
        print("✓ start_calibration works")
        
        # Simulate impedance data
        class FakeResistData:
            Ch1, Ch2, Ch3, Ch4 = 4500, 4600, 18000, 5200
        
        for _ in range(10):
            mgr.add_resistance_data(FakeResistData())
        
        mgr.stop_calibration()
        assert not mgr.is_calibrating, "Should stop calibrating"
        print("✓ stop_calibration works")
        
        results = mgr.get_calibration_results()
        assert results is not None, "Should have results"
        print("✓ Calibration results available")
        
        assert 'channels' in results, "Results should have channels"
        print(f"✓ Analyzed {len(results['channels'])} channels")
        
        print("\n✓ CalibrationManager: OK\n")
        return True
    except Exception as e:
        print(f"\n✗ CalibrationManager test failed: {e}\n")
        return False

def test_signal_processor():
    """Test SignalProcessor functionality."""
    print("\n=== SIGNAL PROCESSOR TEST ===\n")
    
    try:
        from core.signal_processor import SignalProcessor
        import numpy as np
        
        proc = SignalProcessor()
        print("✓ SignalProcessor instantiated")
        
        # Test filtering
        test_data = np.random.randn(10)
        filtered = proc.apply_bandpass_filter(0, test_data)
        assert filtered is not None, "Filter should return data"
        print("✓ Bandpass filter works")
        
        # Test quality calculation
        impedances = [4500, 4600, 18000, 5200]
        quality = proc.calculate_impedance_quality(impedances)
        assert len(quality) == 4, "Should calculate quality for 4 channels"
        print("✓ Impedance quality calculation works")
        
        print("\n✓ SignalProcessor: OK\n")
        return True
    except Exception as e:
        print(f"\n✗ SignalProcessor test failed: {e}\n")
        return False

def test_export_manager():
    """Test ExportManager functionality."""
    print("\n=== EXPORT MANAGER TEST ===\n")
    
    try:
        from core.export_manager import ExportManager
        from pathlib import Path
        
        # Use temp directory for testing
        test_dir = Path("/tmp/eeg_test") if os.name != 'nt' else Path("C:\\Temp\\eeg_test")
        
        mgr = ExportManager(str(test_dir))
        print("✓ ExportManager instantiated")
        
        session_dir = mgr.create_session_directory("test_session")
        assert session_dir.exists(), "Session directory should be created"
        print(f"✓ Session directory created: {session_dir.name}")
        
        # Cleanup
        import shutil
        if session_dir.parent.exists():
            try:
                shutil.rmtree(session_dir.parent)
            except:
                pass
        
        print("\n✓ ExportManager: OK\n")
        return True
    except Exception as e:
        print(f"\n✗ ExportManager test failed: {e}\n")
        return False

def main():
    """Run all tests."""
    print("\n" + "="*50)
    print("  EEG + Voice Recording Application")
    print("  Verification Suite")
    print("="*50)
    
    all_pass = True
    
    # Core import tests
    all_pass &= test_imports()
    
    # Component tests
    all_pass &= test_device_manager()
    all_pass &= test_calibration_manager()
    all_pass &= test_signal_processor()
    all_pass &= test_export_manager()
    
    # Summary
    print("="*50)
    if all_pass:
        print("\n✓ ALL TESTS PASSED - Application ready!")
        print("\nTo start the application, run:")
        print("  python app.py")
        print("  OR")
        print("  powershell .\\run.ps1")
        print("  OR")
        print("  run.bat\n")
        sys.exit(0)
    else:
        print("\n✗ SOME TESTS FAILED - Check errors above\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
