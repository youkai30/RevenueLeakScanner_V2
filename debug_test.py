import sys
sys.path.insert(0, '.')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width': 375, 'height': 667})
    page = context.new_page()
    html = """<html>
<body style="margin: 0; padding: 0; height: 3000px;">
    <div style="height: 1000px;">Top Spacer</div>
    <h1 style="height: 100px;">My Product Name</h1>
    <form class="product-form" style="height: 200px; background: blue;">
        <input type="submit" value="Add to Cart" />
    </form>
</body>
</html>"""
    page.set_content(html)
    
    # Test candidate generation
    candidates = page.evaluate("""
        () => {
            const isHeaderOrDrawer = (el) => {
                let parent = el;
                while (parent) {
                    const tag = parent.tagName;
                    const cls = (typeof parent.className === 'string' ? parent.className : "").toLowerCase();
                    if (tag === 'HEADER' || tag === 'NAV' ||
                        cls.includes('header') || cls.includes('nav') || cls.includes('drawer')) {
                        return true;
                    }
                    parent = parent.parentElement;
                }
                return false;
            };

            const candidates = [];
            const forms = Array.from(document.querySelectorAll('form'));
            forms.forEach(f => {
                const txt = (f.textContent || '').toLowerCase();
                const cls = (f.className || '').toLowerCase();
                const id_ = (f.id || '').toLowerCase();
                const rect = f.getBoundingClientRect();
                const visible = rect.width > 20 && rect.height > 50;
                const is_purchase = /add to cart|buy now|checkout|cart/.test(txt) ||
                                   /product-form/.test(cls) ||
                                   /add-to-cart/.test(id_);
                if (visible && is_purchase && !isHeaderOrDrawer(f)) {
                    candidates.push({ rect: {top: rect.top, left: rect.left, width: rect.width, height: rect.height}, txt: txt, cls: cls });
                }
            });
            return candidates;
        }
    """)
    print('Candidates:', candidates)
    context.close()
    browser.close()