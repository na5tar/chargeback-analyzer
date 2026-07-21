import pdfplumber
import os
from pdf2image import convert_from_path
import base64
import io
from PIL import Image


def score_page_relevance(page_text, case):
    """Score a page from 0-100 based on relevance to case."""
    score = 0
    text_lower = page_text.lower()
    
    # Case-specific keywords (must match these to be highly relevant)
    case_id = case.get('case_id', '').lower()
    txn_id = case.get('transaction', {}).get('transaction_id', '').lower()
    
    # Check if page contains case-specific identifiers
    has_case_id = case_id in text_lower
    has_txn_id = txn_id in text_lower
    
    # High-weight keywords (transaction-specific)
    high_weight = [
        case_id,
        txn_id,
        case.get('transaction', {}).get('merchant_name', '').lower(),
        case.get('transaction', {}).get('billing_address_postcode', '').lower(),
    ]
    
    # Add shipping postcode if exists
    shipping = case.get('transaction', {}).get('shipping_address_postcode')
    if shipping:
        high_weight.append(shipping.lower())
    
    # Medium-weight keywords (scheme-specific)
    medium_weight = ['delivered', 'tracking', 'signature', 'pod', 'consignment', 
                     'confirmation', 'proof', 'delivery', 'service rendered']
    
    # Check high-weight matches
    for kw in high_weight:
        if kw and kw in text_lower:
            score += 25
    
    # Check medium-weight matches
    for kw in medium_weight:
        if kw in text_lower:
            score += 10
    
    # PENALTY: If page doesn't contain case-specific ID, cap score at 40
    # This prevents generic cover pages from being auto-sent
    if not has_case_id and not has_txn_id:
        score = min(score, 40)
    
    # Cap at 100
    return min(score, 100)


def extract_page_text(pdf_path, page_num):
    """Extract text from a specific page using pdfplumber."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if page_num < len(pdf.pages):
                return pdf.pages[page_num].extract_text() or ""
    except Exception as e:
        print(f"Warning: pdfplumber failed for {pdf_path} page {page_num}: {e}")
    
    return None


def select_pages_for_vision(pdf_path, case, max_pages=5):
    """
    Select which pages to send to Kimi for vision analysis.
    
    Returns: (selected_pages_info, routing_tier, analyst_note)
    """
    
    # Try pdfplumber first (fast, no OCR)
    pages = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                score = score_page_relevance(text, case)
                pages.append({
                    'page_num': i + 1,
                    'score': score,
                    'text_preview': text[:300].replace('\n', ' ')
                })
    except Exception as e:
        print(f"pdfplumber failed for {pdf_path}: {e}")
        print("Falling back to OCR...")
        return None, "OCR_FALLBACK", "pdfplumber failed, using OCR fallback"
    
    # Sort by relevance score descending
    pages.sort(key=lambda x: x['score'], reverse=True)
    
    # TIER 1: 1-2 highly relevant pages (score >= 60)
    high_relevance = [p for p in pages if p['score'] >= 60]
    
    if len(high_relevance) == 1:
        selected = high_relevance
        tier = "TIER_1"
        note = f"Auto-sent 1 highly relevant page (score >= 60) to Kimi."
        return selected, tier, note
    
    if len(high_relevance) >= 2:
        selected = high_relevance[:2]  # Cap at 2
        tier = "TIER_1"
        note = f"Auto-sent {len(selected)} highly relevant pages (score >= 60) to Kimi."
        return selected, tier, note
    
    # TIER 2: 1-5 relevant pages (score >= 25)
    medium_relevance = [p for p in pages if p['score'] >= 25]
    
    if 1 <= len(medium_relevance) <= 5:
        selected = medium_relevance
        tier = "TIER_2"
        note = f"Auto-sent {len(selected)} relevant pages (score >= 25) to Kimi."
        return selected, tier, note
    
    # TIER 3: Too many relevant pages or no relevant pages — analyst decision required
    top_pages = pages[:max_pages]
    tier = "TIER_3"
    
    if len(medium_relevance) > 5:
        note = f"Multiple pages ({len(medium_relevance)}) contain relevant keywords. Analyst must select which pages to send to Kimi."
    else:
        note = f"No highly relevant pages found. Showing top {len(top_pages)} pages for analyst review."
    
    return top_pages, tier, note


def convert_selected_pages_to_images(pdf_path, selected_pages):
    """Convert only selected pages to images for vision API."""
    page_numbers = [p['page_num'] for p in selected_pages]
    
    # pdf2image uses 0-based indexing
    images = convert_from_path(pdf_path, dpi=200, first_page=min(page_numbers), last_page=max(page_numbers))
    
    # Map back to original page numbers
    result = []
    for i, img in enumerate(images):
        actual_page = min(page_numbers) + i
        if actual_page in page_numbers:
            result.append({
                'page': actual_page,
                'image': img
            })
    
    return result


def prepare_document_images_tiered(case, doc_folder="documents"):
    """
    Prepare document images using tiered page selection.
    Returns list of image dicts ready for Kimi API.
    """
    images = []
    
    for doc_name in case.get('merchant_evidence_documents', []):
        doc_path = os.path.join(doc_folder, doc_name)
        
        if not os.path.exists(doc_path):
            print(f"Warning: {doc_path} not found")
            continue
        
        # Skip non-PDF files (images go straight through)
        if not doc_name.lower().endswith('.pdf'):
            with open(doc_path, "rb") as img_file:
                img_base64 = base64.b64encode(img_file.read()).decode('utf-8')
            
            images.append({
                'filename': doc_name,
                'page': 1,
                'base64': img_base64,
                'tier': 'IMAGE_DIRECT',
                'score': 100
            })
            continue
        
        # PDF: Use tiered selection
        selected, tier, note = select_pages_for_vision(doc_path, case)
        
        print(f"\n{doc_name}: {note}")
        
        # Handle OCR fallback
        if tier == "OCR_FALLBACK":
            all_pages = convert_from_path(doc_path, dpi=200)
            for i, img in enumerate(all_pages):
                buffered = io.BytesIO()
                img.save(buffered, format="PNG")
                img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                images.append({
                    'filename': doc_name,
                    'page': i + 1,
                    'base64': img_base64,
                    'tier': 'OCR_FALLBACK',
                    'score': 0
                })
            continue
        
        # Convert selected pages to images
        page_images = convert_selected_pages_to_images(doc_path, selected)
        
        for item in page_images:
            buffered = io.BytesIO()
            item['image'].save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            # Find the score for this page
            page_info = next((p for p in selected if p['page_num'] == item['page']), None)
            
            images.append({
                'filename': doc_name,
                'page': item['page'],
                'base64': img_base64,
                'tier': tier,
                'score': page_info['score'] if page_info else 0,
                'text_preview': page_info['text_preview'] if page_info else ''
            })
    
    return images


if __name__ == "__main__":
    # Test with CB-2025-0007
    import json
    
    with open('cases.json', 'r') as f:
        cases = json.load(f)
    
    case = cases[6]  # CB-2025-0007
    print(f"Testing page selection for {case['case_id']}...")
    print(f"Documents: {case['merchant_evidence_documents']}")
    
    images = prepare_document_images_tiered(case)
    print(f"\nTotal images prepared: {len(images)}")
    for img in images:
        print(f"  - {img['filename']} page {img['page']} (tier: {img['tier']}, score: {img['score']})")