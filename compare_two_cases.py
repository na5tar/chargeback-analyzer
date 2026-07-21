#!/usr/bin/env python3
"""
Focused comparison: CB-2025-0001 and CB-2025-0006
No truncation, full rationale, side-by-side output.
Usage: python compare_two_cases.py
"""
import json
import time
from analyzer import analyze_case
from page_selector import prepare_document_images_tiered


def load_cases(path="cases.json"):
    with open(path, 'r') as f:
        return json.load(f)


def compare_case(case, providers=["openai", "kimi"]):
    """
    Run a single case through multiple providers and return full comparison.
    """
    case_id = case['case_id']
    print(f"\n{'='*70}")
    print(f"CASE: {case_id}")
    print(f"SCHEME: {case['scheme'].upper()} | REASON: {case['reason_code']} — {case['reason_code_label']}")
    print(f"MERCHANT: {case['transaction']['merchant_name']}")
    print(f"AVS: {case['transaction']['avs_result']} | CVV: {case['transaction']['cvv_result']} | 3DS: {case['transaction']['three_ds_status']}")
    print(f"BILLING: {case['transaction']['billing_address_postcode']} | SHIPPING: {case['transaction']['shipping_address_postcode']}")
    print(f"{'='*70}")

    images = prepare_document_images_tiered(case)
    print(f"Documents: {len(case['merchant_evidence_documents'])} | Images prepared: {len(images)}")

    results = {}
    for provider in providers:
        print(f"\n--- {provider.upper()} ---")
        start = time.time()
        try:
            analysis, meta = analyze_case(case, images, provider=provider)
            elapsed = time.time() - start

            result = {
                "recommendation": analysis.get("recommendation", "unknown"),
                "confidence": analysis.get("confidence_score", 0),
                "tokens": analysis.get("llm_tokens_used", 0),
                "mode": analysis.get("analysis_mode", "unknown"),
                "rationale": analysis.get("representment_rationale", "N/A"),
                "justification": analysis.get("justification", "N/A"),
                "evidence_assessment": analysis.get("evidence_assessment", []),
                "systematic_flags": analysis.get("systematic_flags", []),
                "elapsed_sec": round(elapsed, 2),
                "error": None
            }

            print(f"  Recommendation: {result['recommendation'].upper()}")
            print(f"  Confidence: {result['confidence']}/100")
            print(f"  Tokens: {result['tokens']}")
            print(f"  Mode: {result['mode']}")
            print(f"  Time: {result['elapsed_sec']}s")
            print(f"  Rationale: {result['rationale']}")
            print(f"  Justification: {result['justification']}")

            if result['systematic_flags']:
                print(f"  Flags:")
                for flag in result['systematic_flags']:
                    print(f"    - {flag['flag_type']}: {flag['description']}")

            if result['evidence_assessment']:
                print(f"  Evidence Assessment:")
                for item in result['evidence_assessment']:
                    status = item.get('status', 'unknown')
                    emoji = {'satisfied': '✅', 'partial': '⚠️', 'missing': '❌', 'not_applicable': '➖'}.get(status, '❓')
                    print(f"    {emoji} Req {item['requirement_number']}: {status.upper()}")
                    print(f"       Doc: {item.get('document_reference', 'N/A')}")
                    print(f"       Explanation: {item.get('explanation', 'N/A')[:200]}")

        except Exception as e:
            result = {
                "recommendation": "error",
                "confidence": 0,
                "tokens": 0,
                "mode": "error",
                "rationale": str(e),
                "justification": str(e),
                "evidence_assessment": [],
                "systematic_flags": [],
                "elapsed_sec": round(time.time() - start, 2),
                "error": str(e)
            }
            print(f"  ERROR: {e}")

        results[provider] = result

        # Rate limit for Kimi
        if provider == "kimi":
            time.sleep(2)

    # Disagreement check
    recs = [r["recommendation"] for r in results.values() if r["error"] is None]
    if len(set(recs)) > 1:
        print(f"\n{'⚠️'*10}")
        print(f"DISAGREEMENT DETECTED: {', '.join(set(recs))}")
        print(f"{'⚠️'*10}")
    else:
        print(f"\n{'✅'*10}")
        print(f"AGREEMENT: {recs[0] if recs else 'N/A'}")
        print(f"{'✅'*10}")

    return {"case_id": case_id, "results": results}


def main():
    cases = load_cases()

    # Filter to the two cases we want
    target_cases = ["CB-2025-0001", "CB-2025-0006"]

    all_results = []
    for case in cases:
        if case['case_id'] in target_cases:
            result = compare_case(case, providers=["openai", "kimi"])
            all_results.append(result)

    # Save full results (no truncation)
    output_file = "comparison_two_cases.json"
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2)

    print(f"\n{'='*70}")
    print(f"Full results saved to: {output_file}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()