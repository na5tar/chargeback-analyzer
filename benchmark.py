"""
Cross-provider benchmarking for chargeback analyzer.
Usage: python benchmark.py --providers kimi openai --output benchmark_results.json
"""
import json
import time
import argparse
import os
from datetime import datetime
from dotenv import load_dotenv
from analyzer import analyze_case
from page_selector import prepare_document_images_tiered

load_dotenv()


def load_cases(path="cases.json"):
    with open(path, 'r') as f:
        return json.load(f)


def benchmark_provider(provider, cases, max_cases=None):
    """
    Run all cases through a single provider and collect metrics.

    Returns list of result dicts with timing, tokens, recommendation, confidence.
    """
    results = []
    case_subset = cases[:max_cases] if max_cases else cases

    for case in case_subset:
        case_id = case['case_id']
        print(f"\n[{provider.upper()}] Case {case_id}...")

        # Prepare images
        images = prepare_document_images_tiered(case)

        # Time the analysis
        start = time.time()
        try:
            analysis, meta = analyze_case(
                case=case,
                images=images,
                provider=provider,
                benchmark=True if provider == "openai" else False
            )
            elapsed = time.time() - start

            # Get actual token usage from metadata if available
            tokens_used = analysis.get("llm_tokens_used", 0)
            prompt_tokens = analysis.get("llm_prompt_tokens", 0)
            completion_tokens = analysis.get("llm_completion_tokens", 0)

            result = {
                "case_id": case_id,
                "provider": provider,
                "success": "error" not in analysis,
                "recommendation": analysis.get("recommendation", "unknown"),
                "confidence_score": analysis.get("confidence_score", 0),
                "analysis_mode": analysis.get("analysis_mode", "unknown"),
                "llm_tokens_used": tokens_used,
                "llm_prompt_tokens": prompt_tokens,
                "llm_completion_tokens": completion_tokens,
                "elapsed_seconds": round(elapsed, 2),
                "error": analysis.get("error") if "error" in analysis else None,
                "provider_used": analysis.get("provider_used", provider),
            }
        except Exception as e:
            elapsed = time.time() - start
            result = {
                "case_id": case_id,
                "provider": provider,
                "success": False,
                "recommendation": "error",
                "confidence_score": 0,
                "analysis_mode": "error",
                "llm_tokens_used": 0,
                "elapsed_seconds": round(elapsed, 2),
                "error": str(e),
                "provider_used": provider,
            }

        results.append(result)
        print(f"  → {result['recommendation']} | conf: {result['confidence_score']} | time: {result['elapsed_seconds']}s | tokens: {result['llm_tokens_used']}")

        # Rate limit: sleep between cases to avoid 429
        if provider == "kimi":
            time.sleep(2)

    return results


def compute_summary(results):
    """Aggregate metrics across all case results."""
    by_provider = {}
    for r in results:
        p = r["provider"]
        if p not in by_provider:
            by_provider[p] = []
        by_provider[p].append(r)

    summary = {}
    for provider, provider_results in by_provider.items():
        total = len(provider_results)
        successes = sum(1 for r in provider_results if r["success"])
        avg_conf = sum(r["confidence_score"] for r in provider_results) / total if total else 0
        avg_time = sum(r["elapsed_seconds"] for r in provider_results) / total if total else 0
        total_tokens = sum(r["llm_tokens_used"] for r in provider_results)
        errors = [r for r in provider_results if not r["success"]]

        # Cost estimates using actual input/output rates
        # Kimi: $0.001/1K input, $0.003/1K output
        # OpenAI GPT-4o: $0.005/1K input, $0.015/1K output  
        # Claude: $0.003/1K input, $0.015/1K output
        rates = {
            "kimi": {"input": 0.001, "output": 0.003},
            "openai": {"input": 0.005, "output": 0.015},
            "claude": {"input": 0.003, "output": 0.015}
        }
        provider_rates = rates.get(provider, {"input": 0.001, "output": 0.003})

        # Calculate using actual prompt/completion split if available
        total_prompt = sum(r.get("llm_prompt_tokens", 0) or r.get("llm_tokens_used", 0) // 2 for r in provider_results)
        total_completion = sum(r.get("llm_completion_tokens", 0) or r.get("llm_tokens_used", 0) // 2 for r in provider_results)

        input_cost = (total_prompt / 1000) * provider_rates["input"]
        output_cost = (total_completion / 1000) * provider_rates["output"]
        estimated_cost = input_cost + output_cost

        summary[provider] = {
            "total_cases": total,
            "success_rate": successes / total if total else 0,
            "avg_confidence": round(avg_conf, 1),
            "avg_response_time_sec": round(avg_time, 2),
            "total_tokens": total_tokens,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "estimated_input_cost_usd": round(input_cost, 4),
            "estimated_output_cost_usd": round(output_cost, 4),
            "estimated_total_cost_usd": round(estimated_cost, 4),
            "errors": len(errors),
            "error_details": [{"case_id": e["case_id"], "error": e["error"]} for e in errors],
        }

    return summary


def main():
    parser = argparse.ArgumentParser(description="Benchmark chargeback analyzer across LLM providers")
    parser.add_argument("--providers", nargs="+", default=["kimi", "openai"],
                        choices=["kimi", "openai", "claude"],
                        help="Providers to benchmark")
    parser.add_argument("--output", default="benchmark_results.json",
                        help="Path to save JSON results")
    parser.add_argument("--max-cases", type=int, default=None,
                        help="Limit number of cases (for quick testing)")
    args = parser.parse_args()

    cases = load_cases()
    print(f"Loaded {len(cases)} cases")
    if args.max_cases:
        print(f"Limiting to first {args.max_cases} cases")

    all_results = []
    for provider in args.providers:
        print(f"\n{'='*60}")
        print(f"BENCHMARKING: {provider.upper()}")
        print(f"{'='*60}")
        provider_results = benchmark_provider(provider, cases, max_cases=args.max_cases)
        all_results.extend(provider_results)

    summary = compute_summary(all_results)

    output = {
        "benchmark_date": datetime.now().isoformat(),
        "providers_tested": args.providers,
        "total_cases": len(cases),
        "per_case_results": all_results,
        "summary": summary,
    }

    with open(args.output, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n{'='*60}")
    print("BENCHMARK COMPLETE")
    print(f"{'='*60}")
    print(f"Results saved to: {args.output}")
    print("\nSummary:")
    for provider, stats in summary.items():
        print(f"\n  {provider.upper()}:")
        print(f"    Success rate: {stats['success_rate']*100:.0f}%")
        print(f"    Avg confidence: {stats['avg_confidence']}")
        print(f"    Avg response time: {stats['avg_response_time_sec']}s")
        print(f"    Total tokens: {stats['total_tokens']}")
        print(f"    Est. cost: ${stats['estimated_cost_usd']}")
        if stats['errors']:
            print(f"    Errors: {stats['errors']}")


if __name__ == "__main__":
    main()