import logging
import json
from src.ingestion.store_loader import StoreRecord
from src.orchestration.worker import execute_single_store_worker

logging.basicConfig(level=logging.INFO)

TARGET_STORES = [
    {"domain": "allbirds.com", "base_url": "https://www.allbirds.com"},
    {"domain": "gymshark.com", "base_url": "https://www.gymshark.com"},
    {"domain": "chubbies shorts.com", "base_url": "https://www.chubbiesshorts.com"},
    {"domain": "morphe.com", "base_url": "https://www.morphe.com"},
    {"domain": "kith.com", "base_url": "https://kith.com"},
    {"domain": "brooklinen.com", "base_url": "https://www.brooklinen.com"},
    {"domain": "alohas.io", "base_url": "https://alohas.io"},
    {"domain": "triangl.com", "base_url": "https://triangl.com"},
    {"domain": "fleshlight.com", "base_url": "https://www.fleshlight.com"},
    {"domain": "huel.com", "base_url": "https://huel.com"},
]

def run_field_validation():
    results = []
    print("=== STARTING REAL-WORLD FIELD VALIDATION (10 REAL SHOPIFY STORES) ===")
    for idx, store_data in enumerate(TARGET_STORES, start=1):
        domain = store_data["domain"]
        print(f"\n[{idx}/10] Executing scan for real Shopify store: {domain}")
        store_record = StoreRecord(domain=domain, base_url=store_data["base_url"])
        res_dict = execute_single_store_worker(store_record.model_dump(mode="json"))
        results.append(res_dict)
        print(f"Result for {domain}: Status={res_dict.get('status')}, Loss=${res_dict.get('est_monthly_loss_usd', 0):,.2f}, Priority={res_dict.get('lead_priority')}")

    with open("field_validation_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\n=== FIELD VALIDATION SCAN RUN COMPLETE ===")

if __name__ == "__main__":
    run_field_validation()
