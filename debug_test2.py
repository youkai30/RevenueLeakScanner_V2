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
    
    # Test candidate scoring
    score_result = page.evaluate("""
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

            const cta_keywords = ["add to cart", "add to bag", "buy now", "select size", "checkout"];
            const forms = Array.from(document.querySelectorAll('form'));
            let bestScore = 0;
            let bestEl = null;
            
            forms.forEach(f => {
                const txt = (f.textContent || '').toLowerCase();
                const cls = (f.className || '').toLowerCase();
                const id_ = (f.id || '').toLowerCase();
                const tag = f.tagName.toLowerCase();
                const rect = f.getBoundingClientRect();
                const visible = rect.width > 20 && rect.height > 50;
                const is_purchase = /add to cart|buy now|checkout|cart/.test(txt) ||
                                   /product-form/.test(cls) ||
                                   /add-to-cart/.test(id_);
                if (visible && is_purchase && !isHeaderOrDrawer(f)) {
                    let score = 0;
                    if (cta_keywords.some(k => txt.includes(k))) score += 0.25;
                    if (/\d+[\.,]?\d{1,2}/.test(txt)) score += 0.15;
                    if (["variant", "selector", "size", "color"].some(k => cls.includes(k) || id_.includes(k))) score += 0.10;
                    if (tag === 'form' || cls.includes('product-form') || id_.includes('product-form')) score += 0.20;
                    if (r.width > 10 && r.height > 10 && r.top >= -100 && r.bottom <= (window.innerHeight + 100)) score += 0.10;
                    if (cta_keywords.some(k => txt.includes(k)) && /\d+[\.,]?\d{1,2}/.test(txt) &&
                        ["variant", "selector", "size", "color"].some(k => cls.includes(k) || id_.includes(k))) score += 0.10;
                    if (r.left >= -10 && r.right <= (window.innerWidth + 10) && r.top >= -10 && r.bottom <= (window.innerHeight + 10)) score += 0.05;
                    if (isHeaderOrDrawer(f)) score -= 0.30;
                    score = Math.max(0.0, Math.min(1.0, score));
                    if (score > bestScore) {
                        bestScore = score;
                        bestEl = f;
                    }
                }
            });
            
            return {bestScore: bestScore, bestEl: bestEl ? 'found' : null};
        }
    """)
    print('Score result:', score_result)
    context.close()
    browser.close()