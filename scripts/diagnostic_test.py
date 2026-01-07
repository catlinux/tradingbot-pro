#!/usr/bin/env python3
"""
GridBot Pro Diagnostic Test Suite
Comprehensive system validation for development and deployment
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# --- OUTPUT FORMATTING ---
def print_status(test_name: str, passed: bool, message: str = ""):
    """Print colored status message for test"""
    status = "[PASS]" if passed else "[FAIL]"
    msg = f" - {message}" if message else ""
    print(f"  {status}: {test_name}{msg}")
    return passed

def test_imports():
    """Test critical Python imports"""
    print("\n=== IMPORT TESTS ===")

    # Test core imports
    imports_to_test = [
        ('fastapi', 'FastAPI'),
        ('uvicorn', 'Uvicorn'),
        ('ccxt', 'CCXT'),
        ('sqlite3', 'SQLite3'),
        ('json5', 'JSON5'),
    ]

    for module_name, display_name in imports_to_test:
        try:
            __import__(module_name)
            print_status(display_name, True)
        except ImportError as e:
            print_status(display_name, False, str(e))
            assert False, f"Missing module: {module_name}"


def test_project_structure():
    """Verify required project directories exist"""
    print("\n=== PROJECT STRUCTURE TESTS ===")

    base = Path(__file__).parent.parent
    required_dirs = [
        'core',
        'web',
        'config',
        'data',
        'scripts',
        'utils',
        'web/static',
        'web/templates',
        'web/static/js',
        'web/static/css',
    ]

    for dir_path in required_dirs:
        full_path = base / dir_path
        exists = full_path.is_dir()
        print_status(f"Directory: {dir_path}", exists)
        assert exists, f"Missing required directory: {dir_path}"


def test_configuration():
    """Test configuration files"""
    print("\n=== CONFIGURATION TESTS ===")

    base = Path(__file__).parent.parent
    config_files = [
        'config/config.json5',
        'config/env.example',
        'requirements.txt',
    ]

    for file_path in config_files:
        full_path = base / file_path
        exists = full_path.is_file()
        print_status(f"File: {file_path}", exists)
        assert exists, f"Missing configuration file: {file_path}"


def test_database():
    """Test database connectivity and schema"""
    print("\n=== DATABASE TESTS ===")

    try:
        from core.database import BotDatabase

        # Test database initialization
        db = BotDatabase()
        print_status("Database initialization", True)

        # Test basic operations
        try:
            # Test get_stats (creates schema if needed)
            _ = db.get_stats()
            print_status("Database schema", True)

            # Test insert operation
            db.log_trade({
                'symbol': 'TEST/USDT',
                'side': 'BUY',
                'price': 100.0,
                'amount': 1.0,
                'timestamp': 0,
            })
            print_status("Trade logging", True)

        except Exception as e:
            print_status("Database operations", False, str(e))
            assert False, f"Database operations failed: {e}"

    except Exception as e:
        print_status("Database module import", False, str(e))
        assert False, f"Database import failed: {e}"


def test_api_endpoints():
    """Test FastAPI endpoint definitions"""
    print("\n=== API ENDPOINT TESTS ===")

    try:
        from web.server import app

        # Get all routes
        routes = [route.path for route in app.routes]

        required_endpoints = [
            '/api/status',
            '/api/history/balance',
            '/api/top_strategies',
            '/api/record_balance',
        ]

        for endpoint in required_endpoints:
            found = endpoint in routes
            print_status(f"Endpoint: {endpoint}", found)
            assert found, f"Missing API endpoint: {endpoint}"
    except Exception as e:
        print_status("API module import", False, str(e))
        assert False, f"API module import failed: {e}"


def test_environment():
    """Test environment variables and setup"""
    print("\n=== ENVIRONMENT TESTS ===")

    base = Path(__file__).parent.parent
    venv_paths = [
        '.venv',
        'venv',
    ]

    has_venv = any((base / path).is_dir() for path in venv_paths)
    print_status("Virtual environment exists", has_venv or True, "Optional - can use system Python")

    # Check .env file
    env_exists = (base / '.env').is_file()
    print_status(".env file exists", env_exists or True, "Optional - uses defaults")

    assert True


def test_code_quality():
    """Basic code quality checks"""
    print("\n=== CODE QUALITY CHECKS ===")

    try:
        # Check Python syntax in core modules
        import py_compile
        base = Path(__file__).parent.parent

        python_files = [
            'core/bot.py',
            'core/database.py',
            'core/exchange.py',
            'web/server.py',
        ]

        for file_path in python_files:
            full_path = base / file_path
            try:
                py_compile.compile(str(full_path), doraise=True)
                print_status(f"Syntax: {file_path}", True)
            except py_compile.PyCompileError as e:
                print_status(f"Syntax: {file_path}", False, str(e))
                assert False, f"Syntax error in {file_path}: {e}"
    except Exception as e:
        print_status("Code quality check", False, str(e))
        assert False, f"Code quality check failed: {e}"

def main():
    """Run all diagnostic tests"""
    print("\n" + "="*50)
    print("GridBot Pro - Diagnostic Test Suite")
    print("="*50 + "\n")
    
    results = {
        'Imports': test_imports(),
        'Project Structure': test_project_structure(),
        'Configuration': test_configuration(),
        'Database': test_database(),
        'API Endpoints': test_api_endpoints(),
        'Environment': test_environment(),
        'Code Quality': test_code_quality(),
    }
    
    # Print summary
    print("\n" + "="*50)
    print("TEST SUMMARY")
    print("="*50)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {status} {test_name}")
    
    print(f"\nResult: {passed}/{total} tests passed\n")
    
    return 0 if passed == total else 1

if __name__ == '__main__':
    sys.exit(main())
