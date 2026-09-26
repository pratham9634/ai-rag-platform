"""
10-Page Enterprise Handbook PDF Generator.

Natively creates a realistic, structured 10-page corporate employee policy
document using PyMuPDF (fitz) for testing and benchmarking RAG systems.
Every page contains distinct operational policies, figures, and conditional clauses.
"""

from pathlib import Path

import fitz  # PyMuPDF

OUTPUT_DIR = Path(__file__).parent / "datasets"
OUTPUT_FILE = OUTPUT_DIR / "acme_employee_handbook.pdf"

HANDBOOK_PAGES = [
    {
        "page_number": 1,
        "title": "Page 1: Corporate Governance, Employment Classification & Probation",
        "content": """ACME ENTERPRISE CLOUD — GLOBAL EMPLOYEE HANDBOOK (2026 EDITION)

SECTION 1: CORPORATE MISSION & EMPLOYMENT CLASSIFICATION
Acme Enterprise Cloud provides mission-critical cloud infrastructure and generative AI orchestration for Fortune 500 enterprises. All personnel are classified as either:
1. Regular Full-Time: Employees scheduled to work 40 hours per week, eligible for all company-sponsored benefit plans, equity grants, and paid leave.
2. Regular Part-Time: Employees working fewer than 30 hours per week, eligible for prorated benefits.
3. Temporary / Contractors: Workers engaged for a specific project duration, ineligible for company benefit packages or equity vesting.

SECTION 1.2: PROBATIONARY INTRODUCTORY PERIOD
All new full-time hires are subject to an initial 90-day probationary introductory period commencing on their formal start date.
During this 90-day window:
- Employee performance and culture alignment are formally reviewed at 30, 60, and 90 days by the direct manager.
- Employees are not permitted to book discretionary international business travel or request non-emergency paid time off exceeding 2 consecutive days.
- Completion of the 90-day period requires formal written sign-off from both the Department Vice President and People Operations.""",
    },
    {
        "page_number": 2,
        "title": "Page 2: Working Hours, Remote Work Stipends & Hardware Procurement",
        "content": """SECTION 2: WORKING HOURS & FLEXIBLE SCHEDULES
Core collaboration hours across all regional offices are 10:00 AM to 4:00 PM local time. While engineers and knowledge workers may adjust start and end times with team agreement, attendance at daily standups and sprint planning sessions during core hours is mandatory.

SECTION 2.1: REMOTE WORK STIPENDS & HOME OFFICE ALLOWANCE
Acme operates on a remote-first hybrid philosophy. Full-time remote employees are entitled to:
- Home Office Setup Stipend: A one-time, non-taxable reimbursement of up to $750 for ergonomic chairs, standing desks, monitors, or noise-canceling headsets. Claims must be submitted within 60 days of hire via Concur.
- Monthly Connectivity Subsidy: An ongoing monthly stipend of $100 paid directly through payroll to offset high-speed fiber internet and mobile phone data usage.

SECTION 2.2: HARDWARE PROCUREMENT & REFRESH CYCLES
Standard issue engineering hardware consists of an Apple MacBook Pro 16-inch (M3 Max, 64GB RAM) or Dell Precision 5680 workstation.
- Standard hardware refresh cycles occur every 36 months from initial receipt.
- Lost or stolen devices must be reported immediately (within 2 hours) to the Information Security Operations Center (ISOC) for remote cryptographic wipe.""",
    },
    {
        "page_number": 3,
        "title": "Page 3: Paid Time Off (PTO), Sick Leave & Family Leave Policies",
        "content": """SECTION 3: PAID TIME OFF (PTO) ACCRUAL
Acme believes in work-life sustainability and provides a generous leave program:
- Annual PTO Allowance: Regular full-time employees receive 25 days of accrued paid time off per calendar year, accruing at a rate of 2.08 days per full month worked.
- Rollover Caps: Employees may roll over a maximum of 5 unused PTO days into the following calendar year. Any unused PTO exceeding 5 days on December 31 is forfeited.
- Advance Notice: Planned PTO of 3 or more consecutive business days requires at least 2 weeks prior written notice and manager approval in Workday.

SECTION 3.1: SICK LEAVE & MENTAL HEALTH DAYS
Employees receive 10 days of paid sick and mental health leave per year, available immediately upon hire without accrual waiting periods. Doctor certification is only required for sick leaves extending beyond 3 consecutive working days.

SECTION 3.2: PARENTAL & BEREAVEMENT LEAVE
- Primary Caregiver Parental Leave: 16 weeks of 100% paid leave for the birth, adoption, or foster placement of a child, available after 6 months of continuous employment.
- Secondary Caregiver Parental Leave: 8 weeks of 100% paid leave.
- Bereavement Leave: Up to 5 consecutive paid days for immediate family members (spouse, child, parent, sibling).""",
    },
    {
        "page_number": 4,
        "title": "Page 4: Healthcare Benefits, 401(k) Retirement & Equity Vesting",
        "content": """SECTION 4: HEALTH, DENTAL & VISION INSURANCE
Acme covers 90% of the monthly health insurance premium for employees and 75% for eligible dependents under our Blue Cross Blue Shield PPO or Kaiser Permanente HMO plans. Coverage takes effect on the first calendar day of the month following the hire date.

SECTION 4.1: 401(K) RETIREMENT PLAN & EMPLOYER MATCHING
Retirement savings are managed through Fidelity Investments:
- Company Match Formula: Acme provides a dollar-for-dollar 100% match on employee 401(k) contributions up to 6% of the employee's gross annual base salary.
- Immediate Vesting: All employer matching contributions are 100% immediately vested from day one with zero vesting cliff.
- Traditional and Roth 401(k) options are both supported up to federal IRS annual statutory contribution limits.

SECTION 4.2: EQUITY INCENTIVE PLANS (RSUS & STOCK OPTIONS)
Corporate equity grants are governed by the 2024 Global Equity Incentive Plan:
- Standard Vesting Schedule: Equity grants follow a standard 4-year vesting schedule with a 1-year cliff (25% vests on the first anniversary of the vesting commencement date, and 6.25% vests quarterly thereafter for the remaining 36 months).""",
    },
    {
        "page_number": 5,
        "title": "Page 5: Information Security, Password Complexity & MFA Standards",
        "content": """SECTION 5: CYBERSECURITY & ACCESS CONTROL POLICIES
All employees handling corporate or customer data must adhere to strict ISO-27001 and SOC-2 Type II information security baselines.

SECTION 5.1: PASSWORD COMPLEXITY & ROTATION RULES
All corporate accounts and Active Directory credentials must enforce the following criteria:
- Minimum Length: At least 16 characters in length.
- Character Classes: Must include at least 1 uppercase letter, 1 lowercase letter, 1 number, and 1 non-alphanumeric symbol (!@#$%^&*).
- Dictionary Checks: Passwords matching common dictionary words or predictable sequences are rejected automatically by Okta.
- Rotation Interval: Passwords must be rotated every 90 days. Reusing any of the previous 8 passwords is prohibited.

SECTION 5.2: MULTI-FACTOR AUTHENTICATION (MFA)
- Hardware Token Requirement: Universal Two-Factor (FIDO2 / WebAuthn hardware security keys like YubiKey) is mandatory for accessing production AWS, Supabase, and GitHub environments.
- SMS and voice-call verification are strictly forbidden due to SIM-swapping vulnerabilities.
- Workstation Screen Lockout: Workstations must be configured to lock automatically after 15 minutes of inactivity.""",
    },
    {
        "page_number": 6,
        "title": "Page 6: BYOD Protocols & Data Classification Framework",
        "content": """SECTION 6: BRING YOUR OWN DEVICE (BYOD) POLICY
Personal smartphones and tablets may access corporate email, Slack, and calendars only under strict compliance guidelines:
- Mobile Device Management (MDM): Personal devices must enroll in Microsoft Intune MDM, requiring biometric unlock (FaceID or fingerprint) and full-device AES-256 storage encryption.
- Jailbroken / Rooted Devices: Connecting modified, jailbroken, or rooted hardware to any Acme network or cloud resource results in immediate account suspension.

SECTION 6.1: FOUR-TIER DATA CLASSIFICATION FRAMEWORK
All digital assets and document files are classified into four strict categories:
1. Public (Tier 1): Marketing collateral, public press releases, approved open-source code.
2. Internal (Tier 2): General internal wikis, organizational charts, non-confidential department announcements.
3. Confidential (Tier 3): Customer contracts, financial spreadsheets, product roadmaps, source code repositories. Requires role-based access control and tenant isolation.
4. Restricted (Tier 4): Customer Personally Identifiable Information (PII), cryptographic private keys, payroll compensation databases, and health records. Requires hardware MFA and VP-level access approval.""",
    },
    {
        "page_number": 7,
        "title": "Page 7: Incident Response Protocol & Severity SLA Matrix",
        "content": """SECTION 7: INCIDENT MANAGEMENT & ESCALATION PROCEDURES
The Acme Security Operations Center (SOC) operates 24/7/365 to triage, contain, and remediate cybersecurity and infrastructure disruptions.

SECTION 7.1: SEVERITY LEVEL DEFINITIONS & SLA RESPONSE TIMES
- Severity 1 (Sev-1) — Critical Outage / Data Breach:
  Definition: Complete customer platform outage, confirmed compromise of production database, or active exfiltration of Restricted Tier 4 customer data.
  Initial Response SLA: Within 15 minutes.
  Executive Escalation: Immediate notification to the CTO, CISO, and General Counsel within 30 minutes. Status updates provided every 60 minutes.
- Severity 2 (Sev-2) — Major Degradation:
  Definition: Impaired core system functionality impacting more than 20% of users without customer data breach.
  Initial Response SLA: Within 1 hour.
- Severity 3 (Sev-3) — Moderate Issue:
  Definition: Non-critical feature bug, minor latency degradation, or isolated tenant issue.
  Initial Response SLA: Within 4 business hours.
- Severity 4 (Sev-4) — Low / Cosmetic:
  Definition: Minor UI defect or documentation typo.
  Initial Response SLA: Within 24 business hours.""",
    },
    {
        "page_number": 8,
        "title": "Page 8: Travel & Expense Limits, Meal Per Diems & Approvals",
        "content": """SECTION 8: CORPORATE TRAVEL & EXPENSE POLICY
Business travel must be pre-approved in writing by the department manager before flight booking.

SECTION 8.1: AIRFARE & LODGING GUIDELINES
- Economy Class Standard: Flights under 6 hours must be booked in Standard Economy class. Business class is permitted only for international flights with flight times exceeding 8 continuous hours.
- Hotel Nightly Room Cap: Up to $250/night for standard tier cities, and up to $350/night for designated high-cost metropolitan areas (New York, San Francisco, London, Tokyo, Zurich).

SECTION 8.2: MEAL PER DIEM ALLOWANCES
- Domestic Daily Meal Per Diem: Maximum $75 per day ($15 breakfast, $25 lunch, $35 dinner).
- International Daily Meal Per Diem: Maximum $120 per day.
- Itemized Receipts: Itemized receipts are mandatory for all expenses exceeding $25. Credit card summary slips are not accepted. Alcohol is non-reimbursable unless part of an authorized client entertainment dinner.

SECTION 8.3: EXPENSE APPROVAL TIERS
- Up to $1,000: Direct Team Manager approval.
- $1,001 to $5,000: Department Director approval.
- Exceeding $5,000: Vice President (VP) and Finance Operations sign-off required.""",
    },
    {
        "page_number": 9,
        "title": "Page 9: Code of Conduct, Anti-Harassment & Whistleblower Protections",
        "content": """SECTION 9: WORKPLACE ETHICS & PROFESSIONAL CONDUCT
Acme is committed to providing a professional, inclusive, and harassment-free work environment regardless of race, gender, sexual orientation, disability, religion, or age.

SECTION 9.1: ZERO-TOLERANCE ANTI-HARASSMENT POLICY
Harassment, discrimination, bullying, or unwelcome verbal/physical conduct of any kind is strictly prohibited. Violations will result in immediate disciplinary action up to and including termination of employment.

SECTION 9.2: CONFLICT OF INTEREST & OUTSIDE EMPLOYMENT
Employees must not engage in outside consulting, secondary employment, or board memberships with direct Acme competitors. Any outside commercial engagement requires prior written authorization from the Chief Legal Officer (CLO).

SECTION 9.3: WHISTLEBLOWER HOTLINE & RETALIATION IMMUNITY
Employees who observe unlawful conduct, accounting irregularities, or safety violations may report anonymously via the Acme Ethics Helpline (ethics.acme-cloud.internal or 1-800-555-ACME).
- Retaliation against any employee who reports suspected wrongdoing in good faith is illegal and results in immediate dismissal of the retaliating party.
- All investigations are conducted independently by the Legal and Internal Audit teams within 14 business days.""",
    },
    {
        "page_number": 10,
        "title": "Page 10: Termination Protocols, Severance Packages & IP Assignment",
        "content": """SECTION 10: OFFBOARDING & TERMINATION OF EMPLOYMENT
Employment at Acme is at-will, meaning either the company or the employee may terminate the employment relationship at any time, with or without cause, subject to applicable local laws.

SECTION 10.1: RESIGNATION NOTICE & SEVERANCE SCHEDULES
- Voluntary Resignation: Exempt professional employees are expected to provide a minimum of 2 weeks written notice to their manager and People Operations.
- Involuntary Separation (Reductions in Force / Restructuring):
  Eligible employees receive standard severance packages calculated as:
  - Base Severance: 4 weeks of salary continuation.
  - Tenure Increment: Additional 2 weeks of base salary for each full completed year of continuous service, capped at a maximum of 26 total weeks.
  - COBRA Healthcare Continuation: 3 months of employer-subsidized health benefits.

SECTION 10.2: INTELLECTUAL PROPERTY ASSIGNMENT & NON-DISCLOSURE
All inventions, source code, patents, algorithms, and documentation developed during employment using company equipment or related to Acme business belong exclusively to Acme Enterprise Cloud.
- Employees remain bound by permanent Non-Disclosure Agreements (NDAs) regarding proprietary customer algorithms and trade secrets following separation.
- All company laptops, badge credentials, and cryptographic tokens must be surrendered on the final day of employment.""",
    },
]


def generate_handbook_pdf(output_path: Path | None = None) -> Path:
    """Generate the 10-page PDF document using PyMuPDF."""
    dest = output_path or OUTPUT_FILE
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()

    for item in HANDBOOK_PAGES:
        # Standard Letter page size: 612 x 792 points
        page = doc.new_page(width=612, height=792)

        # Header banner
        page.draw_rect(fitz.Rect(36, 36, 576, 70), color=(0.1, 0.2, 0.4), fill=(0.95, 0.96, 0.98))
        page.insert_text(
            fitz.Point(46, 58),
            item["title"],
            fontsize=12,
            fontname="helv",
            color=(0.1, 0.2, 0.4),
        )

        # Body text
        rect = fitz.Rect(46, 85, 566, 730)
        page.insert_textbox(
            rect,
            item["content"],
            fontsize=10.5,
            fontname="helv",
            color=(0.15, 0.15, 0.15),
            align=fitz.TEXT_ALIGN_LEFT,
        )

        # Footer with page number
        page.insert_text(
            fitz.Point(270, 765),
            f"— Page {item['page_number']} of 10 —",
            fontsize=9,
            fontname="helv",
            color=(0.5, 0.5, 0.5),
        )

    doc.save(str(dest))
    doc.close()
    return dest


if __name__ == "__main__":
    path = generate_handbook_pdf()
    print(f"Generated 10-page handbook at: {path}")
