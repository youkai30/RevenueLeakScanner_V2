import json
import pathlib
from bs4 import BeautifulSoup

html_path = r"C:\Users\Admin\.gemini\antigravity\brain\7ca45097-328e-4acd-9dc3-1db09174f3ca\.system_generated\steps\18477\content.md"
with open(html_path, "r", encoding="utf-8") as f:
    content = f.read()

soup = BeautifulSoup(content, "html.parser")

print("=== ALL FORMS ===")
for i, form in enumerate(soup.find_all("form")):
    print(f"Form {i}:")
    print(f"  class: {form.get('class')}")
    print(f"  action: {form.get('action')}")
    print(f"  id: {form.get('id')}")

print("\n=== HEADINGS ===")
for h in soup.find_all(["h1", "h2", "h3"]):
    text = h.get_text().strip()
    if text:
        print(f"{h.name}: class={h.get('class')} text={text[:100]}")
