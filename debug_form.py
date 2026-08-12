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
    
    # Check form text content
    form = page.query_selector('.product-form')
    if form:
        txt = (form.textContent or '').lower()
        print(f'form.textContent: {repr(txt)}')
        cls = (form.className or '').lower()
        print(f'form.className: {repr(cls)}')
        # Check input
        input_el = form.query_selector('input')
        if input_el:
            inp_val = input_el.get_attribute('value')
            inp_txt = (input_el.textContent or inp_val or '').lower()
            print(f'input value attr: {repr(inp_val)}')
            print(f'input textContent: {repr(inp_txt)}')
    
    context.close()
    browser.close()