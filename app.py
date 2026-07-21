# app.py
"""
Chargeback Representment Analyzer — Analyst UI
Streamlit app with Checkout.com brand theming.
Run: streamlit run app.py
"""
import streamlit as st
import json
import os
import base64
import time
from datetime import datetime
from dotenv import load_dotenv

from analyzer import analyze_case
from page_selector import prepare_document_images_tiered
from telemetry import (
    record_analyst_decision,
    get_reason_code_stats,
    get_all_telemetry_summary,
    get_override_categories,
    get_provider_performance
)
from llm_client import select_provider
from reason_code_rules import get_rule

load_dotenv()

st.set_page_config(
    page_title="Chargeback Analyzer | Checkout.com",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Checkout.com theming
st.markdown("""
<style>
    .stApp {
        background-color: #0A2540 !important;
    }
    [data-testid="stSidebar"] {
        background-color: #0D1B2A !important;
        border-right: 1px solid rgba(255,255,255,0.06);
    }
    .stButton > button {
        background-color: #0066FF !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }
    .stButton > button:hover {
        background-color: #0052CC !important;
    }
    .stButton > button:disabled {
        background-color: #1a3a5c !important;
        color: rgba(255,255,255,0.3) !important;
        cursor: not-allowed !important;
    }
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stSelectbox > div > div > div {
        background-color: rgba(255,255,255,0.05) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        color: white !important;
        border-radius: 8px !important;
    }
    label {
        color: rgba(255,255,255,0.4) !important;
        font-size: 11px !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    h1, h2, h3 {
        color: white !important;
    }
    div[data-testid="stMetric"] {
        background: rgba(255,255,255,0.03);
        border-radius: 8px;
        padding: 10px;
    }
    div[data-testid="stMetric"] label {
        color: rgba(255,255,255,0.4) !important;
        font-size: 10px !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: white !important;
        font-size: 22px !important;
        font-weight: 700 !important;
    }
    .streamlit-expanderHeader {
        background: rgba(255,255,255,0.03) !important;
        border-radius: 8px !important;
        color: white !important;
    }
    .streamlit-expanderContent {
        background: rgba(255,255,255,0.02) !important;
        border-radius: 0 0 8px 8px !important;
    }
    .ai-recommendation-banner {
        background: linear-gradient(135deg, #0066FF 0%, #0052CC 100%);
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 20px;
        color: white;
    }
    .case-resolved-banner {
        background: linear-gradient(135deg, #10B981 0%, #059669 100%);
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 20px;
        color: white;
    }
    .override-warning-box {
        background: rgba(239, 68, 68, 0.1);
        border: 1px solid rgba(239, 68, 68, 0.3);
        border-radius: 12px;
        padding: 20px;
        margin: 16px 0;
    }
    .interstitial-box {
        background: rgba(245, 158, 11, 0.1);
        border: 1px solid rgba(245, 158, 11, 0.3);
        border-radius: 12px;
        padding: 20px;
        margin: 16px 0;
    }
    .rag-high { color: #10B981; font-weight: 700; }
    .rag-medium { color: #F59E0B; font-weight: 700; }
    .rag-low { color: #EF4444; font-weight: 700; }
    .doc-list-item {
        padding: 8px 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 6px;
        margin: 4px 0;
    }
    .batch-queue-item {
        padding: 6px 10px;
        background: rgba(0, 102, 255, 0.1);
        border-radius: 6px;
        margin: 3px 0;
        font-size: 12px;
    }
    .batch-progress-bar {
        background: rgba(255,255,255,0.1);
        border-radius: 4px;
        height: 8px;
        overflow: hidden;
        margin: 8px 0;
    }
    .batch-progress-fill {
        background: linear-gradient(90deg, #0066FF, #00D4AA);
        height: 100%;
        border-radius: 4px;
        transition: width 0.3s ease;
    }
    .status-pill {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .status-pending { background: rgba(156, 163, 175, 0.15); color: #9CA3AF; }
    .status-progress { background: rgba(245, 158, 11, 0.15); color: #F59E0B; }
    .status-resolved { background: rgba(16, 185, 129, 0.15); color: #10B981; }
    .bullet-list {
        margin: 8px 0;
        padding-left: 16px;
    }
    .bullet-list li {
        margin: 4px 0;
        color: rgba(255,255,255,0.8);
    }
</style>
""", unsafe_allow_html=True)


# ==================== LOAD LOGO ====================

def get_logo_base64():
    logo_paths = [
        'checkout-logo.jpeg',
        'checkout-logo.jpg',
        'checkout-logo.png',
        os.path.join('assets', 'checkout-logo.jpeg'),
        os.path.join('assets', 'checkout-logo.jpg'),
    ]
    for path in logo_paths:
        if os.path.exists(path):
            with open(path, 'rb') as f:
                return base64.b64encode(f.read()).decode('utf-8')
    return None


LOGO_BASE64 = get_logo_base64()


# ==================== LOAD DATA ====================

@st.cache_data
def load_cases():
    with open('cases.json', 'r') as f:
        return json.load(f)


cases = load_cases()

# ==================== SESSION STATE INIT ====================

def init_session_state():
    defaults = {
        'current_case_idx': 0,
        'analysis_results': {},
        'images_prepared': {},
        'analyst_decisions': {},
        'admin_mode': False,
        'admin_clicks': 0,
        'forced_provider': None,
        'analyst_id': 'analyst_1',
        'show_telemetry': False,
        'analysis_in_progress': set(),
        'override_form_case_id': None,
        'override_form_choice': None,
        'interstitial_case_id': None,
        'interstitial_category': None,
        'interstitial_detail': None,
        'filter_scheme': 'All',
        'filter_reason_code': 'All',
        'filter_merchant_search': '',
        'filter_sort_by': 'Value (High to Low)',
        'filter_status': 'All',
        'batch_queue': set(),
        'batch_running': False,
        'batch_current': None,
        'batch_completed': 0,
        'batch_total': 0,
        'batch_retry_msg': None,
        'admin_override_case_id': None,
        'admin_override_choice': None,
        'admin_password_verified': False,
        'admin_login_requested': False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


init_session_state()


def get_case_status(case_id):
    if case_id in st.session_state.analyst_decisions:
        return "resolved"
    if case_id in st.session_state.analysis_in_progress:
        return "in_progress"
    if case_id in st.session_state.analysis_results:
        return "in_progress"
    return "pending"


def status_emoji(status):
    return {"pending": "⚪", "in_progress": "🟡", "resolved": "🟢"}.get(status, "⚪")


def status_pill(status):
    return f'<span class="status-pill status-{status}">{status.replace("_", " ").upper()}</span>'


def record_analyst_choice(case, result, choice, category, detail, provider):
    """Record analyst decision to telemetry and session state."""
    record_analyst_decision(
        case_data=case,
        analysis_result=result,
        analyst_choice=choice,
        override_category=category,
        override_detail=detail,
        analyst_id=st.session_state.get('analyst_id', 'anonymous')
    )

    st.session_state.analyst_decisions[case['case_id']] = {
        'choice': choice,
        'override_category': category,
        'override_detail': detail,
        'timestamp': datetime.now().isoformat(),
        'provider_used': provider
    }


def apply_filters(case_list):
    """Apply sidebar filters to case list."""
    filtered = case_list

    if st.session_state.filter_status != 'All':
        filtered = [c for c in filtered if get_case_status(c['case_id']) == st.session_state.filter_status]

    if st.session_state.filter_scheme != 'All':
        filtered = [c for c in filtered if c['scheme'].upper() == st.session_state.filter_scheme.upper()]

    if st.session_state.filter_reason_code != 'All':
        filtered = [c for c in filtered if c['reason_code'] == st.session_state.filter_reason_code]

    if st.session_state.filter_merchant_search.strip():
        search = st.session_state.filter_merchant_search.lower()
        filtered = [c for c in filtered if search in c['transaction']['merchant_name'].lower()]

    if st.session_state.filter_sort_by == 'Value (High to Low)':
        filtered = sorted(filtered, key=lambda c: float(c['chargeback_amount']['value']), reverse=True)
    elif st.session_state.filter_sort_by == 'Value (Low to High)':
        filtered = sorted(filtered, key=lambda c: float(c['chargeback_amount']['value']))
    elif st.session_state.filter_sort_by == 'Case ID':
        filtered = sorted(filtered, key=lambda c: c['case_id'])
    elif st.session_state.filter_sort_by == 'Merchant Name':
        filtered = sorted(filtered, key=lambda c: c['transaction']['merchant_name'].lower())

    return filtered


def run_next_batch_item():
    """Process one item from the batch queue with rate limiting and retry."""
    queue = st.session_state.batch_queue

    if not queue or not st.session_state.batch_running:
        st.session_state.batch_running = False
        st.session_state.batch_current = None
        return

    next_case_id = None
    for cid in queue:
        if cid not in st.session_state.analysis_results and cid not in st.session_state.analysis_in_progress:
            next_case_id = cid
            break

    if not next_case_id:
        st.session_state.batch_running = False
        st.session_state.batch_current = None
        st.session_state.batch_queue = set()
        return

    case = next((c for c in cases if c['case_id'] == next_case_id), None)
    if not case:
        st.session_state.batch_queue.discard(next_case_id)
        return

    st.session_state.analysis_in_progress.add(next_case_id)
    st.session_state.batch_current = next_case_id

    # Rate limit: Kimi allows max 3 concurrent requests; OpenAI has higher limits
    provider = st.session_state.get('forced_provider')
    if provider == "kimi":
        time.sleep(2)
    max_retries = 3
    retry_count = 0
    success = False

    while retry_count < max_retries and not success:
        try:
            images = prepare_document_images_tiered(case)
            st.session_state.images_prepared[next_case_id] = images

            analysis_result, _ = analyze_case(case, images, provider=provider)
            st.session_state.analysis_results[next_case_id] = analysis_result
            success = True
        except Exception as e:
            error_str = str(e)
            is_rate_limit = '429' in error_str or 'rate_limit' in error_str.lower() or 'concurrency' in error_str.lower()

            if is_rate_limit and retry_count < max_retries - 1:
                retry_count += 1
                wait_time = retry_count * 3  # 3s, 6s, 9s backoff
                st.session_state.batch_retry_msg = f"Rate limited (429). Retrying {retry_count}/{max_retries} in {wait_time}s..."
                time.sleep(wait_time)
            else:
                st.session_state.analysis_results[next_case_id] = {
                    "error": error_str,
                    "recommendation": "manual_review",
                    "confidence_score": 0,
                    "provider_used": provider or "unknown",
                    "retry_count": retry_count
                }
                success = True  # Don't retry non-rate-limit errors

    st.session_state.analysis_in_progress.discard(next_case_id)
    st.session_state.batch_queue.discard(next_case_id)
    st.session_state.batch_completed += 1
    st.session_state.batch_retry_msg = None


def get_rag_level(confidence):
    """Convert numeric confidence to RAG level."""
    if confidence >= 80:
        return "high", "#10B981", "No human checks required"
    elif confidence >= 50:
        return "medium", "#F59E0B", "Some intervention/check required"
    else:
        return "low", "#EF4444", "AI unable to assess — manual review required"


# ==================== SIDEBAR ====================

with st.sidebar:
    if LOGO_BASE64:
        st.markdown(
            f'<img src="data:image/jpeg;base64,{LOGO_BASE64}" style="width: 32px; height: 32px; border-radius: 8px; margin-bottom: 8px;" />',
            unsafe_allow_html=True
        )
    st.markdown("**Chargeback Analyzer**")
    st.caption("Disputes Team")
    st.caption(f"👤 Signed in as: `{st.session_state.analyst_id}`")

    pending_count = sum(1 for c in cases if get_case_status(c['case_id']) == 'pending')
    in_progress_count = sum(1 for c in cases if get_case_status(c['case_id']) == 'in_progress')
    resolved_count = sum(1 for c in cases if get_case_status(c['case_id']) == 'resolved')

    st.divider()

    cols = st.columns(3)
    with cols[0]:
        st.metric("Pending", pending_count)
    with cols[1]:
        st.metric("In Progress", in_progress_count)
    with cols[2]:
        st.metric("Resolved", resolved_count)

    st.divider()

    # ==================== BATCH QUEUE ====================
    st.markdown("### 🚀 Batch Analysis")

    batch_queue = st.session_state.batch_queue
    batch_running = st.session_state.batch_running

    if batch_running:
        total = st.session_state.batch_total
        completed = st.session_state.batch_completed
        current = st.session_state.batch_current
        pct = (completed / total * 100) if total > 0 else 0

        st.markdown(f"**Running: {completed}/{total}**")
        if current:
            current_case = next((c for c in cases if c['case_id'] == current), None)
            if current_case:
                st.caption(f"Analyzing: {current_case['transaction']['merchant_name']}")

        # Show retry message if rate limited
        if st.session_state.get('batch_retry_msg'):
            st.warning(st.session_state.batch_retry_msg)

        st.markdown(f"""
        <div class="batch-progress-bar">
            <div class="batch-progress-fill" style="width: {pct}%"></div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("⏹ Stop Batch", use_container_width=True):
            st.session_state.batch_running = False
            st.session_state.batch_queue = set()
            st.session_state.batch_current = None
            st.session_state.batch_retry_msg = None
            st.rerun()

    elif batch_queue:
        st.markdown(f"**{len(batch_queue)} cases queued**")
        for cid in list(batch_queue)[:5]:
            case_item = next((c for c in cases if c['case_id'] == cid), None)
            if case_item:
                st.markdown(f'<div class="batch-queue-item">{case_item["transaction"]["merchant_name"]} | {case_item["case_id"]}</div>', unsafe_allow_html=True)

        if len(batch_queue) > 5:
            st.caption(f"...and {len(batch_queue) - 5} more")

        run_col, clear_col = st.columns(2)
        with run_col:
            if st.button("▶ Run Batch", use_container_width=True, type="primary"):
                st.session_state.batch_running = True
                st.session_state.batch_total = len(batch_queue)
                st.session_state.batch_completed = 0
                st.rerun()
        with clear_col:
            if st.button("🗑 Clear", use_container_width=True):
                st.session_state.batch_queue = set()
                st.rerun()

    else:
        st.caption("Queue cases below for batch analysis")

        pending_cases = [c for c in cases if get_case_status(c['case_id']) == 'pending']
        if pending_cases and st.button("➕ Select All Pending", use_container_width=True):
            for c in pending_cases:
                st.session_state.batch_queue.add(c['case_id'])
            st.rerun()

    st.divider()

    # ==================== FILTERS ====================
    st.markdown("### Filters")

    with st.container():
        status_options = ['All', 'pending', 'in_progress', 'resolved']
        status_labels = ['All', 'Pending', 'In Progress', 'Resolved']
        st.session_state.filter_status = st.selectbox(
            "Status",
            status_options,
            index=status_options.index(st.session_state.filter_status) if st.session_state.filter_status in status_options else 0,
            format_func=lambda x: status_labels[status_options.index(x)],
            key="filter_status_widget"
        )

        schemes = ['All'] + sorted(list(set(c['scheme'].upper() for c in cases)))
        st.session_state.filter_scheme = st.selectbox(
            "Scheme",
            schemes,
            index=schemes.index(st.session_state.filter_scheme) if st.session_state.filter_scheme in schemes else 0,
            key="filter_scheme_widget"
        )

        reason_options = {'All': 'All'}
        for c in cases:
            rc = c['reason_code']
            label = c['reason_code_label']
            key = f"{rc} | {label}"
            reason_options[rc] = key

        reason_keys = list(reason_options.keys())
        reason_labels = list(reason_options.values())

        current_rc = st.session_state.filter_reason_code
        try:
            current_idx = reason_keys.index(current_rc)
        except ValueError:
            current_idx = 0

        selected_label = st.selectbox(
            "Reason Code",
            reason_labels,
            index=current_idx,
            key="filter_reason_widget"
        )

        selected_idx = reason_labels.index(selected_label)
        st.session_state.filter_reason_code = reason_keys[selected_idx]

        st.session_state.filter_merchant_search = st.text_input(
            "Search Merchant",
            value=st.session_state.filter_merchant_search,
            placeholder="Type merchant name...",
            key="filter_merchant_widget"
        )

        sort_options = ['Value (High to Low)', 'Value (Low to High)', 'Case ID', 'Merchant Name']
        st.session_state.filter_sort_by = st.selectbox(
            "Sort By",
            sort_options,
            index=sort_options.index(st.session_state.filter_sort_by) if st.session_state.filter_sort_by in sort_options else 0,
            key="filter_sort_widget"
        )

        if st.button("🔄 Clear Filters", use_container_width=True):
            st.session_state.filter_status = 'All'
            st.session_state.filter_scheme = 'All'
            st.session_state.filter_reason_code = 'All'
            st.session_state.filter_merchant_search = ''
            st.session_state.filter_sort_by = 'Value (High to Low)'
            st.rerun()

    st.divider()
    st.markdown("### Case Queue")

    filtered_cases = apply_filters(cases)
    filtered_cases = sorted(filtered_cases, key=lambda c: c['case_id'])

    if not filtered_cases:
        st.info("No cases match your filters.")

    for i, case in enumerate(filtered_cases):
        case_id_item = case['case_id']
        status = get_case_status(case_id_item)
        emoji = status_emoji(status)
        is_resolved = status == "resolved"
        is_active = case_id_item == cases[st.session_state.current_case_idx]['case_id']
        is_queued = case_id_item in st.session_state.batch_queue
        is_running = case_id_item == st.session_state.batch_current
        original_idx = next((idx for idx, c in enumerate(cases) if c['case_id'] == case_id_item), 0)

        with st.container():
            st.markdown(f"**{emoji} {case['case_id']}**")
            st.markdown(f"<span style='color:rgba(255,255,255,0.8)'>{case['transaction']['merchant_name']}</span>", unsafe_allow_html=True)
            st.caption(f"{case['scheme'].upper()} | {case['reason_code']} — {case['reason_code_label']}")
            st.caption(f"Amount: {case['chargeback_amount']['value']} {case['chargeback_amount']['currency']} | Txn: {case['transaction']['transaction_id']}")

            btn_cols = st.columns([2, 2, 3])

            with btn_cols[0]:
                btn_label = "View" if is_resolved else "Open"
                if st.button(btn_label, key=f"select_{original_idx}", use_container_width=True, 
                            disabled=is_resolved and not st.session_state.admin_mode,
                            type="primary" if is_active else "secondary"):
                    st.session_state.current_case_idx = original_idx
                    st.rerun()

            with btn_cols[1]:
                if status == 'pending' and not is_queued:
                    if st.button("➕ Queue", key=f"queue_{original_idx}", use_container_width=True):
                        st.session_state.batch_queue.add(case_id_item)
                        st.rerun()
                elif is_queued:
                    if st.button("✓ Queued", key=f"queued_{original_idx}", use_container_width=True, disabled=True):
                        pass
                elif is_running:
                    if st.button("⏳ Running...", key=f"running_{original_idx}", use_container_width=True, disabled=True):
                        pass

            with btn_cols[2]:
                if is_queued and not batch_running:
                    if st.button("✕ Remove", key=f"unqueue_{original_idx}", use_container_width=True):
                        st.session_state.batch_queue.discard(case_id_item)
                        st.rerun()

        if i < len(filtered_cases) - 1:
            st.divider()


# ==================== MAIN CONTENT ====================

case = cases[st.session_state.current_case_idx]
case_id = case['case_id']
result = st.session_state.analysis_results.get(case_id)

# Normalize requirement_numbers to int for consistent comparison
if result and not result.get('error') and result.get('evidence_assessment'):
    for item in result['evidence_assessment']:
        if 'requirement_number' in item:
            try:
                item['requirement_number'] = int(item['requirement_number'])
            except (ValueError, TypeError):
                item['requirement_number'] = 0
is_resolved = case_id in st.session_state.analyst_decisions
is_in_progress = case_id in st.session_state.analysis_in_progress

# If batch is running, process next item
if st.session_state.batch_running:
    run_next_batch_item()
    if st.session_state.batch_running:
        st.rerun()

# Settings button (top right)
settings_col1, settings_col2 = st.columns([6, 1])
with settings_col2:
    if st.button("⚙️", key="admin_toggle", help="Admin access"):
        st.session_state.admin_clicks += 1
        if st.session_state.admin_clicks >= 3:
            st.session_state.admin_login_requested = True
            st.session_state.admin_clicks = 0
        st.rerun()

# Admin password gate
if st.session_state.get('admin_login_requested') and not st.session_state.get('admin_password_verified'):
    with st.container():
        st.markdown("---")
        st.markdown("### 🔒 Admin Access")
        st.warning("Enter admin password to access controls. In production this is account-bound with whitelisting.")
        pwd_col1, pwd_col2 = st.columns([3, 1])
        with pwd_col1:
            pwd = st.text_input(
                "Password",
                type="password",
                key="admin_pwd_input_widget",
                label_visibility="collapsed",
                placeholder="Enter admin password..."
            )
        with pwd_col2:
            if st.button("Unlock", use_container_width=True, type="primary"):
                if pwd == "admin123":
                    st.session_state.admin_password_verified = True
                    st.session_state.admin_mode = True
                    st.session_state.admin_login_requested = False
                    st.session_state.analyst_id = "admin"
                    st.success("✅ Admin mode activated")
                    st.rerun()
                else:
                    st.error("❌ Incorrect password")
                    st.rerun()
        if st.button("Cancel", use_container_width=True):
            st.session_state.admin_login_requested = False
            st.session_state.admin_password_verified = False
            st.rerun()
        st.markdown("---")

# Logout button when already in admin mode
if st.session_state.get('admin_password_verified'):
    logout_col1, logout_col2 = st.columns([6, 1])
    with logout_col2:
        if st.button("🔒 Lock", key="admin_logout", help="Exit admin mode"):
            st.session_state.admin_mode = False
            st.session_state.admin_password_verified = False
            st.session_state.admin_login_requested = False
            st.session_state.analyst_id = "analyst_1"
            st.rerun()

# Admin controls
if st.session_state.admin_mode:
    with st.expander("🔧 Admin Controls", expanded=True):
        admin_provider = st.selectbox(
            "Force Provider",
            ["auto", "kimi", "openai", "claude"],
            index=0,
            key="admin_provider"
        )
        st.session_state.forced_provider = None if admin_provider == "auto" else admin_provider

        if st.button("📊 Toggle Telemetry Dashboard"):
            st.session_state.show_telemetry = not st.session_state.show_telemetry
            st.rerun()

        if st.button("🔄 Reset All Decisions"):
            st.session_state.analyst_decisions = {}
            st.session_state.analysis_results = {}
            st.session_state.analysis_in_progress = set()
            st.session_state.batch_queue = set()
            st.session_state.batch_running = False
            st.rerun()

# Header with status pill
status = get_case_status(case_id)
with st.container():
    col1, col2 = st.columns([4, 1])
    with col1:
        st.markdown(f"## {case['case_id']}")
        st.markdown(f"**{case['scheme'].upper()} | {case['reason_code']}** — {case['reason_code_label']}")
        st.markdown(f"<span style='color:rgba(255,255,255,0.7); font-size: 16px;'>{case['transaction']['merchant_name']}</span>", unsafe_allow_html=True)
        st.markdown(f"<span style='color:rgba(255,255,255,0.5); font-size: 13px;'>Transaction Amount: <b>{case['chargeback_amount']['value']} {case['chargeback_amount']['currency']}</b> | Transaction ID: <b>{case['transaction']['transaction_id']}</b></span>", unsafe_allow_html=True)
    with col2:
        st.markdown(status_pill(status), unsafe_allow_html=True)

# Issuer Narrative
with st.expander("📄 Issuer Narrative", expanded=True):
    st.info(case['issuer_narrative'])

# Transaction metadata
with st.expander("💳 Transaction Details"):
    meta_cols = st.columns(5)
    meta_data = [
        ("AVS", case['transaction']['avs_result'] or 'N/A'),
        ("CVV", case['transaction']['cvv_result'] or 'N/A'),
        ("3DS", case['transaction']['three_ds_status'] or 'N/A'),
        ("Device", case['transaction']['device_fingerprint'] or 'N/A'),
        ("IP", case['transaction']['ip_address'] or 'N/A')
    ]
    for col, (label, value) in zip(meta_cols, meta_data):
        with col:
            st.markdown(f"**{label}**")
            st.markdown(f"{value}")


# ==================== EVIDENCE DOCUMENTS (CLICKABLE) ====================
with st.expander("📁 Evidence Documents"):
    docs = case.get('merchant_evidence_documents', [])
    doc_folder = "documents"
    if docs:
        st.caption("Click to download documents for cross-checking:")
        for doc in docs:
            doc_path = os.path.join(doc_folder, doc)
            if os.path.exists(doc_path):
                with open(doc_path, "rb") as f:
                    doc_bytes = f.read()
                st.download_button(
                    label=f"📄 {doc}",
                    data=doc_bytes,
                    file_name=doc,
                    mime="application/pdf",
                    use_container_width=True,
                    key=f"doc_download_{case_id}_{doc}"
                )
            else:
                st.markdown(f'<div class="doc-list-item">📄 {doc} <span style="color:rgba(255,255,255,0.3)">(file not found)</span></div>', unsafe_allow_html=True)
    else:
        st.info("No evidence documents attached to this case.")


# ==================== EVIDENCE REQUIREMENTS ====================

rule = get_rule(case['reason_code'])

with st.expander("📋 Evidence Requirements", expanded=True):
    if rule and rule.get('requirements'):
        # ELI5: translate scheme logic into what the analyst needs to see
        logic_labels = {
            "ALL": "To recommend **represent**: ALL requirements below must be satisfied",
            "ANY": f"To recommend **represent**: at least **{rule.get('min_required', 1)}** requirements below must be satisfied",
            "EITHER": "To recommend **represent**: at least **ONE** of the options below must be satisfied",
            "NOT_REPRESENTABLE": "This case **cannot be represented** — recommend **accept_liability**"
        }
        logic_text = logic_labels.get(rule['logic'], rule['logic'])
        st.markdown(f"**{logic_text}** | Scheme: {rule['scheme'].upper()}")
        st.markdown("---")

        # Determine case type for applicability checking
        from reason_code_rules import _get_case_type
        case_type = _get_case_type(case)

        for i, req in enumerate(rule['requirements'], 1):
            req_status = None
            req_doc = None
            req_explanation = None

            # Check if this requirement applies to the case type
            req_applies_to = req.get('applies_to', ['goods', 'services']) if isinstance(req, dict) else ['goods', 'services']
            is_applicable = case_type in req_applies_to

            if result and not result.get('error'):
                for item in result.get('evidence_assessment', []):
                    if int(item.get('requirement_number', 0)) == i:
                        req_status = item.get('status', 'missing')
                        req_doc = item.get('document_reference', 'N/A')
                        req_explanation = item.get('explanation', '')
                        break

            # Requirement text FIRST (always visible)
            req_display = req.get("text", req) if isinstance(req, dict) else req
            st.markdown(f"**Req {i}:** {req_display}")

            if not result or result.get('error'):
                # No analysis run yet — always show pending
                st.markdown(f"⬜ *Pending analysis — AI will evaluate this requirement against submitted documents*")
            elif not is_applicable:
                # Analysis done, but this requirement doesn't apply to this case type
                st.markdown(f'➖ Status: `NOT_APPLICABLE`')
                st.caption(f'This requirement applies to: {", ".join(req_applies_to)}. This case is classified as {case_type}.')
            elif req_status:
                emoji_map = {'satisfied': '✅', 'partial': '⚠️', 'missing': '❌', 'not_applicable': '➖'}
                emoji = emoji_map.get(req_status, '❓')
                st.markdown(f"{emoji} Status: `{req_status.upper()}`")
                if req_doc and req_doc != 'N/A':
                    st.caption(f"📄 Found in: {req_doc}")
                # Show explanation for backfilled (LLM-skipped) requirements
                if req_status == 'missing' and req_explanation and 'LLM FAILED' in str(req_explanation):
                    st.warning(f"⚠️ {req_explanation}")
            else:
                # Analysis done, but this requirement wasn't in the LLM output
                # Conservative: treat as MISSING — no evidence means no defense
                st.markdown(f"❌ Status: `MISSING`")
                st.caption("No evidence found for this requirement in submitted merchant documents. If the merchant can provide this evidence, the case may become representable.")

            st.divider()
    else:
        st.info("No specific evidence requirements for this reason code.")


# ==================== RUN ANALYSIS (SINGLE CASE) ====================

if not result and not is_resolved and not is_in_progress:
    if st.button("🔍 Run AI Analysis", use_container_width=True, type="primary"):
        st.session_state.analysis_in_progress.add(case_id)
        st.rerun()

if is_in_progress and not result and not st.session_state.batch_running:
    with st.spinner("Preparing documents and running analysis..."):
        images = prepare_document_images_tiered(case)
        st.session_state.images_prepared[case_id] = images

        provider = st.session_state.get('forced_provider')
        max_retries = 3
        retry_count = 0
        success = False
        last_error = None
        is_rate_limit = False

        try:
            while retry_count < max_retries and not success:
                try:
                    analysis_result, _ = analyze_case(case, images, provider=provider)
                    st.session_state.analysis_results[case_id] = analysis_result
                    success = True
                except Exception as e:
                    last_error = str(e)
                    is_rate_limit = '429' in last_error or 'rate_limit' in last_error.lower() or 'concurrency' in last_error.lower()

                    if is_rate_limit and retry_count < max_retries - 1:
                        retry_count += 1
                        wait_time = retry_count * 3
                        st.toast(f"Rate limited (429). Retrying {retry_count}/{max_retries} in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        st.session_state.analysis_results[case_id] = {
                            "error": last_error,
                            "recommendation": "manual_review",
                            "confidence_score": 0,
                            "provider_used": provider or "unknown",
                            "is_rate_limit": is_rate_limit,
                            "retry_count": retry_count
                        }
                        success = True
        finally:
            st.session_state.analysis_in_progress.discard(case_id)

    st.rerun()


# ==================== DISPLAY ANALYSIS RESULTS ====================

if result:
    if 'error' in result:
        is_rate_limit = result.get('is_rate_limit', False) or '429' in result['error'] or 'rate_limit' in result['error'].lower()

        if is_rate_limit:
            st.error(f"❌ **Rate Limit (429)** — {result['error']}")
            st.warning("Kimi allows max 3 concurrent requests. Please wait a moment and retry.")

            retry_col1, retry_col2 = st.columns(2)
            with retry_col1:
                if st.button("🔄 Retry Analysis", use_container_width=True, type="primary"):
                    # Clear error and re-run
                    if case_id in st.session_state.analysis_results:
                        del st.session_state.analysis_results[case_id]
                    st.session_state.analysis_in_progress.add(case_id)
                    st.rerun()
            with retry_col2:
                if st.button("⏭ Skip for Now", use_container_width=True):
                    st.info("Case skipped. You can retry later from the case queue.")
        else:
            st.error(f"❌ **Analysis Error** — {result['error']}")
            if result.get('raw_content') and result['raw_content'] != 'N/A':
                with st.expander("🔍 Raw LLM Response (for debugging)"):
                    st.code(result['raw_content'][:2000], language='json')
            st.info("The LLM returned a response that could not be parsed as structured JSON.")

    provider_used = result.get('provider_used', 'unknown')
    st.caption(f"Analyzed by **{provider_used.upper()}** | {result.get('analysis_mode', 'N/A')} mode | ~{result.get('llm_tokens_used', 'N/A')} tokens")

    rec = result.get('recommendation', 'manual_review')
    rec_label = rec.replace('_', ' ').title()

    # AI Recommendation + RAG on same line
    conf = result.get('confidence_score', 0)
    rag_level, rag_color, rag_desc = get_rag_level(conf)

    st.markdown(f"""
    <div class="ai-recommendation-banner">
        <div style="font-size: 12px; opacity: 0.7; margin-bottom: 4px;">AI RECOMMENDATION</div>
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div style="font-size: 24px; font-weight: 700;">{rec_label}</div>
            <div style="text-align: right;">
                <div style="font-size: 11px; opacity: 0.7; text-transform: uppercase; letter-spacing: 0.5px;">RAG Confidence</div>
                <div style="font-size: 20px; font-weight: 700; color: {rag_color};">{rag_level.upper()}</div>
                <div style="font-size: 11px; opacity: 0.8;">{rag_desc}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Representment Rationale (moved up, below recommendation)
    if result.get('representment_rationale') and result['representment_rationale'] != 'N/A':
        st.markdown("### Case Rationale")
        st.info(result['representment_rationale'])

    # Evidence Assessment & Flags (bullet points, concise)
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Evidence Assessment")
        evidence_items = result.get('evidence_assessment', [])
        if not evidence_items and 'error' not in result:
            st.info("No evidence assessment available.")

        for item in evidence_items:
            status = item.get('status', 'missing')
            status_emoji = {'satisfied': '✅', 'partial': '⚠️', 'missing': '❌', 'not_applicable': '➖'}.get(status, '❓')
            req_text = ""
            if rule and rule.get('requirements'):
                req_idx = item.get('requirement_number', 1) - 1
                if 0 <= req_idx < len(rule['requirements']):
                    req_item = rule['requirements'][req_idx]
                req_text_str = req_item.get('text', req_item) if isinstance(req_item, dict) else req_item
                req_text = f" — {req_text_str[:60]}..."

            with st.container():
                st.markdown(f"**{status_emoji} Req {item['requirement_number']}**{req_text}")
                st.caption(f"📄 {item.get('document_reference', 'N/A')}")
                # Bullet points instead of paragraphs
                explanation = item.get('explanation', 'No explanation')
                if explanation:
                    sentences = [s.strip() for s in explanation.split('.') if s.strip()]
                    if len(sentences) > 1:
                        bullet_html = "<ul class='bullet-list'>" + "".join([f"<li>{s}.</li>" for s in sentences[:3]]) + "</ul>"
                        st.markdown(bullet_html, unsafe_allow_html=True)
                    else:
                        st.markdown(f"{explanation}")
                if item.get('citation'):
                    st.markdown(f"> *{item['citation'][:120]}*")
                st.divider()

    with col2:
        st.markdown("### Systematic Flags")
        flags = result.get('systematic_flags', [])
        if not flags:
            st.info("No flags raised")

        for flag in flags:
            flag_type = flag.get('flag_type', 'MANUAL_REVIEW')
            description = flag.get('description', '')

            # Bullet points for flags
            if flag_type == 'BURIED_EVIDENCE':
                st.warning(f"🚩 **{flag_type}**")
            elif flag_type == 'CONFIDENT_BUT_IRRELEVANT':
                st.warning(f"⚠️ **{flag_type}**")
            elif flag_type == 'CONTRADICTORY':
                st.error(f"❌ **{flag_type}**")
            else:
                st.info(f"ℹ️ **{flag_type}**")

            if description:
                sentences = [s.strip() for s in description.split('.') if s.strip()]
                if len(sentences) > 1:
                    bullet_html = "<ul class='bullet-list'>" + "".join([f"<li>{s}.</li>" for s in sentences[:3]]) + "</ul>"
                    st.markdown(bullet_html, unsafe_allow_html=True)
                else:
                    st.markdown(f"{description}")

            if flag.get('location'):
                st.caption(f"📍 {flag['location']}")
            st.divider()

        if result.get('merchant_evidence_summary') and result['merchant_evidence_summary'] != 'N/A':
            st.markdown("### Merchant Evidence Summary")
            summary_text = result['merchant_evidence_summary']
            sentences = [s.strip() for s in summary_text.split('.') if s.strip()]
            if len(sentences) > 1:
                bullet_html = "<ul class='bullet-list'>" + "".join([f"<li>{s}.</li>" for s in sentences]) + "</ul>"
                st.markdown(bullet_html, unsafe_allow_html=True)
            else:
                st.info(summary_text)

        if result.get('gaps_analysis') and result['gaps_analysis'] != 'N/A':
            st.markdown("### Gaps Analysis")
            gaps_text = result['gaps_analysis']
            sentences = [s.strip() for s in gaps_text.split('.') if s.strip()]
            if len(sentences) > 1:
                bullet_html = "<ul class='bullet-list'>" + "".join([f"<li>{s}.</li>" for s in sentences]) + "</ul>"
                st.markdown(bullet_html, unsafe_allow_html=True)
            else:
                st.warning(gaps_text)


    # ==================== ANALYST DECISION SECTION (SCROLL DOWN) ====================
    if not is_resolved:
        st.divider()
        st.markdown("### Analyst Decision")

        all_choices = ['represent', 'accept_liability', 'request_more_evidence']
        ai_choice = rec if rec in all_choices else 'represent'

        in_override = st.session_state.override_form_case_id == case_id
        in_interstitial = st.session_state.interstitial_case_id == case_id
        categories = get_override_categories()

        if not in_override and not in_interstitial:
            override_col1, override_col2, override_col3 = st.columns(3)

            with override_col1:
                is_ai = ai_choice == 'represent'
                label = "✓ Agree — Represent" if is_ai else "Represent"
                if st.button(label, use_container_width=True, type="primary" if is_ai else "secondary"):
                    if is_ai:
                        record_analyst_choice(case, result, 'represent', "ANALYST_AGREEMENT", 
                                            "Analyst agreed with LLM recommendation", provider_used)
                        st.rerun()
                    else:
                        st.session_state.override_form_case_id = case_id
                        st.session_state.override_form_choice = 'represent'
                        st.rerun()

            with override_col2:
                is_ai = ai_choice == 'accept_liability'
                label = "✓ Agree — Accept Liability" if is_ai else "✕ Override — Accept Liability"
                if st.button(label, use_container_width=True, type="primary" if is_ai else "secondary"):
                    if is_ai:
                        record_analyst_choice(case, result, 'accept_liability', "ANALYST_AGREEMENT",
                                            "Analyst agreed with LLM recommendation", provider_used)
                        st.rerun()
                    else:
                        st.session_state.override_form_case_id = case_id
                        st.session_state.override_form_choice = 'accept_liability'
                        st.rerun()

            with override_col3:
                is_ai = ai_choice == 'request_more_evidence'
                label = "✓ Agree — Request Evidence" if is_ai else "⚠ Override — Request Evidence"
                if st.button(label, use_container_width=True, type="primary" if is_ai else "secondary"):
                    if is_ai:
                        record_analyst_choice(case, result, 'request_more_evidence', "ANALYST_AGREEMENT",
                                            "Analyst agreed with LLM recommendation", provider_used)
                        st.rerun()
                    else:
                        st.session_state.override_form_case_id = case_id
                        st.session_state.override_form_choice = 'request_more_evidence'
                        st.rerun()

        elif in_override and not in_interstitial:
            st.markdown('<div class="override-warning-box">', unsafe_allow_html=True)
            st.error("⚠️ You are overriding the AI recommendation")
            st.markdown(f"AI recommended: **{ai_choice.replace('_', ' ').title()}**")
            st.markdown(f"Your choice: **{st.session_state.override_form_choice.replace('_', ' ').title()}**")
            st.markdown('</div>', unsafe_allow_html=True)

            override_category = st.selectbox(
                "Override Category *",
                options=list(categories.keys()),
                format_func=lambda k: f"{k}: {categories[k]}",
                key="override_category"
            )

            override_detail = st.text_area(
                "Additional Detail (optional)",
                placeholder="Any extra context about your override decision...",
                height=80,
                key="override_detail"
            )

            confirm_col1, confirm_col2 = st.columns(2)
            with confirm_col1:
                if st.button("✅ Confirm & Review", use_container_width=True, type="primary"):
                    if override_category == "EDGE_CASE" and not override_detail.strip():
                        st.error("⚠️ EDGE_CASE requires additional detail.")
                    else:
                        st.session_state.interstitial_case_id = case_id
                        st.session_state.interstitial_category = override_category
                        st.session_state.interstitial_detail = override_detail
                        st.rerun()

            with confirm_col2:
                if st.button("❌ Cancel", use_container_width=True):
                    st.session_state.override_form_case_id = None
                    st.session_state.override_form_choice = None
                    st.rerun()

        elif in_interstitial:
            st.markdown('<div class="interstitial-box">', unsafe_allow_html=True)
            st.warning("🚨 **Confirm Override**")
            st.markdown(f"You are about to override the AI's **{ai_choice.replace('_', ' ').title()}** recommendation with **{st.session_state.override_form_choice.replace('_', ' ').title()}**.")
            st.markdown(f"**Category:** {categories.get(st.session_state.interstitial_category, 'Unknown')}")
            if st.session_state.get('interstitial_detail'):
                st.markdown(f"**Detail:** {st.session_state.interstitial_detail}")
            st.markdown('</div>', unsafe_allow_html=True)

            final_col1, final_col2 = st.columns(2)
            with final_col1:
                if st.button("✅ Yes, Confirm Override", use_container_width=True, type="primary"):
                    record_analyst_choice(
                        case, result,
                        st.session_state.override_form_choice,
                        st.session_state.interstitial_category,
                        st.session_state.get('interstitial_detail', ''),
                        provider_used
                    )
                    st.session_state.override_form_case_id = None
                    st.session_state.override_form_choice = None
                    st.session_state.interstitial_case_id = None
                    st.session_state.interstitial_category = None
                    st.session_state.interstitial_detail = None
                    st.rerun()

            with final_col2:
                if st.button("❌ No, Go Back", use_container_width=True):
                    st.session_state.interstitial_case_id = None
                    st.session_state.interstitial_category = None
                    st.session_state.interstitial_detail = None
                    st.rerun()

    else:
        decision = st.session_state.analyst_decisions[case_id]
        st.markdown(f"""
        <div class="case-resolved-banner">
            <div style="font-size: 12px; opacity: 0.7; margin-bottom: 4px;">CASE RESOLVED</div>
            <div style="font-size: 24px; font-weight: 700;">{decision['choice'].replace('_', ' ').title()}</div>
            <div style="font-size: 14px; opacity: 0.9; margin-top: 4px;">
                Recorded: {decision['timestamp'][:19]} | Provider: {decision['provider_used'].upper()}
            </div>
        </div>
        """, unsafe_allow_html=True)

        if decision.get('override_category') and decision['override_category'] != "ANALYST_AGREEMENT":
            st.info(f"Override: {decision['override_category']} — {decision.get('override_detail', '')}")

        # Admin override for resolved cases
        if st.session_state.admin_mode:
            st.divider()
            st.markdown("### 🔧 Admin Override")

            # Check if this case has already been admin-overwritten
            from telemetry import get_case_history
            case_history = get_case_history(case_id)
            already_admin_overwritten = any(
                e.get("override_category") == "ADMIN_CORRECTION" for e in case_history
            )

            if already_admin_overwritten:
                st.error("⚠️ This case has already been admin-overwritten. "
                         "Further changes require manager escalation.")
                # Show the overwrite history for transparency
                admin_entries = [e for e in case_history if e.get("override_category") == "ADMIN_CORRECTION"]
                if admin_entries:
                    latest = admin_entries[-1]
                    st.caption(f"Last admin overwrite: {latest['timestamp'][:19]} | "
                               f"By: {latest.get('analyst_id', 'unknown')} | "
                               f"To: {latest['analyst_override'].replace('_', ' ').title()}")
            else:
                st.warning("This case is resolved. As admin, you can overwrite the analyst decision once.")

                # Get current decision to filter it from overwrite options
                current_decision = decision['choice']
                overwrite_options = [
                    ("represent", "Overwrite → Represent", "primary"),
                    ("accept_liability", "Overwrite → Accept Liability", "secondary"),
                    ("request_more_evidence", "Overwrite → Request Evidence", "secondary")
                ]
                # Only show options that differ from current decision
                available_options = [opt for opt in overwrite_options if opt[0] != current_decision]

                if not available_options:
                    st.info("No alternative overwrite options available for this decision.")
                else:
                    cols = st.columns(len(available_options))
                    for idx, (choice, label, btn_type) in enumerate(available_options):
                        with cols[idx]:
                            if st.button(label, use_container_width=True, type=btn_type):
                                st.session_state.admin_override_case_id = case_id
                                st.session_state.admin_override_choice = choice
                                st.rerun()

            # Admin override confirmation form
            if st.session_state.get('admin_override_case_id') == case_id:
                st.markdown("---")
                st.error("⚠️ You are overwriting an analyst decision. This will be logged.")

                admin_reason = st.text_area(
                    "Reason for override *",
                    placeholder="Explain why this decision needs correction...",
                    height=80,
                    key="admin_override_reason"
                )

                admin_confirm_col1, admin_confirm_col2 = st.columns(2)
                with admin_confirm_col1:
                    if st.button("✅ Confirm Admin Override", use_container_width=True, type="primary"):
                        if not admin_reason.strip():
                            st.error("Reason required for admin override.")
                        else:
                            from telemetry import overwrite_decision

                            # Capture choice before clearing
                            override_choice = st.session_state.admin_override_choice

                            overwrite_decision(
                                case_id=case_id,
                                new_choice=override_choice,
                                admin_id=st.session_state.get('analyst_id', 'admin'),
                                reason=admin_reason
                            )

                            # Update session state
                            st.session_state.analyst_decisions[case_id] = {
                                'choice': override_choice,
                                'override_category': 'ADMIN_CORRECTION',
                                'override_detail': admin_reason,
                                'timestamp': datetime.now().isoformat(),
                                'provider_used': decision.get('provider_used', 'unknown')
                            }

                            # Clear override state
                            st.session_state.admin_override_case_id = None
                            st.session_state.admin_override_choice = None

                            st.success(f"✅ Admin override recorded: {override_choice.replace('_', ' ').title()}")
                            st.rerun()

                with admin_confirm_col2:
                    if st.button("❌ Cancel", use_container_width=True):
                        st.session_state.admin_override_case_id = None
                        st.session_state.admin_override_choice = None
                        st.rerun()


# ==================== TELEMETRY DASHBOARD (ADMIN ONLY) ====================
if st.session_state.admin_mode and st.session_state.show_telemetry:
    st.divider()
    st.markdown("## 📊 Telemetry Dashboard")

    summary = get_all_telemetry_summary()

    tel_col1, tel_col2, tel_col3, tel_col4, tel_col5 = st.columns(5)
    with tel_col1:
        st.metric("Total Cases", summary.get('total_cases', 0))
    with tel_col2:
        st.metric("Overrides", summary.get('total_overrides', 0))
    with tel_col3:
        rate = summary.get('overall_override_rate', 0) * 100
        st.metric("Override Rate", f"{rate:.0f}%")
    with tel_col4:
        st.metric("Admin Corrections", summary.get('total_admin_corrections', 0))
    with tel_col5:
        st.metric("Reason Codes", len(summary.get('reason_code_breakdown', {})))

    if summary.get('provider_breakdown'):
        st.markdown("### Provider Performance")
        provider_data = []
        for provider, data in summary['provider_breakdown'].items():
            provider_data.append({
                'Provider': provider.upper(),
                'Cases': data['total_cases'],
                'Overrides': data['overrides'],
                'Admin Corrections': data.get('admin_corrections', 0),
                'Override Rate': f"{data['override_rate']*100:.1f}%"
            })
        st.dataframe(provider_data, use_container_width=True, hide_index=True)

    if summary.get('reason_code_breakdown'):
        st.markdown("### Per-Reason-Code Breakdown")
        for rc, data in summary['reason_code_breakdown'].items():
            stats = get_reason_code_stats(rc)
            with st.expander(f"{rc} — {stats['override_rate']*100:.0f}% override rate ({stats['total_cases']} cases)"):
                st.markdown(f"**Override count:** {data['override_count']}")
                if data.get('top_category'):
                    st.markdown(f"**Top discrepancy:** {data['top_category']}")
                if stats.get('by_provider'):
                    st.markdown("**By Provider:**")
                    for provider, pdata in stats['by_provider'].items():
                        st.markdown(f"- {provider.upper()}: {pdata['count']} overrides")