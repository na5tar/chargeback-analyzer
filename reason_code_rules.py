"""
Simplified compelling evidence rules from Reason Codes.pdf (provided in challenge materials).
These are deliberately simplified for the exercise — real scheme rules have time limits,
dollar thresholds, exclusions, and are updated regularly.
Source: Challenge dataset, Reason Codes.pdf
"""

REASON_CODE_RULES = {
    "10.4": {
        "scheme": "visa",
        "label": "Other Fraud, Card Absent Environment",
        "logic": "ANY",
        "min_required": 2,
        "requirements": [
            {"text": "Evidence the cardholder used the same card and same shipping address in two prior undisputed transactions with this merchant, completed more than 120 days but less than 365 days before the disputed transaction", "applies_to": ["goods", "services", "digital"]},
            {"text": "Evidence the cardholder is in possession of and using the merchandise (e.g. signed-in account activity post-delivery, social media post tagging the merchant)", "applies_to": ["goods"]},
            {"text": "For digital goods: device fingerprint, IP address, geolocation, and customer account login matching prior undisputed transactions", "applies_to": ["digital"]},
            {"text": "Proof of delivery to the cardholder's verified billing address (not just shipping address) with signature confirmation", "applies_to": ["goods", "services", "digital"]}
        ]
    },
    "10.5": {
        "scheme": "visa",
        "label": "Visa Fraud Monitoring Program",
        "logic": "NOT_REPRESENTABLE",
        "min_required": 0,
        "requirements": [],
        "note": "This reason code generally cannot be represented. Recommend accept_liability unless the merchant can prove the transaction was miscoded by the issuer."
    },
    "12.5": {
        "scheme": "visa",
        "label": "Incorrect Amount",
        "logic": "ALL",
        "min_required": 3,
        "requirements": [
            {"text": "The signed receipt, terms of service, or order confirmation showing the amount the cardholder agreed to", "applies_to": ["goods", "services", "digital"]},
            {"text": "Documentation showing the amount charged matches that agreed amount", "applies_to": ["goods", "services", "digital"]},
            {"text": "If a tip, gratuity, or adjustment was added, evidence the cardholder authorised it", "applies_to": ["goods", "services", "digital"]}
        ]
    },
    "12.6.1": {
        "scheme": "visa",
        "label": "Duplicate Processing",
        "logic": "ALL",
        "min_required": 3,
        "requirements": [
            {"text": "Evidence the two transactions are for two separate purchases (e.g. different order IDs, different items, different services rendered)", "applies_to": ["goods", "services", "digital"]},
            {"text": "Documentation of each purchase event (separate invoices, separate delivery confirmations, separate service dates)", "applies_to": ["goods", "services", "digital"]},
            {"text": "Transaction timestamps and authorisation codes for each charge", "applies_to": ["goods", "services", "digital"]}
        ]
    },
    "13.1": {
        "scheme": "visa",
        "label": "Merchandise / Services Not Received",
        "logic": "ALL",
        "min_required": 4,
        "requirements": [
            {"text": "Proof of delivery: tracking number, carrier name, and confirmation of delivery to the cardholder's address", "applies_to": ["goods", "services", "digital"]},
            {"text": "For services: evidence the service was rendered on or before the expected date (booking confirmation, attendance log, access logs)", "applies_to": ["services"]},
            {"text": "Date of delivery / service rendered is on or before the chargeback date", "applies_to": ["goods", "services", "digital"]},
            {"text": "The delivery address materially matches the address provided by the cardholder at purchase", "applies_to": ["goods", "services", "digital"]}
        ]
    },
    "13.2": {
        "scheme": "visa",
        "label": "Cancelled Recurring Transaction",
        "logic": "ALL",
        "min_required": 4,
        "requirements": [
            {"text": "Terms of service disclosing the recurring billing arrangement and the cancellation method", "applies_to": ["goods", "services", "digital"]},
            {"text": "Evidence the cardholder was notified of the upcoming charge (typically 7+ days in advance) for transactions over a defined threshold", "applies_to": ["goods", "services", "digital"]},
            {"text": "No record of the cardholder having submitted a cancellation request prior to the billing date", "applies_to": ["goods", "services", "digital"]},
            {"text": "Evidence of the cardholder's original opt-in to the recurring arrangement", "applies_to": ["goods", "services", "digital"]}
        ]
    },
    "13.3": {
        "scheme": "visa",
        "label": "Not as Described or Defective Merchandise",
        "logic": "ALL",
        "min_required": 3,
        "requirements": [
            {"text": "The merchant's published description of the item the cardholder purchased", "applies_to": ["goods", "services", "digital"]},
            {"text": "Evidence the item delivered matches that description (photos, specs, serial number match)", "applies_to": ["goods"]},
            {"text": "Evidence the merchant offered a return/refund route and the cardholder did not use it, OR evidence the cardholder used and retained the merchandise after raising the complaint", "applies_to": ["goods", "services", "digital"]}
        ]
    },
    "13.6": {
        "scheme": "visa",
        "label": "Credit Not Processed",
        "logic": "EITHER",
        "min_required": 1,
        "requirements": [
            {"text": "Evidence that a refund was processed (refund transaction ID, date, amount)", "applies_to": ["goods", "services", "digital"]},
            {"text": "Evidence that no refund was ever agreed (merchant's refund policy and absence of any refund commitment in cardholder communications)", "applies_to": ["goods", "services", "digital"]}
        ]
    },
    "13.7": {
        "scheme": "visa",
        "label": "Cancelled Merchandise / Services",
        "logic": "ALL",
        "min_required": 3,
        "requirements": [
            {"text": "The merchant's cancellation policy as displayed at point of sale", "applies_to": ["goods", "services", "digital"]},
            {"text": "Evidence the cardholder agreed to that policy (e.g. checkbox click record, signed terms)", "applies_to": ["goods", "services", "digital"]},
            {"text": "Evidence the cardholder either did not cancel within the policy window, or cancelled outside the refundable period", "applies_to": ["goods", "services", "digital"]}
        ]
    },
    "4837": {
        "scheme": "mastercard",
        "label": "No Cardholder Authorisation",
        "logic": "ANY",
        "min_required": 2,
        "requirements": [
            {"text": "AVS match (full address) AND CVV match on the disputed transaction", "applies_to": ["goods", "services", "digital"]},
            {"text": "3D Secure authentication completed successfully (Mastercard SecureCode / Identity Check)", "applies_to": ["goods", "services", "digital"]},
            {"text": "Two prior undisputed transactions from the same cardholder with this merchant in the past 12 months, with matching billing details", "applies_to": ["goods", "services", "digital"]},
            {"text": "Proof of delivery to the cardholder's billing address with signature", "applies_to": ["goods", "services", "digital"]}
        ]
    },
    "4853": {
        "scheme": "mastercard",
        "label": "Cardholder Dispute (Goods / Services Not Provided)",
        "logic": "ALL",
        "min_required": 3,
        "requirements": [
            {"text": "Proof of delivery or service provision (tracking, confirmation, access log)", "applies_to": ["goods", "services", "digital"]},
            {"text": "Evidence the goods or services materially match what was advertised", "applies_to": ["goods", "services", "digital"]},
            {"text": "Either: no contact from the cardholder attempting to resolve the issue before the chargeback, OR documentation showing the merchant attempted resolution and the cardholder refused", "applies_to": ["goods", "services", "digital"]}
        ]
    },
    "4855": {
        "scheme": "mastercard",
        "label": "Goods / Services Not Provided",
        "logic": "ALL",
        "min_required": 3,
        "requirements": [
            {"text": "Proof of delivery (tracking + carrier confirmation) or proof of service rendered (access logs, attendance, completed booking)", "applies_to": ["goods", "services", "digital"]},
            {"text": "Date of delivery / service is before the chargeback date", "applies_to": ["goods", "services", "digital"]},
            {"text": "Delivery address matches the cardholder's records", "applies_to": ["goods", "services", "digital"]}
        ]
    },
    "4859": {
        "scheme": "mastercard",
        "label": "No-Show / Addendum",
        "logic": "ALL",
        "min_required": 4,
        "requirements": [
            {"text": "Evidence of the cardholder's original reservation or booking", "applies_to": ["services"]},
            {"text": "The merchant's no-show / cancellation policy as disclosed at booking", "applies_to": ["services"]},
            {"text": "Evidence the cardholder either failed to show or cancelled outside the policy window", "applies_to": ["services"]},
            {"text": "Evidence the fee charged matches the policy disclosed", "applies_to": ["services"]}
        ]
    },
    "4863": {
        "scheme": "mastercard",
        "label": "Cardholder Does Not Recognise - Potential Fraud",
        "logic": "ANY",
        "min_required": 1,
        "requirements": [
            {"text": "Evidence the merchant's billing descriptor matches the merchant name the cardholder would recognise", "applies_to": ["goods", "services", "digital"]},
            {"text": "AVS + CVV match on the disputed transaction", "applies_to": ["goods", "services", "digital"]},
            {"text": "Prior undisputed transactions from the same cardholder with this merchant", "applies_to": ["goods", "services", "digital"]},
            {"text": "Cardholder's IP / device / account login matching prior undisputed sessions", "applies_to": ["goods", "services", "digital"]}
        ]
    },
    "4870": {
        "scheme": "mastercard",
        "label": "Chip Liability Shift",
        "logic": "NOT_REPRESENTABLE",
        "min_required": 0,
        "requirements": [],
        "note": "This is a card-present reason code. For an acquiring CNP-focused exercise, expect to see accept_liability for this - we'd flag the merchant for terminal upgrade and move on."
    }
}


def get_rule(reason_code):
    """Get the rule for a reason code. Returns None if not found."""
    return REASON_CODE_RULES.get(reason_code)


def _get_case_type(case):
    """Determine if case is goods, services, or digital based on transaction data."""
    mcc = case.get('transaction', {}).get('merchant_mcc', '')
    # Digital goods MCCs
    digital_mccs = ['5815', '5816', '5817', '5818', '7997', '4899', '5999']
    # Services MCCs (hotels, travel, professional services)
    service_mccs = ['7011', '4111', '4511', '4722', '4784', '4899']

    if mcc in digital_mccs:
        return "digital"
    elif mcc in service_mccs:
        return "services"
    else:
        # Default to goods for retail/unknown
        return "goods"


def _get_applicable_requirements(rule, case):
    """Filter requirements to only those applicable to this case type."""
    case_type = _get_case_type(case)
    applicable = []
    for req in rule.get('requirements', []):
        if case_type in req.get('applies_to', ['goods', 'services']):
            applicable.append(req['text'])
    return applicable


def _detect_impossibilities(case):
    """
    Detect structural impossibilities that cannot be fixed with more evidence.
    These override any LLM assessment of requirement satisfaction.

    Returns: list of impossibility strings, or empty list if none.
    """
    impossible_reasons = []
    if not case:
        return impossible_reasons

    tx = case.get('transaction', {})

    # AVS/CVV mismatch — cannot be retroactively fixed
    if tx.get('avs_result') == 'N':
        impossible_reasons.append("AVS mismatch (address verification failed) cannot be retroactively fixed")
    if tx.get('cvv_result') == 'N':
        impossible_reasons.append("CVV mismatch cannot be retroactively fixed")

    # 3DS not attempted — cannot be applied retroactively
    if tx.get('three_ds_status') == 'not_attempted':
        impossible_reasons.append("3DS was not attempted and cannot be retroactively applied")

    # New customer with no prior history — no "prior undisputed transaction" evidence possible
    if tx.get('device_fingerprint') == 'fp_new_unseen':
        impossible_reasons.append("New customer with no prior transaction history")

    # Digital goods with no shipping address
    if tx.get('shipping_address_postcode') is None and tx.get('merchant_mcc') in ['5815', '7997']:
        impossible_reasons.append("Digital goods merchant with no shipping address on file")

    # Billing/shipping address mismatch for goods — cardholder may not have authorized delivery
    billing = tx.get('billing_address_postcode')
    shipping = tx.get('shipping_address_postcode')
    if billing and shipping and billing != shipping:
        impossible_reasons.append(
            f"Shipping address ({shipping}) does not match billing address ({billing}). "
            f"Cardholder may not have authorized delivery to this address."
        )

    # For goods/services not received codes: if cardholder explicitly denies the address, 
    # and AVS failed, this is a strong fraud indicator
    case_type = _get_case_type(case)
    reason_code = case.get('reason_code', '')
    if reason_code in ('13.1', '4855', '4853') and tx.get('avs_result') == 'N' and billing != shipping:
        impossible_reasons.append(
            "AVS failed AND shipping address differs from billing — "
            "strong indicator of unauthorized delivery address"
        )

    return impossible_reasons


def apply_logic(rule, satisfied_count, case=None):
    """
    Apply the reason code logic to determine if requirements are met.

    Structural impossibilities are checked FIRST and always result in
    accept_liability, regardless of what the LLM claims about evidence.
    This prevents LLM overconfidence on cases with fundamental fraud indicators.

    Args:
        rule: The reason code rule dict
        satisfied_count: Number of satisfied requirements (excluding not_applicable)
        case: Optional case data for impossibility detection and requirement filtering

    Returns: (recommendation, justification)
    """
    logic = rule.get("logic", "ALL")
    min_required = rule.get("min_required", 0)

    # Get applicable requirements count for this case type
    if case:
        applicable_reqs = _get_applicable_requirements(rule, case)
        total_reqs = len(applicable_reqs)
    else:
        total_reqs = len(rule.get("requirements", []))

    if logic == "NOT_REPRESENTABLE":
        return "accept_liability", f"This reason code ({rule['label']}) generally cannot be represented per scheme rules. The merchant will bear the loss."

    # =====================================================================
    # STEP 1: Check structural impossibilities FIRST — these override
    # any LLM assessment because they indicate the evidence is fundamentally
    # compromised (e.g., AVS mismatch means the "delivery address" 
    # requirement cannot be trusted even if a tracking number exists).
    # =====================================================================
    impossible_reasons = _detect_impossibilities(case)

    if impossible_reasons:
        return "accept_liability", (
            f"Structural impossibilities detected that cannot be fixed with more evidence: "
            f"{'; '.join(impossible_reasons)}. "
            f"The merchant will bear the loss regardless of document evidence. "
            f"({satisfied_count}/{total_reqs} requirements appeared satisfied by LLM assessment, "
            f"but structural gaps make the case indefensible.)"
        )
    # =====================================================================

    # STEP 2: Apply standard logic only if no impossibilities exist
    if logic == "ALL":
        if satisfied_count >= total_reqs:
            return "represent", f"All {total_reqs} applicable requirements satisfied. We have a defensible case."
        else:
            return "request_more_evidence", f"{satisfied_count}/{total_reqs} applicable requirements satisfied. Missing: {total_reqs - satisfied_count} item(s). Request specific evidence from merchant."

    if logic == "ANY":
        if satisfied_count >= min_required:
            return "represent", f"{satisfied_count} of {total_reqs} possible applicable requirements satisfied (minimum {min_required} needed). We have a defensible case."
        else:
            return "request_more_evidence", f"Only {satisfied_count}/{min_required} minimum applicable requirements met. Need {min_required - satisfied_count} more. Request specific evidence from merchant."

    if logic == "EITHER":
        if satisfied_count >= 1:
            return "represent", f"At least one applicable requirement branch satisfied. We have a defensible case."
        else:
            return "request_more_evidence", f"No evidence for either applicable requirement branch. Request qualifying evidence from merchant."

    return "request_more_evidence", "Unable to determine — manual review required."