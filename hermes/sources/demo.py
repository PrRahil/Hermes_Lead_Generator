from __future__ import annotations

from typing import List

from hermes.sources.base import RawSignal, SourceConnector


DEMO_SIGNALS: List[RawSignal] = [
    RawSignal(
        platform="linkedin",
        title="Hiring: Senior Data Engineer for real-time analytics platform",
        snippet=(
            "Series B SaaS looking for help rebuilding our Kafka → Snowflake pipeline "
            "and adding an LLM-assisted anomaly layer. Budget approved for Q2."
        ),
        url="https://www.linkedin.com/jobs/view/demo-1001",
        company_name="Nimbus Analytics",
        company_domain="nimbusanalytics.example",
        industry="saas",
        employee_count=180,
        revenue_usd=12_000_000,
        location="Austin, TX",
        contact_name="Priya Shah",
        contact_title="Head of Data",
        contact_email="priya.shah@nimbusanalytics.example",
        requirement="Rebuild streaming data pipeline + LLM anomaly detection",
        tags=["data pipeline", "llm", "snowflake"],
        acquisition_source="linkedin:jobs",
    ),
    RawSignal(
        platform="upwork",
        title="Need RAG chatbot over internal docs for AI ops team",
        snippet=(
            "We need a contractor to stand up a production RAG stack (vector DB + evals) "
            "for our support knowledge base. Looking for someone with LangChain/LlamaIndex."
        ),
        url="https://www.upwork.com/jobs/demo-2002",
        company_name="ForgeOps Cloud",
        company_domain="forgeops.example",
        industry="cloud",
        employee_count=95,
        revenue_usd=6_500_000,
        location="Remote / EU",
        contact_name="Marcus Klein",
        contact_title="VP Engineering",
        contact_email="marcus@forgeops.example",
        requirement="Production RAG chatbot with evals and observability",
        tags=["rag", "llm", "ai agent"],
        acquisition_source="upwork:job",
    ),
    RawSignal(
        platform="wellfound",
        title="MLOps engineer to productionize churn models",
        snippet=(
            "Fintech startup (Series A) needs MLOps help: feature store, model registry, "
            "CI for training jobs, and monitoring drift."
        ),
        url="https://wellfound.com/jobs/demo-3003",
        company_name="Ledgerlane",
        company_domain="ledgerlane.example",
        industry="fintech / technology",
        employee_count=55,
        revenue_usd=3_200_000,
        location="New York, NY",
        contact_name="Amina Okonkwo",
        contact_title="CTO",
        contact_email="amina@ledgerlane.example",
        requirement="MLOps platform for churn models",
        tags=["mlops", "feature store", "machine learning"],
        acquisition_source="wellfound:jobs",
    ),
    RawSignal(
        platform="reddit",
        title="[Hiring] Looking for freelance AI consultant to audit our agent stack",
        snippet=(
            "We built a few AI agents with open-source tools and they hallucinate in prod. "
            "Need an audit + hardening plan. Paid engagement."
        ),
        url="https://www.reddit.com/r/MachineLearning/comments/demo4",
        company_name="Brightpath Health",
        company_domain="brightpath.example",
        industry="healthtech",
        employee_count=220,
        revenue_usd=28_000_000,
        location="Chicago, IL",
        contact_name="u/brightpath_pm",
        contact_title="Product Manager",
        contact_email="ops@brightpath.example",
        requirement="AI agent audit and production hardening",
        tags=["ai agent", "llm", "audit"],
        acquisition_source="reddit:MachineLearning",
    ),
    RawSignal(
        platform="clutch",
        title="Agency RFP: Analytics dashboard + data warehouse cleanup",
        snippet=(
            "B2B manufacturing software company seeking partner for dbt/BigQuery cleanup "
            "and executive KPI dashboard. Prefer US or nearshore."
        ),
        url="https://clutch.co/rfp/demo-5005",
        company_name="Steelthread Systems",
        company_domain="steelthread.example",
        industry="software",
        employee_count=410,
        revenue_usd=55_000_000,
        location="Denver, CO",
        contact_name="Helen Cho",
        contact_title="Director of Analytics",
        contact_email="helen.cho@steelthread.example",
        requirement="BigQuery/dbt cleanup + executive analytics dashboards",
        tags=["analytics platform", "data pipeline"],
        acquisition_source="clutch:rfp",
    ),
    RawSignal(
        platform="indeed",
        title="Contract Data Scientist — NLP for support tickets",
        snippet=(
            "6-month contract to classify support tickets and route to specialists. "
            "Must know transformers and evaluation methodology."
        ),
        url="https://www.indeed.com/viewjob?jk=demo6006",
        company_name="Parcelly Logistics",
        company_domain="parcelly.example",
        industry="logistics technology",
        employee_count=1200,
        revenue_usd=140_000_000,
        location="Seattle, WA",
        contact_name="Tom Reyes",
        contact_title="Head of AI",
        contact_email="tom.reyes@parcelly.example",
        requirement="NLP ticket classification with transformers",
        tags=["machine learning", "nlp"],
        acquisition_source="indeed:contract",
    ),
    RawSignal(
        platform="fiverr",
        title="Buyer request: Build vector search over product catalog",
        snippet=(
            "E-commerce brand wants semantic search across 80k SKUs. "
            "Need embeddings pipeline + simple React search UI."
        ),
        url="https://www.fiverr.com/requests/demo-7007",
        company_name="Oak & Loom",
        company_domain="oakandloom.example",
        industry="ecommerce / retail tech",
        employee_count=40,
        revenue_usd=4_800_000,
        location="Remote",
        contact_name="Sofia Marin",
        contact_title="Founder",
        contact_email="sofia@oakandloom.example",
        requirement="Vector search over product catalog",
        tags=["vector database", "embeddings"],
        acquisition_source="fiverr:buyer_request",
    ),
    RawSignal(
        platform="toptal",
        title="Shortlist request: Staff AI engineer for multi-agent orchestration",
        snippet=(
            "Enterprise SaaS needs a staff-level AI engineer for multi-agent workflows "
            "tied into Salesforce and internal APIs. 3-month engagement."
        ),
        url="https://www.toptal.com/developers/demo-8008",
        company_name="Northwind CRM Labs",
        company_domain="northwindcrm.example",
        industry="saas",
        employee_count=650,
        revenue_usd=90_000_000,
        location="Boston, MA",
        contact_name="Derek Lang",
        contact_title="VP Engineering",
        contact_email="derek.lang@northwindcrm.example",
        requirement="Multi-agent orchestration integrated with Salesforce",
        tags=["ai agent", "llm", "integrations"],
        acquisition_source="toptal:shortlist",
    ),
    RawSignal(
        platform="linkedin",
        title="Weekend side project seeking unpaid help with ChatGPT prompts",
        snippet="Student club needs free help writing prompts for a school hackathon.",
        url="https://www.linkedin.com/posts/demo-lowfit",
        company_name="Campus Hack Club",
        company_domain="",
        industry="education",
        employee_count=5,
        revenue_usd=0,
        location="Remote",
        contact_name="Alex Student",
        contact_title="Club Member",
        contact_email="alex@mailinator.com",
        requirement="Free prompt writing",
        tags=["chatgpt"],
        acquisition_source="linkedin:post",
    ),
    RawSignal(
        platform="github",
        title="Discussions: Looking for contractor to add eval harness to open LLM app",
        snippet=(
            "OSS maintainer of a popular RAG demo wants paid help adding offline + online "
            "evaluation, hallucination checks, and CI gates before 1.0."
        ),
        url="https://github.com/example/rag-demo/discussions/42",
        company_name="OpenRAG Labs",
        company_domain="openrag.example",
        industry="open source / technology",
        employee_count=12,
        revenue_usd=1_100_000,
        location="Remote",
        contact_name="Jin Park",
        contact_title="Maintainer / Founder",
        contact_email="jin@openrag.example",
        requirement="LLM evaluation harness and CI quality gates",
        tags=["rag", "llm", "evals"],
        acquisition_source="github:discussions",
    ),
]


class DemoSource(SourceConnector):
    name = "demo"

    def fetch(self, query: str = "", limit: int = 25) -> List[RawSignal]:
        from hermes.sources.match import filter_by_query

        items = filter_by_query(DEMO_SIGNALS, query)
        return items[:limit]