import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

from v2.ai_model import test_connection
ok, r = test_connection()
print(f"Connection: {'OK' if ok else 'FAILED'}")
if isinstance(r, dict):
    print(f"Model: {r.get('model', 'unknown')}")
    print(f"Response: {r.get('response', '')[:200]}")
else:
    print(f"Response: {str(r)[:200]}")
