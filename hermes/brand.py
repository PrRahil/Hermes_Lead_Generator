"""Intellytics positioning used in cold outreach and project framing."""

COMPANY_NAME = "Intellytics"
COMPANY_URL = "https://intellytics.ai"
CONTACT_EMAIL = "contact@intellytics.ai"
CONTACT_PHONE = "+1 (219) 214-6890"

ONE_LINER = (
    "We turn disconnected data into trusted pipelines, dashboards, "
    "predictive insights, and AI-powered workflows."
)

CAPABILITIES = [
    "Data engineering & governed pipelines (dbt, Airflow, Glue, ADF)",
    "Cloud data platforms (Snowflake, Databricks, BigQuery, AWS/Azure/GCP)",
    "Analytics & BI (Tableau, Power BI, semantic layers)",
    "AI / ML / LLM systems, RAG, agents, and evaluation harnesses",
    "Productized delivery — flexible discovery → fixed-scope pilots → production",
]

CASE_PROOF = [
    "Snowflake + AWS modernization for a top-5 U.S. home-leasing portfolio (80k+ homes)",
    "Azure Databricks consolidation across 82+ logistics terminals in 40+ countries",
    "Healthcare warehouse + Power BI + CRM/mobile with SAP integration",
]

DELIVERY_STEPS = [
    "Discover & Align",
    "Define the Roadmap",
    "Research & Architect",
    "Engineer & Build",
    "Test & Deploy",
    "Handover & Evolve",
]


def outreach_signature() -> str:
    return (
        f"{COMPANY_NAME}\n"
        f"{ONE_LINER}\n"
        f"{COMPANY_URL} · {CONTACT_EMAIL} · {CONTACT_PHONE}"
    )
