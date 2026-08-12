#!/usr/bin/env python
import sys
sys.path.insert(0, '.')

# Read the file as bytes to avoid encoding issues
with open('src/evidence/evidence_collector.py', 'rb') as f:
    content = f.read()

# Search for the candidate containers section - looking for the form is_purchase check
# We'll search for "const is_purchase" in the text
try:
    text = content.decode('latin-1')
    # Find all occurrences of is_purchase
    import re
    for m in re.finditer(r'const is_purchase', text):
        start = m.start()
        # Get 300 chars after
        end = min(start + 300, len(text))
        print(f"Found at position {start}:")
        print(text[start:end])
        print("---")
except Exception as e:
    print(f"Error: {e}")
    # Fallback: just print lines with is_purchase
    lines = content.split(b'\n')
    for i, line in enumerate(lines):
        if b'is_purchase' in line:
            print(f"Line {i+1}: {line.decode('latin-1', errors='replace')[:200]}")
PYEOF