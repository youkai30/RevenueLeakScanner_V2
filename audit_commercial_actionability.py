"""
audit_commercial_actionability.py — Commercial Actionability Auditor for Leads
"""
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
LEADS_JSON_PATH = PROJECT_ROOT / "storage" / "leads" / "leads.json"

def main():
    if not LEADS_JSON_PATH.exists():
        print(f"ERROR: {LEADS_JSON_PATH} does not exist. Run the scanner first.")
        return

    with open(LEADS_JSON_PATH, "r", encoding="utf-8") as f:
        leads = json.load(f)

    print(f"Loaded {len(leads)} leads from leads.json")

    highly_actionable = []
    actionable_via_socials = []
    manual_research = []

    for lead in leads:
        domain = lead.get("domain")
        company = lead.get("company_name") or domain
        primary_opp = lead.get("primary_opportunity")
        problem = lead.get("exact_problem")
        email = lead.get("contact_email")
        contact_page = lead.get("contact_page")
        insta = lead.get("instagram_url")
        fb = lead.get("facebook_url")
        screenshot = lead.get("screenshot_evidence_path")
        orig_class = lead.get("lead_class")

        # Skip failed/Class C leads
        if "C — NOT" in str(orig_class):
            continue

        # Evaluate contacts
        has_direct_contact = bool(email or contact_page)
        has_social_contact = bool(insta or fb)

        lead_summary = {
            "domain": domain,
            "company": company,
            "primary_opportunity": primary_opp,
            "problem": problem,
            "email": email,
            "contact_page": contact_page,
            "instagram": insta,
            "facebook": fb,
            "screenshot": screenshot
        }

        if has_direct_contact:
            highly_actionable.append(lead_summary)
        elif has_social_contact:
            actionable_via_socials.append(lead_summary)
        else:
            manual_research.append(lead_summary)

    # Generate Markdown Output
    report_lines = []
    report_lines.append("# COMMERCIAL ACTIONABILITY AUDIT REPORT")
    report_lines.append(f"\nTotal Leads Inspected: {len(leads)}")
    report_lines.append(f"* **Highly Actionable (Direct Contact Email/Page + Evidence)**: {len(highly_actionable)}")
    report_lines.append(f"* **Actionable via Socials (Instagram/Facebook DM + Evidence)**: {len(actionable_via_socials)}")
    report_lines.append(f"* **Requires Manual Research (Evidence but no contacts found)**: {len(manual_research)}")

    report_lines.append("\n## 1. Highly Actionable Leads")
    report_lines.append("| Brand | Domain | Primary Opportunity | Direct Contact Channel | Screenshot Evidence |")
    report_lines.append("| :--- | :--- | :--- | :--- | :--- |")
    for l in highly_actionable:
        contact_str = f"Email: {l['email']}" if l['email'] else f"Page: [Link]({l['contact_page']})"
        screenshot_basename = Path(l['screenshot']).name if l['screenshot'] else "None"
        report_lines.append(f"| {l['company']} | {l['domain']} | `{l['primary_opportunity']}` | {contact_str} | {screenshot_basename} |")

    report_lines.append("\n## 2. Actionable via Social DMs")
    report_lines.append("| Brand | Domain | Primary Opportunity | Social Channels | Screenshot Evidence |")
    report_lines.append("| :--- | :--- | :--- | :--- | :--- |")
    for l in actionable_via_socials:
        social_links = []
        if l['instagram']:
            social_links.append(f"[Insta]({l['instagram']})")
        if l['facebook']:
            social_links.append(f"[FB]({l['facebook']})")
        social_str = ", ".join(social_links)
        screenshot_basename = Path(l['screenshot']).name if l['screenshot'] else "None"
        report_lines.append(f"| {l['company']} | {l['domain']} | `{l['primary_opportunity']}` | {social_str} | {screenshot_basename} |")

    report_lines.append("\n## 3. Leads Requiring Manual Contact Research")
    report_lines.append("| Brand | Domain | Primary Opportunity | Status | Screenshot Evidence |")
    report_lines.append("| :--- | :--- | :--- | :--- | :--- |")
    for l in manual_research:
        screenshot_basename = Path(l['screenshot']).name if l['screenshot'] else "None"
        report_lines.append(f"| {l['company']} | {l['domain']} | `{l['primary_opportunity']}` | Needs email lookup | {screenshot_basename} |")

    # Write report
    report_content = "\n".join(report_lines)
    report_path = PROJECT_ROOT / "storage" / "leads" / "audit" / "commercial_actionability_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    print(f"Audit completed successfully! Report generated at: {report_path}")
    print(f"- Highly Actionable: {len(highly_actionable)}")
    print(f"- Actionable via Socials: {len(actionable_via_socials)}")
    print(f"- Manual Research Required: {len(manual_research)}")


if __name__ == "__main__":
    main()
