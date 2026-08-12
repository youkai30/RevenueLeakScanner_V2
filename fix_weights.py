#!/usr/bin/env python
import sys
sys.path.insert(0, '.')

# Read the file
with open('src/evidence/evidence_collector.py', 'r', encoding='latin-1') as f:
    content = f.read()

# Revert weights to original values that made the test pass
# Original: CTA 0.15, Price 0.20, Form 0.15, Viewport 0.10

# Fix Python-evaluated JS scoring (lines 345-379 area)
content = content.replace(
    'if (signals.cta) score += 0.25;',
    'if (signals.cta) score += 0.15;'
)

content = content.replace(
    'if (signals.price) score += 0.15;',
    'if (signals.price) score += 0.20;'
)

content = content.replace(
    'if (signals.form) score += 0.20;',
    'if (signals.form) score += 0.15;'
)

content = content.replace(
    'if (in_vp) score += 0.05;',
    'if (in_vp) score += 0.10;'
)

# Fix JS-evaluated scoring in _scroll_for_social_proof (lines 666-674)
content = content.replace(
    'if (cta_keywords.some(k => txt.includes(k))) score += 0.25;',
    'if (cta_keywords.some(k => txt.includes(k))) score += 0.15;'
)

content = content.replace(
    'if (/\d+[\.,]?\d{1,2}/.test(txt)) score += 0.15;',
    'if (/\d+[\.,]?\d{1,2}/.test(txt)) score += 0.20;'
)

content = content.replace(
    "if (tag === 'form' || cls.includes('product-form') || id_.includes('product-form')) score += 0.20;",
    "if (tag === 'form' || cls.includes('product-form') || id_.includes('product-form')) score += 0.15;"
)

content = content.replace(
    'if (r.width > 10 && r.height > 10 && r.top >= -100 && r.bottom <= (window.innerHeight + 100)) score += 0.10;',
    'if (r.width > 10 && r.height > 10 && r.top >= -100 && r.bottom <= (window.innerHeight + 100)) score += 0.10;'
)

content = content.replace(
    'if (r.left >= -10 && r.right <= (window.innerWidth + 10) && r.top >= -10 && r.bottom <= (window.innerHeight + 10)) score += 0.05;',
    'if (r.left >= -10 && r.right <= (window.innerWidth + 10) && r.top >= -10 && r.bottom <= (window.innerHeight + 10)) score += 0.10;'
)

# Write back with same encoding
with open('src/evidence/evidence_collector.py', 'w', encoding='latin-1') as f:
    f.write(content)

print('Weights reverted to original values')