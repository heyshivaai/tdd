# PE Technology Due Diligence Platform

## What This Is
An agentic system that performs end-to-end technology due diligence for private equity firms.
Covers the full deal lifecycle: Pre-LOI rapid scans -> Full Diligence (LOI to Close) -> Post-Acquisition Value Creation.

## Project Location
C:\users\itssh\tdd

## Build Order (one agent at a time, fully working before moving on)
1. Pre-LOI Agent - rapid scan, deal-breaker flags, risk score
2. Full Diligence Agent - deep review across 8 domains
3. Report Generator - scorecards, exec summaries, red/yellow/green flags
4. Document Ingestion Tool - read PDFs and Word docs from data room
5. Value Creation Agent - 100-day plans, modernization roadmaps

## Tech Stack
- Language: Python 3.11+
- AI: Anthropic Claude API (model: claude-sonnet-4-20250514)
- Document reading: PyPDF2, python-docx
- CLI: Typer (simple command-line interface)
- Config/secrets: python-dotenv
- Output format: JSON first, then formatted Markdown reports

## Folder Structure
/agents       - one file per agent (pre_loi.py, full_diligence.py, value_creation.py)
/tools        - shared utilities (document_reader.py, scorer.py, report_writer.py)
/prompts      - prompt templates as .txt or .py files, one per diligence domain
/outputs      - all generated reports land here (gitignored)
/data         - sample company inputs and test data room documents
/tests        - test files mirroring the agents/ and tools/ structure
/docs         - architecture notes, domain definitions, scoring rubrics

## Output Contract (every agent must return this JSON shape)
{
  "company_name": string,
  "assessment_type": string,
  "timestamp": ISO string,
  "overall_risk_score": number,
  "flags": {
    "red": [],
    "yellow": [],
    "green": []
  },
  "domain_scores": {},
  "executive_summary": string,
  "detailed_findings": {},
  "recommendations": []
}

## Diligence Domains (Full Diligence covers all 8)
1. Architecture - scalability, resilience, modularity, cloud posture
2. Codebase - quality, technical debt, language/framework choices
3. Security - vulnerabilities, compliance (SOC2, ISO27001, GDPR), data governance
4. Product - roadmap realism, feature velocity, PMF signals
5. DevOps - CI/CD maturity, observability, incident response, SLAs
6. Team - structure, seniority mix, key-person risk, hiring velocity
7. Data - data models, quality, pipelines, AI/ML readiness
8. Commercial Tech - licensing, vendor lock-in, IP ownership

## Scoring Rubric
1-2: Critical failure / deal-breaker territory
3-4: Significant concerns, major remediation needed
5-6: Average, typical for companies at this stage
7-8: Strong, minor improvements only
9-10: Best-in-class

## Key Rules for Claude Code to Follow
- Always write Python with type hints
- Every function needs a docstring explaining what it does and why
- Secrets come from .env only - never hardcoded
- Test each agent with a fake Acme Corp example before moving on
- Commit working code with a clear message after each milestone
- If something can be a shared tool, put it in /tools not in the agent
