"""
app.py
-------
AirResolve AI -- Customer-Facing Airline Resolution Agent
Streamlit front-end. Run with:

    streamlit run app.py
"""

import os
import streamlit as st
from datetime import datetime
from dotenv import load_dotenv

from utils.data_loader import get_data_store
from utils.audit_logger import new_log, log_event, format_log_line
from agent.agent import Agent, LLMClient

load_dotenv()

st.set_page_config(
    page_title="AirResolve AI",
    page_icon="\u2708\ufe0f",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------

st.markdown("""
<style>
    #MainMenu, footer, header {visibility: hidden;}
    .stApp {
        background: linear-gradient(180deg, #0b1220 0%, #0e1626 100%);
    }
    section[data-testid="stSidebar"] {
        background: #0a0f1c;
        border-right: 1px solid #1c2740;
    }
    .arz-header {
        display: flex; justify-content: space-between; align-items: center;
        padding: 14px 20px; border-radius: 14px;
        background: linear-gradient(135deg, #0f1b30 0%, #142544 100%);
        border: 1px solid #22375f; margin-bottom: 14px;
    }
    .arz-title { font-size: 22px; font-weight: 800; color: #f2f6ff; letter-spacing: 0.3px; }
    .arz-subtitle { font-size: 12.5px; color: #7f93bf; margin-top: 2px; }
    .arz-status { display:flex; align-items:center; gap:8px; font-size: 13px; color:#9be89b; font-weight:600;}
    .arz-dot { width:9px; height:9px; border-radius:50%; background:#3ddc84; box-shadow: 0 0 8px #3ddc84; display:inline-block;}
    .arz-dot.mock { background:#f5b942; box-shadow: 0 0 8px #f5b942; }

    .arz-card {
        background: #101c33; border: 1px solid #22355c; border-radius: 14px;
        padding: 16px 18px; margin-bottom: 14px;
    }
    .arz-card h4 { margin: 0 0 10px 0; color: #cfe0ff; font-size: 14px; letter-spacing: 0.4px; text-transform: uppercase;}
    .arz-field { display:flex; justify-content:space-between; font-size: 13.5px; color:#dbe6ff; padding:4px 0; border-bottom: 1px dashed #1e2c4a;}
    .arz-field:last-child{border-bottom:none;}
    .arz-field span.label{color:#8298c4;}

    .badge { display:inline-block; padding: 2px 10px; border-radius: 999px; font-size: 11.5px; font-weight: 700; letter-spacing:.3px;}
    .badge-gold { background:#3a2c0b; color:#f5c451; border:1px solid #6b4f14;}
    .badge-silver { background:#26314a; color:#c7d4ef; border:1px solid #3d4f75;}
    .badge-platinum { background:#2a1c3d; color:#d9b8ff; border:1px solid #4c3170;}
    .badge-cancelled { background:#3a1414; color:#ff8a8a; border:1px solid #6b1f1f;}
    .badge-delayed { background:#3a2c0b; color:#f5b942; border:1px solid #6b4f14;}
    .badge-unaffected { background:#123a24; color:#7fe0a7; border:1px solid #1f6b41;}
    .badge-escalated { background:#3a1414; color:#ff9d6b; border:1px solid #6b3a1f;}
    .badge-allowed { background:#0f3a24; color:#6bffb0; border:1px solid #1f6b41;}

    .decision-box { border-radius: 12px; padding: 12px 14px; margin-bottom:10px; font-size: 13.3px; line-height:1.5;}
    .decision-allowed { background:#0d1f16; border:1px solid #1f6b41; color:#d9ffe8;}
    .decision-escalated { background:#241109; border:1px solid #6b3a1f; color:#ffe3cf;}
    .decision-info { background:#0f1a2e; border:1px solid #223458; color:#cfe0ff;}
    .decision-title { font-weight:700; margin-bottom:4px; display:flex; justify-content:space-between; align-items:center;}

    .action-line { font-family: 'SFMono-Regular', Consolas, monospace; font-size: 12.5px; color:#bcd0ff; padding:3px 0;}
    .metric-box { background:#101c33; border:1px solid #22355c; border-radius:12px; padding:12px 8px; text-align:center;}
    .metric-num { font-size: 22px; font-weight:800; color:#f2f6ff;}
    .metric-label { font-size:11px; color:#8298c4; text-transform:uppercase; letter-spacing:.4px;}

    div[data-testid="stChatMessage"] { background: transparent; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------------------

def init_state():
    defaults = {
        "messages": [],
        "current_customer": None,
        "audit_log": new_log(),
        "escalation_counter": 0,
        "granted_actions": set(),
        "last_decisions": [],
        "last_actions": [],
        "escalations_all": [],
        "actions_all": [],
        "cases_touched": set(),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


@st.cache_resource(show_spinner=False)
def get_agent():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    llm = LLMClient(api_key=api_key) if api_key else LLMClient(api_key=None)
    return Agent(llm_client=llm), llm


agent, llm_client = get_agent()
store = get_data_store()


def reset_conversation(keep_customer: bool):
    st.session_state.messages = []
    st.session_state.audit_log = new_log()
    st.session_state.escalation_counter = 0
    st.session_state.granted_actions = set()
    st.session_state.last_decisions = []
    st.session_state.last_actions = []
    st.session_state.escalations_all = []
    st.session_state.actions_all = []
    st.session_state.cases_touched = set()
    if not keep_customer:
        st.session_state.current_customer = None


def process_user_message(text: str):
    if not text.strip():
        return
    st.session_state.messages.append({"role": "customer", "content": text, "ts": datetime.now().strftime("%H:%M:%S")})

    result = agent.handle_message(
        user_text=text,
        current_customer=st.session_state.current_customer,
        audit_log=st.session_state.audit_log,
        escalation_counter=st.session_state.escalation_counter,
        granted_actions=st.session_state.granted_actions,
    )

    st.session_state.current_customer = result["customer"]
    st.session_state.escalation_counter = result["escalation_counter"]
    st.session_state.granted_actions = result["granted_actions"]
    st.session_state.last_decisions = result["decisions"]
    st.session_state.last_actions = result["actions"]
    st.session_state.actions_all.extend(result["actions"])
    st.session_state.escalations_all.extend(result["escalations"])
    if result["customer"]:
        st.session_state.cases_touched.add(result["customer"]["booking_reference"])

    st.session_state.messages.append({
        "role": "agent",
        "content": result["response_text"],
        "ts": datetime.now().strftime("%H:%M:%S"),
        "sentiment": result["sentiment"],
    })


SCENARIO_STARTERS = {
    "priya_nair": "My flight SK-204 was cancelled.",
    "arvind_kulkarni": "My flight has been delayed four hours. I missed an important meeting. I want a hotel.",
    "meher_kaur": "My flight is delayed six hours. I'd like a full night's hotel stay please.",
}


def load_scenario(customer_id: str):
    reset_conversation(keep_customer=False)
    customer = store.get_customer_by_id(customer_id)
    st.session_state.current_customer = customer
    log_event(st.session_state.audit_log, "identify", f"Customer identified: {customer['name']} (demo scenario)")
    log_event(st.session_state.audit_log, "retrieve", f"Booking retrieved: {customer['booking_reference']}")
    process_user_message(SCENARIO_STARTERS[customer_id])


# ---------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------

with st.sidebar:
    st.markdown("### \u2708\ufe0f AirResolve AI")
    st.caption("Customer Resolution Intelligence")

    if llm_client.available:
        st.markdown("<div class='arz-status'><span class='arz-dot'></span> LLM Mode -- Live</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='arz-status'><span class='arz-dot mock'></span> Mock Mode -- No API key</div>", unsafe_allow_html=True)
        st.caption("Set ANTHROPIC_API_KEY in your .env to enable live LLM-generated responses. The policy engine and all decisions work identically either way.")

    st.divider()
    st.markdown("#### \u25b6 Demo Scenarios")
    if st.button("Scenario 1 -- Priya (Cancellation)", use_container_width=True):
        load_scenario("priya_nair")
        st.rerun()
    if st.button("Scenario 2 -- Arvind (4h delay)", use_container_width=True):
        load_scenario("arvind_kulkarni")
        st.rerun()
    if st.button("Scenario 3 -- Meher (6h delay)", use_container_width=True):
        load_scenario("meher_kaur")
        st.rerun()

    st.divider()
    st.markdown("#### Customer Selector")
    customers = store.all_customers()
    names = ["-- none --"] + [c["name"] for c in customers]
    current_name = st.session_state.current_customer["name"] if st.session_state.current_customer else "-- none --"
    picked = st.selectbox("Set active customer manually", names, index=names.index(current_name) if current_name in names else 0, label_visibility="collapsed")
    if picked != "-- none --" and (not st.session_state.current_customer or st.session_state.current_customer["name"] != picked):
        chosen = store.get_customer_by_name(picked)
        st.session_state.current_customer = chosen
        log_event(st.session_state.audit_log, "identify", f"Customer identified: {chosen['name']} (manual selection)")
        log_event(st.session_state.audit_log, "retrieve", f"Booking retrieved: {chosen['booking_reference']}")
        st.rerun()

    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("New Conversation", use_container_width=True):
            reset_conversation(keep_customer=False)
            st.rerun()
    with col_b:
        if st.button("Clear Chat", use_container_width=True):
            reset_conversation(keep_customer=True)
            st.rerun()

    st.divider()
    st.caption("Prototype notice: all actions (refunds, vouchers, hotel bookings, escalations) are **simulated** for this demo. No real airline transactions occur.")


# ---------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------

status_html = (
    "<div class='arz-status'><span class='arz-dot'></span> Agent Online</div>"
    if True else ""
)
st.markdown(f"""
<div class="arz-header">
  <div>
    <div class="arz-title">\u2708 AIRRESOLVE AI</div>
    <div class="arz-subtitle">Customer Resolution Intelligence &mdash; Grounded Policy Agent</div>
  </div>
  {status_html}
</div>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------
# Layout: chat (left) + case panel (right)
# ---------------------------------------------------------------------

chat_col, panel_col = st.columns([2.1, 1])

TIER_BADGE_CLASS = {"Gold": "badge-gold", "Silver": "badge-silver", "Platinum": "badge-platinum"}
STATUS_BADGE_CLASS = {"Cancelled": "badge-cancelled", "Delayed": "badge-delayed", "Unaffected": "badge-unaffected"}


with chat_col:
    st.markdown("#### AI Conversation")
    chat_box = st.container(height=430, border=True)
    with chat_box:
        if not st.session_state.messages:
            st.info("Load a demo scenario from the sidebar, or just start typing below (e.g. *'My flight SK-204 was cancelled.'*).")
        for msg in st.session_state.messages:
            if msg["role"] == "customer":
                with st.chat_message("user", avatar="\U0001F9D1"):
                    st.markdown(msg["content"])
                    st.caption(msg["ts"])
            else:
                with st.chat_message("assistant", avatar="\u2708\ufe0f"):
                    st.markdown(msg["content"])
                    st.caption(f"{msg['ts']} \u00b7 detected tone: {msg.get('sentiment', 'calm')}")

    # Quick action buttons
    qa_cols = st.columns(4)
    quick_actions = [
        ("Flight status", "What's the status of my flight?"),
        ("Cancellation", "My flight was cancelled."),
        ("Delay compensation", "My flight is delayed, what am I entitled to?"),
        ("Escalate / complaint", "I want to file a formal complaint about this."),
    ]
    for col, (label, canned) in zip(qa_cols, quick_actions):
        if col.button(label, use_container_width=True, key=f"qa_{label}"):
            process_user_message(canned)
            st.rerun()

    user_text = st.chat_input("Type the customer's message...")
    if user_text:
        process_user_message(user_text)
        st.rerun()


with panel_col:
    st.markdown("#### Case Panel")
    customer = st.session_state.current_customer

    if not customer:
        st.markdown("<div class='arz-card'><h4>No active case</h4><span style='color:#8298c4;font-size:13px;'>Select a customer or load a demo scenario to begin.</span></div>", unsafe_allow_html=True)
    else:
        booking = store.get_booking_for_customer(customer)
        flight = store.get_flight(customer["booking_reference"], leg="outbound")
        tier_badge = TIER_BADGE_CLASS.get(customer["loyalty_tier"], "badge-silver")
        status_badge = STATUS_BADGE_CLASS.get(flight.get("status"), "badge-delayed") if flight else ""

        st.markdown(f"""
        <div class="arz-card">
          <h4>Customer</h4>
          <div class="arz-field"><span class="label">Name</span><span>{customer['name']}</span></div>
          <div class="arz-field"><span class="label">Loyalty Tier</span><span class="badge {tier_badge}">{customer['loyalty_tier']}</span></div>
          <div class="arz-field"><span class="label">PNR</span><span>{customer['booking_reference']}</span></div>
          <div class="arz-field"><span class="label">Prior complaints</span><span>{customer['travel_history']['prior_complaints']}</span></div>
        </div>
        """, unsafe_allow_html=True)

        if flight:
            st.markdown(f"""
            <div class="arz-card">
              <h4>Flight</h4>
              <div class="arz-field"><span class="label">Flight</span><span>{flight['flight_number']}</span></div>
              <div class="arz-field"><span class="label">Route</span><span>{flight['route']}</span></div>
              <div class="arz-field"><span class="label">Date</span><span>{flight['date']}</span></div>
              <div class="arz-field"><span class="label">Departure</span><span>{flight['scheduled_departure']}</span></div>
              <div class="arz-field"><span class="label">Status</span><span class="badge {status_badge}">{flight['status']}{' ' + str(flight.get('delay_hours')) + 'h' if flight.get('delay_hours') else ''}</span></div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<div class='arz-card'><h4>Policy Decision</h4>", unsafe_allow_html=True)
        if not st.session_state.last_decisions:
            st.markdown("<span style='color:#8298c4;font-size:13px;'>No policy check yet this turn.</span></div>", unsafe_allow_html=True)
        else:
            for d in st.session_state.last_decisions:
                if d.get("requires_escalation"):
                    box_class, icon = "decision-escalated", "\u26a0\ufe0f"
                elif d.get("eligible"):
                    box_class, icon = "decision-allowed", "\u2713"
                else:
                    box_class, icon = "decision-info", "\u2139\ufe0f"
                title = d.get("intent", "").replace("_", " ").title()
                policy_used = d.get("policy_used") or "\u2014"
                st.markdown(f"""
                <div class="decision-box {box_class}">
                  <div class="decision-title"><span>{icon} {title}</span></div>
                  <div style="color:#8298c4;font-size:11.5px;margin-bottom:4px;">Policy used: {policy_used}</div>
                  <div>{d.get('reason', '')}</div>
                </div>
                """, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------
# Bottom: Action log + Escalations + Metrics
# ---------------------------------------------------------------------

st.divider()
log_col, esc_col, metric_col = st.columns([1.3, 1.3, 1])

with log_col:
    st.markdown("#### Action / Audit Log")
    with st.container(height=220, border=True):
        if not st.session_state.audit_log:
            st.caption("No events yet.")
        for entry in reversed(st.session_state.audit_log):
            st.markdown(f"<div class='action-line'>{format_log_line(entry)}</div>", unsafe_allow_html=True)

with esc_col:
    st.markdown("#### Escalations")
    with st.container(height=220, border=True):
        if not st.session_state.escalations_all:
            st.caption("No escalations this session.")
        for e in reversed(st.session_state.escalations_all):
            st.markdown(f"""
            <div class="decision-box decision-escalated">
              <div class="decision-title"><span>\u26a0\ufe0f {e['escalation_id']}</span><span class="badge badge-escalated">{e['status']}</span></div>
              <div style="font-size:12.5px;">
                Customer: {e['customer']} &middot; PNR: {e['pnr']}<br>
                Request: {e['requested_action']}<br>
                Policy limit: {e['policy_constraint']}<br>
                Reason: {e['reason']}
              </div>
            </div>
            """, unsafe_allow_html=True)

with metric_col:
    st.markdown("#### Dashboard")
    m1, m2 = st.columns(2)
    m3, m4 = st.columns(2)
    policy_checks = sum(1 for e in st.session_state.audit_log if e["category"] == "policy")
    with m1:
        st.markdown(f"<div class='metric-box'><div class='metric-num'>{len(st.session_state.cases_touched)}</div><div class='metric-label'>Cases</div></div>", unsafe_allow_html=True)
    with m2:
        st.markdown(f"<div class='metric-box'><div class='metric-num'>{len(st.session_state.actions_all)}</div><div class='metric-label'>Actions</div></div>", unsafe_allow_html=True)
    with m3:
        st.markdown(f"<div class='metric-box'><div class='metric-num'>{len(st.session_state.escalations_all)}</div><div class='metric-label'>Escalations</div></div>", unsafe_allow_html=True)
    with m4:
        st.markdown(f"<div class='metric-box'><div class='metric-num'>{policy_checks}</div><div class='metric-label'>Policy Checks</div></div>", unsafe_allow_html=True)
