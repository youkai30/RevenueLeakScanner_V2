"""
src/ingestion/store_loader.py — StoreRecord Domain Model Definition

Layer 1: Ingestion & Domain Contracts
"""
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.exceptions import DomainValidationError


class StoreRecord(BaseModel):
    """
    Immutable DTO representing an ingested target store.
    Owner: src/ingestion/store_loader.py
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    domain: str = Field(description="Normalized hostname of target store")
    base_url: str = Field(description="Full HTTP/HTTPS root URL of target store")
    industry: str = Field(default="E-Commerce", description="Industry vertical category")
    country: str = Field(default="US", description="Target store country code")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Ingestion timestamp in UTC",
    )

    @field_validator("domain", mode="before")
    @classmethod
    def validate_and_normalize_domain(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise DomainValidationError("Domain string cannot be empty")
        
        domain_clean = v.strip().lower()
        # Remove protocol prefix if accidentally passed to domain
        domain_clean = re.sub(r"^https?://", "", domain_clean)
        # Remove path suffix if present
        domain_clean = domain_clean.split("/")[0]

        # Standard RFC domain regex check
        domain_regex = r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
        if not re.match(domain_regex, domain_clean):
            raise DomainValidationError(f"Invalid RFC domain hostname: '{v}'")

        return domain_clean

    @field_validator("base_url", mode="before")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise DomainValidationError("Base URL string cannot be empty")

        url_clean = v.strip()
        parsed = urlparse(url_clean)

        if parsed.scheme not in ("http", "https"):
            raise DomainValidationError(f"Base URL must use http:// or https:// scheme, got: '{v}'")
        if not parsed.netloc:
            raise DomainValidationError(f"Malformed Base URL hostname: '{v}'")

        return url_clean


class StoreLoader:
    """
    Ingests and parses target store records from CSV or JSON files into validated StoreRecord DTOs.
    """

    def load_stores_from_file(self, file_path: str | Path) -> list[StoreRecord]:
        """Loads and validates StoreRecord items from a CSV or JSON file path."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Target store file not found: {path}")

        records: list[StoreRecord] = []

        if path.suffix.lower() == ".csv":
            import csv
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    domain_val = row.get("domain") or row.get("url") or row.get("Domain")
                    if domain_val:
                        domain_clean = domain_val.strip().lower()
                        domain_clean = re.sub(r"^https?://", "", domain_clean).split("/")[0]
                        base_url = f"https://{domain_clean}"
                        try:
                            records.append(StoreRecord(domain=domain_clean, base_url=base_url))
                        except Exception:
                            pass
        elif path.suffix.lower() == ".json":
            import json
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item, str):
                        domain_clean = item.strip().lower()
                        domain_clean = re.sub(r"^https?://", "", domain_clean).split("/")[0]
                        base_url = f"https://{domain_clean}"
                        try:
                            records.append(StoreRecord(domain=domain_clean, base_url=base_url))
                        except Exception:
                            pass
                    elif isinstance(item, dict):
                        domain_val = item.get("domain") or item.get("url")
                        if domain_val:
                            domain_clean = domain_val.strip().lower()
                            domain_clean = re.sub(r"^https?://", "", domain_clean).split("/")[0]
                            base_url = f"https://{domain_clean}"
                            try:
                                records.append(StoreRecord(domain=domain_clean, base_url=base_url))
                            except Exception:
                                pass

        return records

