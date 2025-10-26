import os
import sys
import importlib.util
import argparse
import traceback


def run_all_tests():
    """
    Dynamically discovers and runs all test scripts in the 'tests' directory.
    """
    tests_dir = os.path.dirname(__file__)
    # Find all files named 'test_*.py' but exclude this runner script.
    test_files = [
        f
        for f in os.listdir(tests_dir)
        if f.startswith("test_") and f.endswith(".py")
    ]

    if not test_files:
        print("No test files found (e.g., 'test_*.py').")
        return True

    total_tests = len(test_files)
    passed_tests = 0

    for test_file in sorted(test_files):
        test_name = os.path.splitext(test_file)[0].replace("test_", "").capitalize()
        print(f"--- Running Test: {test_name} ---")

        try:
            # Dynamically import the test module
            module_name = os.path.splitext(test_file)[0]
            spec = importlib.util.spec_from_file_location(
                module_name, os.path.join(tests_dir, test_file)
            )
            assert spec is not None
            assert spec.loader is not None
            test_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(test_module)

            # Run the test and get the result
            test_module.run_test()
            print(f"✅ {test_name} is working.")
            passed_tests += 1
        except Exception:
            print(f"❌ {test_name} test failed!")
            traceback.print_exc(file=sys.stdout)
        finally:
            print("-" * (len(test_name) + 18))

    print(f"\nTest Summary: {passed_tests}/{total_tests} passed.")
    return passed_tests == total_tests


if __name__ == "__main__":
    if run_all_tests():
        sys.exit(0)
    else:
        sys.exit(1)
