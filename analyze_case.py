# analyze_case.py
"""
Main entry point for chargeback case analysis.
Usage: python analyze_case.py --case CB-2025-0007 --provider kimi
"""
import json
import argparse
import os
from dotenv import load_dotenv
from analyzer import analyze_case
from page_selector import prepare_document_images_tiered

load_dotenv()


def load_cases(path="cases.json"):
    """Load all cases from JSON."""
    with open(path, 'r') as f:
        return json.load(f)


def get_case_by_id(cases, case_id):
    """Find a case by ID."""
    for case in cases:
        if case['case_id'] == case_id:
            return case
    return None


def run_analysis(case_id, provider=None, benchmark=False, output_path=None):
    """
    Run full analysis pipeline for a single case.

    Args:
        case_id: e.g. "CB-2025-0007"
        provider: "kimi", "openai", "claude", or None for auto-select
        benchmark: If True, force OpenAI for consistent benchmarking
        output_path: Optional path to save JSON output

    Returns:
        analysis dict
    """
    cases = load_cases()
    case = get_case_by_id(cases, case_id)

    if not case:
        raise ValueError(f"Case {case_id} not found in cases.json")

    print(f"\n{'='*70}")
    print(f"CASE: {case['case_id']}")
    print(f"SCHEME: {case['scheme'].upper()}")
    print(f"REASON: {case['reason_code']} - {case['reason_code_label']}")
    print(f"MERCHANT: {case['transaction']['merchant_name']}")
    print(f"AMOUNT: {case['chargeback_amount']['value']} {case['chargeback_amount']['currency']}")
    print(f"{'='*70}")

    # Step 1: Prepare document images with tiered selection
    print("\n[1/3] Preparing document images...")
    images = prepare_document_images_tiered(case)
    print(f"  → {len(images)} images prepared")
    for img in images:
        print(f"     {img['filename']} p{img['page']} (tier: {img['tier']}, score: {img['score']})")

    # Step 2: Run LLM analysis
    print("\n[2/3] Running LLM analysis...")
    analysis, _ = analyze_case(
        case=case,
        images=images,
        provider=provider,
        benchmark=benchmark
    )

    # Step 3: Output results
    print("\n[3/3] Analysis complete!")
    print(f"\n{'='*70}")
    print(f"RESULTS")
    print(f"{'='*70}")
    print(f"Provider:      {analysis.get('provider_used', 'N/A')}")
    print(f"Mode:          {analysis.get('analysis_mode', 'N/A')}")
    print(f"Recommendation:  {analysis.get('recommendation', 'N/A').upper()}")
    print(f"Confidence:    {analysis.get('confidence_score', 'N/A')}/100")
    print(f"Tokens used:   ~{analysis.get('llm_tokens_used', 'N/A')}")
    print(f"\nJustification:")
    print(f"  {analysis.get('justification', 'N/A')}")

    if 'error' in analysis:
        print(f"\n⚠️  ERROR: {analysis['error']}")

    # Evidence assessment summary
    if 'evidence_assessment' in analysis:
        print(f"\nEvidence Assessment:")
        for item in analysis['evidence_assessment']:
            status_emoji = {"satisfied": "✅", "partial": "⚠️", "missing": "❌"}.get(item['status'], "❓")
            print(f"  {status_emoji} Req {item['requirement_number']}: {item['status'].upper()}")
            print(f"     Doc: {item.get('document_reference', 'N/A')}")
            print(f"     {item.get('explanation', 'N/A')[:120]}...")

    # Systematic flags
    if analysis.get('systematic_flags'):
        print(f"\n🚩 Systematic Flags:")
        for flag in analysis['systematic_flags']:
            print(f"  [{flag['flag_type']}] {flag['description']}")

    # Save output
    if output_path:
        with open(output_path, 'w') as f:
            json.dump(analysis, f, indent=2)
        print(f"\n💾 Saved to: {output_path}")

    return analysis


def main():
    parser = argparse.ArgumentParser(description="Chargeback Representment Analyzer")
    parser.add_argument("--case", required=True, help="Case ID (e.g. CB-2025-0007)")
    parser.add_argument("--provider", choices=["kimi", "openai", "claude"], 
                       help="LLM provider (default: auto-select)")
    parser.add_argument("--benchmark", action="store_true", 
                       help="Force OpenAI for benchmarking")
    parser.add_argument("--output", help="Path to save JSON output")

    args = parser.parse_args()

    run_analysis(
        case_id=args.case,
        provider=args.provider,
        benchmark=args.benchmark,
        output_path=args.output
    )


if __name__ == "__main__":
    main()