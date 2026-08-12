# 02 Business Model — Revenue Leak Scanner V2

## 1. Executive Commercial Summary

Revenue Leak Scanner V2 is architected specifically to power the outbound sales and client acquisition engines of E-Commerce Growth and CRO (Conversion Rate Optimization) Agencies.

```
+-----------------------------------------------------------------------------------+
|                            COMMERCIAL VALUE PROPOSITION                           |
+-----------------------------------------------------------------------------------+
|  "We transform unverified cold prospect outreach into high-converting, trust-    |
|   anchored sales opportunities by equipping agencies with verifiable, dollar-     |
|   quantified proof of lost e-commerce revenue."                                   |
+-----------------------------------------------------------------------------------+
```

Instead of positioning the scanner as a standalone developer diagnostic tool, Version 2 treats the scanner as a **Commercial Weaponization Engine**. It bridges the gap between raw web scraping and agency revenue generation by turning technical storefront flaws into financial opportunity metrics ($/month lost).

---

## 2. Target Commercial Personas & Needs

```
+------------------+----------------------------------+-----------------------------------+
| Persona          | Role & Primary Objective         | Core Operational Need             |
+------------------+----------------------------------+-----------------------------------+
| Agency Founder / | Scale agency ARR; increase cold  | High-volume lead lists with high  |
| Managing Director| email reply rates & booked sales | response probability and zero    |
|                  | calls.                           | risk of false positive claims.    |
|                  |                                  |                                   |
| Business Dev /   | Book meetings with brand CMOs/   | 1-click cold email image teasers  |
| SDR Team         | E-Commerce Directors on LinkedIn | and short 1-page executive audit  |
|                  | and Email.                       | PDFs displaying dollar loss.      |
|                  |                                  |                                   |
| Account Exec /   | Close prospects during discovery | Interactive audit benchmarks that |
| Lead CRO Strategist| calls and pitch presentations. | prove lost revenue and quantify   |
|                  |                                  | project ROI ($/mo recovery).      |
+------------------+----------------------------------+-----------------------------------+
```

---

## 3. Commercial Deliverable Formats Matrix

The V2 architecture supports three distinct, tier-aligned commercial output artifacts tailored to the agency sales funnel:

```
                  +----------------------------------------------------+
                  |               AGENCY SALES FUNNEL                  |
                  +----------------------------------------------------+
                                            │
           1. Cold Outreach Stage           │ Output: Cold Pitch Teaser Image
                                            ▼
           2. Meeting Booking Stage         │ Output: 1-Page Executive Audit PDF
                                            ▼
           3. Strategy Pitch & Close        │ Output: Interactive Multi-Store Benchmark
```

| Deliverable Format | Primary Target Audience | File / Asset Spec | Core Commercial Content |
|---|---|---|---|
| **1. Cold Pitch Teaser Image** | Prospecting SDRs (Email/LinkedIn) | Single Cropped PNG (`teaser.png`) | Visually highlighted out-of-stock variant + callout arrow + estimated monthly lost revenue. |
| **2. Executive Audit PDF** | E-Commerce Founder / CMO | 1-Page Clean PDF (`audit.pdf`) | Single-store analysis: lost dollar calculation, CRO stack detection, and back-in-stock gap. |
| **3. Multi-Store Benchmark** | Agency Strategy & Pitch Team | Interactive Standalone HTML | Comparative category audit demonstrating agency authority and brand benchmark gaps. |

---

## 4. Monetization & SaaS Packaging Architecture

Revenue Leak Scanner V2 supports three tier-based commercial licensing models:

```
+-----------------------------------------------------------------------------------+
|                          SAAS TIER & PACKAGING ARCHITECTURE                       |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  TIER 1: SDR OUTBOUND ENGINE (Pay-Per-Verified-Leak / Credit Model)               |
|  - Designed for boutique agencies running targeted cold outreach.                 |
|  - Deliverables: Single-Store Teaser Images & Executive PDFs.                     |
|                                                                                   |
|  TIER 2: AGENCY PROSPECTING PLATFORM (Monthly Recurring Subscription)            |
|  - Designed for mid-market CRO agencies scanning 250–1,000 stores per month.     |
|  - Features: Master Lead Dashboard, App Stack Filtering, Dollar Impact Calculator.|
|                                                                                   |
|  TIER 3: ENTERPRISE WHITE-LABEL TENANT (Custom Enterprise SLA)                    |
|  - Designed for large growth networks and Shopify Plus Partner Agencies.          |
|  - Features: Custom Domain Branding, White-Label PDF Templates, CRM API Push.    |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

---

## 5. Agency Sales Funnel Integration

```
+-----------------------+      +-----------------------+      +-----------------------+
|  STAGE 1: DISCOVERY   |      |   STAGE 2: OUTREACH   |      |    STAGE 3: CLOSING   |
+-----------------------+      +-----------------------+      +-----------------------+
| Bulk Scanner executes | ───► | SDR attaches 1-click  | ───► | AE presents 1-Page    |
| scan on 500 target    |      | Teaser Image to email |      | Executive PDF or      |
| Shopify stores.       |      | showing $ lost/month. |      | Multi-Store Benchmark |
+-----------------------+      +-----------------------+      | showing recovery ROI. |
            │                              │                  +-----------------------+
            ▼                              ▼                              │
+-----------------------+      +-----------------------+                  ▼
| System filters top 5% |      | Prospect replies:     |      +-----------------------+
| verified leaks with   |      | "How did you find     |      | Deal Signed:          |
| highest lost revenue. |      | this data?"           |      | Retainer Closed ($5k+) |
+-----------------------+      +-----------------------+      +-----------------------+
```

---

## 6. Financial Impact Formula Specification

To move from qualitative badges to quantitative financial metrics, Version 2 implements a standardized, rule-based **Lost Revenue Estimation Engine**:

$$\text{Monthly Lost Revenue (\$)} = \text{Est. Monthly Traffic} \times \text{OOS Variant Frequency (\%)} \times \text{Baseline CR (\%)} \times \text{Category AOV (\$)}$$

```
+-----------------------------------------------------------------------------------+
|                       FINANCIAL IMPACT CALCULATION PARAMETERS                      |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  - Est. Monthly Traffic: Derived via BuiltWith / Tranco rank estimation bucket.   |
|  - OOS Variant Frequency: Scraped ratio of out-of-stock SKUs to total SKUs (e.g. 15%)|
|  - Baseline Conversion Rate (CR): Standard category benchmark (default: 2.0%).   |
|  - Category Average Order Value (AOV): Extracted product price or category baseline|
|                                                                                   |
|  EXAMPLE CALCULATION (TOMS Footwear):                                             |
|  120,000 visits/mo * 12% OOS * 2.0% CR * $85.00 AOV = $24,480 / month lost revenue |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

---

## 7. Commercial Non-Functional Requirements (NFRs)

1. **Zero False Positive Guarantee:** A single false positive claim destroys agency credibility. All reported revenue leaks MUST pass 100% of automated rule assertions before inclusion in an outreach package.
2. **Sub-3-Second Prospect Comprehension:** Any SDR or brand founder looking at an outreach asset MUST understand the exact revenue leak within 3 seconds.
3. **Email Deliverability Optimisation:** Outreach assets MUST be lightweight (image teasers under 200KB) to ensure high inbox deliverability rates.
4. **White-Label Customization:** The system MUST allow agency tenant overrides (custom logo, brand colors, booking link `cal.com/agency-sdr`) without code changes.

---

## 8. Business Model Architecture Decisions (ADRs)

### ADR-BM-001: Commercial Dollar Quantification First
* **Status:** Accepted
* **Context:** V1 reported qualitative statuses (`Revenue Leak — High`), which failed to provide strong commercial urgency during cold outreach.
* **Decision:** V2 elevates financial loss estimation ($/month) to a top-level system metric present in every output payload.
* **Consequences:** Scanner context must capture product price metrics and traffic estimation buckets during execution.

### ADR-BM-002: Multi-Format Asset Generation
* **Status:** Accepted
* **Context:** V1 generated a single 7MB HTML file containing 10 stores, which could not be attached to cold emails or sent to individual brand founders.
* **Decision:** V2 decouples presentation rendering to output three separate formats: Teaser PNG, Executive Audit PDF, and Benchmark HTML.
* **Consequences:** The renderer architecture must support template drivers for PDF rendering (e.g. WeasyPrint / HTML-to-PDF) and image cropping.
