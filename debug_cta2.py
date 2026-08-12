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
    
    # Test the scoring
    page.evaluate("""
        () => {
            const cta_keywords = ['add to cart', 'add to bag', 'buy now', 'select size', 'checkout'];
            
            const getElementText = (el) => {
                let text = (el.textContent || el.innerText || "").toLowerCase().trim();
                
                const inputs = el.querySelectorAll('input');
                inputs.forEach(input => {
                    const inputValue = (input.value || "").toLowerCase().trim();
                    if (inputValue && inputValue.length > 2) {
                        text += " " + inputValue;
                    }
                });
                
                const buttons = el.querySelectorAll('button');
                buttons.forEach(btn => {
                    const btnText = (btn.textContent || btn.innerText || "").toLowerCase().trim();
                    if (btnText && btnText.length > 2) {
                        text += " " + btnText;
                    }
                });
                
                const ariaLabel = (el.getAttribute("aria-label") || "").toLowerCase().trim();
                if (ariaLabel && ariaLabel.length > 2) {
                    text += " " + ariaLabel;
                }
                
                const elTitle = (el.getAttribute("title") || "").toLowerCase().trim();
                if (elTitle && elTitle.length > 2) {
                    text += " " + elTitle;
                }
                
                return text;
            };
            
            const el = document.querySelector(".product-form");
            if (el) {
                const txt = (el.textContent || "").toLowerCase();
                const elementTxt = getElementText(el);
                // Output via console.log will appear in pytest output
                console.log("form textContent:", JSON.stringify(txt));
                console.log("elementTxt (new):", JSON.stringify(elementTxt));
                
                const signals = { cta: false, price: false, variant: false, form: false, visible: false, coherence: false };
                signals.cta = cta_keywords.some(k => elementTxt.includes(k));
                if (signals.cta) { console.log("CTA signal FIRED with new method"); }
                else { console.log("CTA signal NOT fired with new method"); }
                
                signals.cta_old = cta_keywords.some(k => txt.includes(k));
                if (signals.cta_old) { console.log("CTA signal OLD method fired"); }
                else { console.log("CTA signal OLD method NOT fired"); }
            }
        }
    """)
    print('Script completed - check pytest output for console.log messages')
    context.close()
    browser.close()