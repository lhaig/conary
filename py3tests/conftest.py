import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# The rebuilt SAS harness (testrunner, testutils) lives in testharness/.
HARNESS = os.path.join(ROOT, 'testharness')
if HARNESS not in sys.path:
    sys.path.insert(0, HARNESS)
