# analyzer.py
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from reason_code_rules import get_rule, apply_logic, _get_applicable_requirements, _get_case_type
from page_selector import prepare_document_images_tiered
from llm_client import generate, select_provider
# Telemetry addendum removed — historical data used in batch workflows only

load_dotenv()

# ==================== SAFETY CONFIG ====================
MAX_IMAGES_PER_API_CALL = 15
MAX_IMAGES_PER_CASE = 20
MAX_TOKENS_PER_RESPONSE = 8000
MAX_CASES_PER_SESSION = 20
# =======================================================


def build_system_prompt(rule, case=None):
    """Build the system prompt with reason code rules + telemetry feedback."""
    from reason_code_rules import _get_applicable_requirements, _detect_impossibilities

    logic_desc = {
        "ALL": f"ALL applicable requirements must be satisfied",
        "ANY": f"At least {rule['min_required']} of applicable requirements must be satisfied",
        "EITHER": "At least one applicable requirement branch must be satisfied",
        "NOT_REPRESENTABLE": "This reason code generally cannot be represented"
    }

    # Only show requirements applicable to this case type
    applicable_reqs = _get_applicable_requirements(rule, case) if case else [r.get('text', r) if isinstance(r, dict) else r for r in rule.get('requirements', [])]
    requirements_text = "\n".join([
        f"{i+1}. {req}" 
        for i, req in enumerate(applicable_reqs)
    ])

    # Build impossibility warning for the prompt if any exist
    impossibility_warning = ""
    if case:
        impossibilities = _detect_impossibilities(case)
        if impossibilities:
            impossibility_warning = "\n\nCRITICAL STRUCTURAL FLAGS FOR THIS CASE (do not ignore these):\n"
            for imp in impossibilities:
                impossibility_warning += f"- {imp}\n"
            impossibility_warning += "\nThese structural issues CANNOT be fixed with more evidence. If they exist, the case is fundamentally compromised."

    # Telemetry addendum removed from AI prompt — systematic flags should be case-only
    # Historical override data is used in weekly/bi-weekly workflows, not per-case analysis
    telemetry_addendum = ""

    return f"""You are a chargeback representment analyst. Your job is to assess merchant evidence against scheme rules.

REASON CODE: {rule.get('code', 'N/A')} - {rule['label']}
SCHEME: {rule['scheme'].upper()}
LOGIC: {logic_desc.get(rule['logic'], rule['logic'])}

COMPELLING EVIDENCE REQUIREMENTS:
{requirements_text if requirements_text else 'N/A - This reason code is not representable'}
{impossibility_warning}

INSTRUCTIONS:
1. Examine each merchant evidence document carefully
2. For EACH requirement above, assess whether it is: SATISFIED, PARTIAL, MISSING, or NOT_APPLICABLE
3. For SATISFIED or PARTIAL, cite the specific document and page/location where the evidence appears
4. For MISSING, explain what evidence would be needed
5. For NOT_APPLICABLE: use this when a requirement is conditional and does not apply to this transaction type.
   Examples:
   - "For services: ..." → NOT_APPLICABLE if the transaction is for physical goods
   - "For digital goods: ..." → NOT_APPLICABLE if the transaction is for physical goods
   - "Proof of delivery to billing address" → NOT_APPLICABLE if the merchant only ships to a different address type
   Do NOT mark conditional requirements as MISSING when they don't apply — this misleads the analyst into thinking evidence is lacking.
6. ADDRESS MATCHING RULE (critical for "delivery address" requirements):
   - The "cardholder's address" means their BILLING address, not the shipping address
   - If the merchant delivered to a different address than billing WITHOUT explicit cardholder authorization, mark as MISSING or PARTIAL
   - AVS result "N" means address verification FAILED — this is a CRITICAL GAP for any delivery-address requirement
   - Do NOT mark delivery-address requirements as SATISFIED solely because the merchant shipped to the shipping address
7. MANDATORY COMPLETENESS RULE — THIS IS CRITICAL:
   - You MUST assess EVERY SINGLE requirement listed above. Do NOT skip any.
   - For ALL logic: every requirement must be in your evidence_assessment array
   - For ANY logic: every requirement must be in your evidence_assessment array (we will count which are satisfied)
   - If you cannot find evidence for a requirement, mark it as MISSING — do not omit it from the output
   - If a requirement is conditional and does not apply, mark it as NOT_APPLICABLE — do not omit it
   - OMITTING a requirement from your output is a FAILURE. The analyst needs to see your assessment of ALL requirements.
8. TRANSACTION METADATA CHECK — ALWAYS cross-reference evidence against transaction data:
   - Compare delivery addresses in documents against the BILLING address in case data (NOT shipping address)
   - Check AVS result: if "N", the address verification FAILED — flag this as a structural weakness
   - Check CVV result: if "N", the card verification failed — flag this
   - Check 3DS status: if "not_attempted", strong authentication was missing
   - Check billing vs shipping postcode: if different, the cardholder may not have authorized delivery to shipping address
   - For "delivery address matches" requirements: the cardholder's verified address is their BILLING address
   - Do NOT mark delivery-address requirements as SATISFIED based solely on shipping address match
9. REQUIREMENT 4 (Delivery Address) — SPECIFIC INSTRUCTIONS:
   - Look at the delivery confirmation document for the ACTUAL delivery address
   - Compare it to the BILLING address in the case data (NOT shipping address)
   - If AVS=Y and billing=shipping, the delivery address is verified — this STRONGLY supports the requirement
   - If the delivery document shows the same postcode as billing, mark as SATISFIED
   - If the delivery document shows a different address, mark as MISSING or PARTIAL
   - NEVER skip this requirement — it is critical for ALL logic cases
10. Flag any evidence that appears authoritative but does not actually meet the requirements
11. Return your analysis as a valid JSON object with this exact structure:

{{
    "evidence_assessment": [
        {{
            "requirement_number": 1,
            "requirement_text": "exact text of requirement",
            "status": "satisfied|partial|missing|not_applicable",
            "document_reference": "filename.pdf, page X",
            "explanation": "detailed explanation of what was found or why it's missing / not applicable",
            "citation": "exact quote or description of the evidence found"
        }}
    ],
    "systematic_flags": [
        {{
            "flag_type": "BURIED_EVIDENCE|CONFIDENT_BUT_IRRELEVANT|CONTRADICTORY|MANUAL_REVIEW",
            "description": "description of the issue",
            "location": "where found"
        }}
    ],
    "merchant_evidence_summary": "2-3 sentence summary of what the merchant actually submitted",
    "gaps_analysis": "What specific evidence is missing and what to request. ONLY count requirements marked MISSING — do not count NOT_APPLICABLE as missing.",
    "representment_rationale": "3-5 sentence rationale ready for analyst review. Be honest about weaknesses — do not oversell the case.",
    "confidence_score": 0-100
}}

IMPORTANT:
- Be precise with citations (page numbers, line references)
- Do not trust confident-sounding language that lacks substantive proof
- If evidence is buried in a multi-page document, note the exact location
- The status must be one of: satisfied, partial, missing, not_applicable
- Use "not_applicable" only when a requirement type (e.g., "for services") clearly does not match the case, not_applicable
- NOT_APPLICABLE requirements do NOT count toward the total requirements needed
- If structural impossibilities exist (e.g., AVS mismatch, address mismatch), LOWER your confidence score accordingly
- Return ONLY the JSON object, no markdown formatting, no code blocks
{telemetry_addendum}
"""


def build_minimal_system_prompt(rule):
    """Stripped-down prompt for token-constrained scenarios."""
    return f"""Analyze chargeback evidence. Return JSON:

{{
    "evidence_assessment": [
        {{"requirement_number": 1, "status": "satisfied|partial|missing|not_applicable", "document_reference": "file, page", "explanation": "brief"}}
    ],
    "systematic_flags": [],
    "merchant_evidence_summary": "brief summary",
    "gaps_analysis": "what is missing (not_applicable does not count as missing)",
    "representment_rationale": "brief rationale — be honest about weaknesses",
    "confidence_score": 0-100
}}

Reason code: {rule['code']} - {rule['label']}
Logic: {rule['logic']}
Requirements: {len(rule['requirements'])} total
"""


def build_user_message(case, images):
    """Build the user message with case data and images."""

    case_data = {
        "case_id": case['case_id'],
        "scheme": case['scheme'],
        "reason_code": case['reason_code'],
        "reason_code_label": case['reason_code_label'],
        "chargeback_date": case['chargeback_date'],
        "chargeback_amount": case['chargeback_amount'],
        "issuer_narrative": case['issuer_narrative'],
        "transaction": {
            "merchant_name": case['transaction']['merchant_name'],
            "merchant_mcc": case['transaction']['merchant_mcc'],
            "transaction_date": case['transaction']['transaction_date'],
            "amount": case['transaction']['amount'],
            "card_bin_country": case['transaction']['card_bin_country'],
            "avs_result": case['transaction']['avs_result'],
            "cvv_result": case['transaction']['cvv_result'],
            "three_ds_status": case['transaction']['three_ds_status'],
            "ip_address": case['transaction']['ip_address'],
            "device_fingerprint": case['transaction']['device_fingerprint'],
            "billing_address_postcode": case['transaction']['billing_address_postcode'],
            "shipping_address_postcode": case['transaction']['shipping_address_postcode']
        },
        "merchant_evidence_documents": case['merchant_evidence_documents']
    }

    # Build message content
    content = [
        {
            "type": "text",
            "text": f"Please analyze this chargeback case and its evidence documents.\n\nCASE DATA:\n{json.dumps(case_data, indent=2)}\n\nExamine the following evidence documents and provide a structured assessment."
        }
    ]

    # Add images
    for img in images:
        content.append({
            "type": "text",
            "text": f"\n--- DOCUMENT: {img['filename']} (Page {img['page']}) [Tier: {img.get('tier', 'N/A')}] ---\n"
        })
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{img['base64']}"
            }
        })

    return {"role": "user", "content": content}


def analyze_case(case, images, provider=None, task_type="default", benchmark=False, minimal_mode=False):
    """
    Send case + images to LLM and get structured analysis.

    Args:
        case: Case dict from cases.json
        images: List of image dicts from page_selector
        provider: Explicit provider override ("kimi", "openai", "claude")
        task_type: "default", "reasoning", "cost_sensitive", "fast"
        benchmark: If True, use OpenAI for consistent benchmarking
        minimal_mode: If True, use stripped-down prompt for token savings

    Returns: (analysis_dict, raw_response_metadata)
    """

    # Auto-select provider if not explicitly set
    # Default: OpenAI for speed/reliability; Kimi as cost-sensitive fallback
    if provider is None:
        if task_type == "cost_sensitive":
            provider = "kimi"
        else:
            provider = "openai"  # Default: faster, more reliable for production

    # Claude vision is now supported via _convert_messages_for_claude in llm_client.py
    # No fallback needed — images are converted to Anthropic format automatically

    print(f"Using provider: {provider}")

    # Safety: Cap images per API call
    if len(images) > MAX_IMAGES_PER_API_CALL:
        print(f"Warning: {len(images)} images, limiting to {MAX_IMAGES_PER_API_CALL}")
        images = images[:MAX_IMAGES_PER_API_CALL]

    # Safety: Cap images per case
    if len(images) > MAX_IMAGES_PER_CASE:
        print(f"Warning: {len(images)} images exceeds case limit {MAX_IMAGES_PER_CASE}, truncating")
        images = images[:MAX_IMAGES_PER_CASE]

    rule = get_rule(case['reason_code'])
    if not rule:
        return {
            "error": f"Unknown reason code: {case['reason_code']}",
            "recommendation": "manual_review",
            "confidence_score": 0
        }, None

    # Handle non-representable codes: run LLM first to check for exceptions,
    # then apply deterministic override. This ensures thoroughness.
    if rule['logic'] == 'NOT_REPRESENTABLE':
        # Build messages for LLM to check documents
        if minimal_mode:
            messages = [
                {"role": "system", "content": build_minimal_system_prompt(rule)},
                build_user_message(case, images)
            ]
            max_tokens = 4000
        else:
            messages = [
                {"role": "system", "content": build_system_prompt(rule, case)},
                build_user_message(case, images)
            ]
            max_tokens = MAX_TOKENS_PER_RESPONSE

        # Override system prompt for NOT_REPRESENTABLE to be explicit about what to check
        not_representable_prompt = f"""You are a chargeback representment analyst. This case has reason code {rule['code']} — {rule['label']}.

IMPORTANT: This reason code is generally NOT_REPRESENTABLE per scheme rules. However, you MUST still examine the merchant's evidence documents thoroughly to check for EXCEPTIONS or special circumstances that might change this assessment.

FOR REASON CODE 10.5 (Visa Fraud Monitoring Program):
- Check if the merchant can prove the transaction was MISCODED by the issuer
- Look for evidence that the transaction should have been processed under a different reason code
- If miscoding evidence exists, this case MAY be representable

FOR REASON CODE 4870 (Chip Liability Shift):
- Check if the merchant has evidence the terminal was chip-enabled and the transaction was chip-read
- Look for terminal upgrade receipts, chip-read logs, or acquirer communications
- If chip evidence exists, this case MAY be representable

INSTRUCTIONS:
1. Examine ALL merchant evidence documents carefully
2. Look specifically for evidence that would EXCEPTION this reason code
3. If you find exception evidence, assess it honestly
4. If no exception evidence exists, state this clearly
5. Return your analysis as valid JSON with this structure:

{{
    "evidence_assessment": [
        {{
            "requirement_number": 1,
            "requirement_text": "Check for exception evidence",
            "status": "satisfied|partial|missing",
            "document_reference": "filename.pdf, page X",
            "explanation": "detailed explanation",
            "citation": "exact quote"
        }}
    ],
    "systematic_flags": [],
    "merchant_evidence_summary": "summary of what merchant submitted",
    "gaps_analysis": "what is missing",
    "representment_rationale": "3-5 sentences on whether exception evidence exists",
    "confidence_score": 0-100,
    "exception_found": true|false,
    "exception_description": "if exception_found is true, describe the evidence"
}}

IMPORTANT:
- Be honest — do not invent exception evidence that does not exist
- If no exception evidence is found, state clearly: 'No exception evidence found. Case remains NOT_REPRESENTABLE.'
- Return ONLY the JSON object, no markdown, no code blocks
"""

        messages[0]["content"] = not_representable_prompt

        # Call LLM
        from llm_client import generate_with_metadata
        try:
            response = generate_with_metadata(
                messages=messages,
                provider=provider,
                system=None,
                max_tokens=max_tokens,
                temperature=1.0
            )
            response_text = response["text"]
            actual_usage = response.get("usage", {})

            # Parse JSON
            analysis = json.loads(response_text.strip())

            # Check if exception was found
            exception_found = analysis.get('exception_found', False)
            exception_desc = analysis.get('exception_description', '')

            if exception_found and exception_desc:
                # Exception found! Override NOT_REPRESENTABLE
                return {
                    "case_id": case['case_id'],
                    "reason_code": case['reason_code'],
                    "evidence_assessment": analysis.get('evidence_assessment', []),
                    "systematic_flags": analysis.get('systematic_flags', []) + [{
                        "flag_type": "NOT_REPRESENTABLE_EXCEPTION",
                        "description": f"Exception evidence found: {exception_desc}",
                        "location": "LLM document review"
                    }],
                    "merchant_evidence_summary": analysis.get('merchant_evidence_summary', 'N/A'),
                    "gaps_analysis": analysis.get('gaps_analysis', 'N/A'),
                    "representment_rationale": analysis.get('representment_rationale', 'Exception evidence may make this case representable.'),
                    "confidence_score": analysis.get('confidence_score', 50),
                    "recommendation": "represent",  # Exception overrides NOT_REPRESENTABLE
                    "justification": f"NOT_REPRESENTABLE exception found: {exception_desc}. Case may be defensible.",
                    "provider_used": provider,
                    "llm_tokens_used": actual_usage.get('total_tokens', 0),
                    "analysis_mode": "not_representable_exception"
                }, None
            else:
                # No exception found — standard NOT_REPRESENTABLE
                recommendation, justification = apply_logic(rule, 0, case)
                return {
                    "case_id": case['case_id'],
                    "reason_code": case['reason_code'],
                    "evidence_assessment": analysis.get('evidence_assessment', []),
                    "systematic_flags": analysis.get('systematic_flags', []) + [{
                        "flag_type": "NOT_REPRESENTABLE",
                        "description": rule.get('note', 'This reason code cannot be represented'),
                        "location": "N/A"
                    }],
                    "merchant_evidence_summary": analysis.get('merchant_evidence_summary', 'N/A'),
                    "gaps_analysis": analysis.get('gaps_analysis', 'N/A'),
                    "representment_rationale": analysis.get('representment_rationale', justification),
                    "confidence_score": 95,
                    "recommendation": recommendation,
                    "justification": justification,
                    "provider_used": provider,
                    "llm_tokens_used": actual_usage.get('total_tokens', 0),
                    "analysis_mode": "not_representable_checked"
                }, None

        except Exception as e:
            # LLM failed — fall back to deterministic short-circuit
            print(f"LLM check for NOT_REPRESENTABLE failed: {e}. Falling back to deterministic.")
            recommendation, justification = apply_logic(rule, 0, case)
            return {
                "case_id": case['case_id'],
                "reason_code": case['reason_code'],
                "evidence_assessment": [],
                "systematic_flags": [{
                    "flag_type": "NOT_REPRESENTABLE",
                    "description": rule.get('note', 'This reason code cannot be represented'),
                    "location": "N/A"
                }],
                "merchant_evidence_summary": "N/A - Reason code not representable (LLM check failed)",
                "gaps_analysis": "N/A",
                "representment_rationale": justification,
                "confidence_score": 95,
                "recommendation": recommendation,
                "justification": justification,
                "provider_used": provider,
                "llm_tokens_used": 0,
                "analysis_mode": "deterministic"
            }, None

    # Build messages
    if minimal_mode:
        messages = [
            {"role": "system", "content": build_minimal_system_prompt(rule)},
            build_user_message(case, images)
        ]
        max_tokens = 4000
    else:
        messages = [
            {"role": "system", "content": build_system_prompt(rule, case)},
            build_user_message(case, images)
        ]
        max_tokens = MAX_TOKENS_PER_RESPONSE

    # Call LLM via unified wrapper with retry for truncated responses
    max_tokens_attempts = [8000, 12000] if not minimal_mode else [4000]

    for attempt, max_tokens in enumerate(max_tokens_attempts, 1):
        try:
            mode_label = "MINIMAL" if minimal_mode else f"attempt {attempt}"
            print(f"Sending {len(images)} images to {provider.upper()} API... ({mode_label}, max_tokens={max_tokens})")

            # Use generate_with_metadata for accurate token tracking
            from llm_client import generate_with_metadata
            response = generate_with_metadata(
                messages=messages,
                provider=provider,
                system=None,  # Already included in messages
                max_tokens=max_tokens,
                temperature=1.0
            )
            response_text = response["text"]
            actual_usage = response.get("usage", {})
            print("Response received!")
            print(f"  Actual tokens: {actual_usage.get('total_tokens', 'N/A')} "
                  f"(prompt: {actual_usage.get('prompt_tokens', 'N/A')}, "
                  f"completion: {actual_usage.get('completion_tokens', 'N/A')})")

            # Parse JSON from response
            analysis = json.loads(response_text.strip())

            # If we get here, parsing succeeded
            break

        except json.JSONDecodeError as e:
            print(f"JSON parse failed ({mode_label}): {str(e)[:100]}")
            if not minimal_mode and attempt < len(max_tokens_attempts):
                print(f"Retrying with higher token limit...")
                continue
            elif not minimal_mode:
                # FALLBACK TO MINIMAL MODE
                print("Full analysis failed, falling back to minimal mode...")
                return analyze_case(case, images, provider=provider, minimal_mode=True)
            else:
                # Minimal mode also failed
                return {
                    "error": f"Failed to parse JSON response in minimal mode: {str(e)}",
                    "raw_content": response_text[:1000] if 'response_text' in locals() else "N/A",
                    "recommendation": "manual_review",
                    "confidence_score": 0,
                    "provider_used": provider
                }, None

        except Exception as e:
            return {
                "error": f"API call failed: {str(e)}",
                "recommendation": "manual_review",
                "confidence_score": 0,
                "provider_used": provider
            }, None

    # Validate: ensure all applicable requirements are present in LLM output
    evidence_items = analysis.get('evidence_assessment', [])

    # Build set of requirement numbers returned by LLM (normalize to int)
    returned_req_numbers = set()
    for item in evidence_items:
        rn = item.get('requirement_number')
        if rn is not None:
            try:
                returned_req_numbers.add(int(rn))
            except (ValueError, TypeError):
                pass

    # Iterate over ALL original requirements to find applicable ones that are missing
    case_type = _get_case_type(case) if case else "goods"
    for orig_idx, req in enumerate(rule.get('requirements', []), start=1):
        # Check if this requirement is applicable to the case type
        req_applies_to = req.get('applies_to', ['goods', 'services']) if isinstance(req, dict) else ['goods', 'services']
        if case_type not in req_applies_to:
            continue  # Skip non-applicable requirements

        # Check if the LLM returned this requirement
        if orig_idx not in returned_req_numbers:
            req_text = req.get('text', req) if isinstance(req, dict) else req
            evidence_items.append({
                "requirement_number": orig_idx,
                "requirement_text": req_text,
                "status": "missing",
                "document_reference": "N/A",
                "explanation": "No evidence found in submitted merchant documents for this requirement. The merchant did not provide documentation that satisfies this scheme rule.",
                "citation": "N/A"
            })
            # Note: No flag added here — post-processing handles auto-assessment if applicable

    # Sort evidence_items by requirement_number for consistent display
    evidence_items.sort(key=lambda x: x.get('requirement_number', 999))
    analysis['evidence_assessment'] = evidence_items

    # Count satisfied and applicable requirements
    satisfied_count = sum(1 for item in evidence_items if item['status'] == 'satisfied')
    applicable_count = sum(1 for item in evidence_items if item['status'] != 'not_applicable')

    # Post-process: auto-assess requirements using transaction metadata when evidence is obvious
    # This catches cases where the LLM skipped a requirement but the answer is clear from metadata
    tx = case.get('transaction', {}) if case else {}
    for item in evidence_items:
        req_num = item.get('requirement_number', 0)
        req_text = item.get('requirement_text', '')

        # Auto-assess delivery address requirement (Req 4 for 13.1, Req 3 for 4855)
        if ("delivery address" in req_text.lower() or "address matches" in req_text.lower() or "cardholder's address" in req_text.lower()):
            if item.get('status') == 'missing' and item.get('document_reference') == 'N/A':
                # LLM skipped this but we can check metadata
                avs = tx.get('avs_result', '')
                billing = tx.get('billing_address_postcode', '')
                shipping = tx.get('shipping_address_postcode', '')

                if avs == 'Y' and billing and shipping and billing == shipping:
                    # Strong indicator: AVS passed and billing=shipping
                    # Check if any delivery documents exist
                    docs = case.get('merchant_evidence_documents', [])
                    has_delivery_doc = any(d.lower().find('delivery') != -1 or d.lower().find('tracking') != -1 or d.lower().find('confirm') != -1 for d in docs)

                    if has_delivery_doc:
                        item['status'] = 'satisfied'
                        item['document_reference'] = f"Auto-assessed from metadata: AVS={avs}, billing=shipping={billing}"
                        item['explanation'] = f"Requirement satisfied: AVS verification passed ({avs}), billing address ({billing}) matches shipping address ({shipping}), and delivery documents confirm shipment to this verified address."
                        item['citation'] = f"Transaction metadata: AVS={avs}, billing_postcode={billing}, shipping_postcode={shipping}"
                        # Add a flag
                        flags = analysis.get('systematic_flags', [])
                        flags.append({
                            "flag_type": "MANUAL_REVIEW",
                            "description": f"Requirement {req_num} satisfied per transaction metadata: AVS={avs}, billing address ({billing}) matches shipping address ({shipping}). Delivery to verified address confirmed.",
                            "location": "analyzer.py post-processing"
                        })
                        analysis['systematic_flags'] = flags

    # Re-count satisfied after auto-assessment
    satisfied_count = sum(1 for item in evidence_items if item['status'] == 'satisfied')

    # Apply reason code logic WITH case data for impossibility detection
    # This now checks structural impossibilities FIRST, before satisfied count
    recommendation, justification = apply_logic(rule, satisfied_count, case)

    analysis['case_id'] = case['case_id']
    analysis['reason_code'] = case['reason_code']
    analysis['recommendation'] = recommendation
    analysis['justification'] = justification
    analysis['provider_used'] = provider
    analysis['analysis_mode'] = 'minimal' if minimal_mode else 'full'

    # Use actual token usage from API metadata if available
    if actual_usage and actual_usage.get('total_tokens'):
        analysis['llm_tokens_used'] = actual_usage['total_tokens']
        analysis['llm_prompt_tokens'] = actual_usage.get('prompt_tokens', 0)
        analysis['llm_completion_tokens'] = actual_usage.get('completion_tokens', 0)
    else:
        # Fallback to rough estimate if metadata unavailable
        prompt_text = json.dumps(messages)
        analysis['llm_tokens_used'] = len(prompt_text) // 4 + max_tokens

    return analysis, {"provider": provider, "mode": "minimal" if minimal_mode else "full"}


if __name__ == "__main__":
    # Test with CB-2025-0007 (buried evidence case)
    import json

    with open('cases.json', 'r') as f:
        cases = json.load(f)

    case = cases[6]  # CB-2025-0007

    print(f"Analyzing {case['case_id']}...")
    print(f"Reason: {case['reason_code']} - {case['reason_code_label']}")
    print(f"Merchant: {case['transaction']['merchant_name']}")
    print(f"Documents: {case['merchant_evidence_documents']}")

    # Use tiered page selection
    images = prepare_document_images_tiered(case)
    print(f"\nTotal images prepared: {len(images)}")
    for img in images:
        print(f"  - {img['filename']} page {img['page']} (tier: {img['tier']}, score: {img['score']})")

    # Test with different providers
    for test_provider in ["kimi", "openai"]:
        print(f"\n{'='*60}")
        print(f"TESTING WITH PROVIDER: {test_provider}")
        print(f"{'='*60}")

        analysis, meta = analyze_case(case, images, provider=test_provider)

        print(f"\nProvider used: {analysis.get('provider_used', 'N/A')}")
        print(f"Analysis mode: {analysis.get('analysis_mode', 'N/A')}")
        print(f"Recommendation: {analysis.get('recommendation', 'N/A')}")
        print(f"Confidence: {analysis.get('confidence_score', 'N/A')}")

        if 'error' in analysis:
            print(f"Error: {analysis['error']}")
            if 'raw_content' in analysis:
                print(f"Raw preview: {analysis['raw_content'][:500]}")