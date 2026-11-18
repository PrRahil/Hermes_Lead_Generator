from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Prefer OpenRouter (OpenAI-compatible). OPENAI_API_KEY kept as fallback alias.
    openrouter_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "https://openrouter.ai/api/v1"
    # Cheapest strong OpenAI model on OpenRouter for JSON + short outreach rewrite.
    openai_model: str = "openai/gpt-4.1-nano"
    openrouter_http_referer: str = "http://127.0.0.1:8787"
    openrouter_app_title: str = "Hermes Lead Machine"

    serper_api_key: str = ""
    hunter_api_key: str = ""

    hermes_host: str = "127.0.0.1"
    hermes_port: int = 8787
    hermes_db_path: str = str(DATA_DIR / "hermes_leads.db")

    # Continuous hunter
    scan_interval_sec: int = 180
    strong_lead_target: int = 50
    strong_lead_min_score: float = 70.0
    # Keep LLM off by default during long hunts (templates only)
    hermes_use_llm: bool = False

    icp_industries: str = (
        "technology,software,saas,data,artificial intelligence,"
        "machine learning,analytics,cloud,fintech,healthtech"
    )
    icp_min_employees: int = 20
    icp_max_employees: int = 5000
    icp_min_revenue_usd: int = 1_000_000
    icp_target_titles: str = (
        "CTO,VP Engineering,Head of Data,Head of AI,ML Engineer,"
        "Data Engineer,Founder,CEO,Product Manager,Director of Analytics,"
        "VP Data,Chief Data Officer,MLOps Lead"
    )
    icp_keywords: str = (
        "data pipeline,data engineering,LLM,RAG,machine learning,AI agent,MLOps,"
        "analytics platform,feature store,vector database,ETL,ELT,dbt,Snowflake,"
        "BigQuery,Databricks,Kafka,real-time analytics,AI consultant,"
        "generative AI,LLM evaluation,prompt engineering,embeddings,"
        "recommendation system,NLP,computer vision,data warehouse,"
        "business intelligence,Looker,Power BI,Airflow,orchestration"
    )

    @property
    def industries(self) -> List[str]:
        return [x.strip().lower() for x in self.icp_industries.split(",") if x.strip()]

    @property
    def target_titles(self) -> List[str]:
        return [x.strip() for x in self.icp_target_titles.split(",") if x.strip()]

    @property
    def keywords(self) -> List[str]:
        return [x.strip().lower() for x in self.icp_keywords.split(",") if x.strip()]

    @property
    def llm_api_key(self) -> str:
        return (self.openrouter_api_key or self.openai_api_key or "").strip()

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)

    @property
    def uses_openrouter(self) -> bool:
        return "openrouter.ai" in (self.openai_base_url or "").lower()

    @property
    def db_path(self) -> Path:
        path = Path(self.hermes_db_path)
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path


@lru_cache
def get_settings() -> Settings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "exports").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "imports").mkdir(parents=True, exist_ok=True)
    return Settings()


PLATFORMS = [
    "linkedin",
    "upwork",
    "fiverr",
    "wellfound",
    "clutch",
    "toptal",
    "indeed",
    "reddit",
    "github",
    "manual",
    "web",
]

PIPELINE_STAGES = [
    "signal",
    "lead",
    "qualified",
    "outreach",
    "replied",
    "negotiation",
    "won",
    "lost",
    "suppressed",
]