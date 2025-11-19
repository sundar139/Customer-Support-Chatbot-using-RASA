import os
import time
import json
from typing import List, Dict, Any
from uuid import uuid4

import requests
import streamlit as st


# Configuration
DEFAULT_RASA_ENDPOINT = os.getenv(
    "RASA_REST_ENDPOINT",
    "http://localhost:5006/webhooks/rest/webhook",
)
STATUS_ENDPOINT = os.getenv("RASA_STATUS_ENDPOINT", "http://localhost:5006/status")
# Derive base URL for Rasa HTTP API from status endpoint
BASE_RASA_URL = STATUS_ENDPOINT.rsplit("/status", 1)[0]


def get_status() -> Dict[str, Any]:
    try:
        resp = requests.get(STATUS_ENDPOINT, timeout=4)
        if resp.ok:
            return resp.json()
        return {"error": f"Status HTTP {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}


def send_to_rasa(sender_id: str, message: str, endpoint: str) -> List[Dict[str, Any]]:
    payload = {"sender": sender_id, "message": message}
    last_error: Exception | None = None
    # Simple resilience: one retry and longer timeout
    for attempt in range(2):
        try:
            resp = requests.post(endpoint, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            return [{"text": json.dumps(data)}]
        except Exception as e:
            last_error = e
            time.sleep(0.6)
    return [{"text": f"Request failed: {last_error}"}]


def restart_conversation(sender_id: str) -> bool:
    """Send a restart event to Rasa to reset tracker for the given sender."""
    try:
        url = f"{BASE_RASA_URL}/conversations/{sender_id}/events"
        resp = requests.post(url, json={"event": "restart"}, timeout=10)
        return resp.ok
    except Exception:
        return False


st.set_page_config(page_title="Rasa Chatbot • Streamlit", page_icon="🤖", layout="centered")
st.title("Rasa Chatbot (Streamlit UI)")

with st.sidebar:
    st.subheader("Connection")
    # Persist in session_state so resets are predictable
    if "endpoint" not in st.session_state:
        st.session_state.endpoint = DEFAULT_RASA_ENDPOINT
    if "active_sender_id" not in st.session_state:
        # Use a random default to avoid carrying old tracker state across sessions
        st.session_state.active_sender_id = f"streamlit-{uuid4().hex[:8]}"

    endpoint = st.text_input("Rasa REST endpoint", value=st.session_state.endpoint, key="endpoint_widget")
    st.session_state.endpoint = endpoint

    # Decouple active sender from widget state; apply only when requested
    sender_input = st.text_input("Sender ID (optional)", value="", key="sender_id_widget")
    apply_sid = st.button("Apply sender ID")
    if apply_sid and sender_input.strip():
        st.session_state.active_sender_id = sender_input.strip()
        st.success(f"Active sender updated.")

    st.caption(f"Active sender: {st.session_state.active_sender_id}")

    if st.button("Check server status"):
        status = get_status()
        if "error" in status:
            st.error(f"Status check failed: {status['error']}")
        else:
            st.success("Server is reachable")
            st.json(status)

    st.divider()
    st.caption("Tip: Start your actions on port 5055 and core on 5006.")


# Initialize chat history
if "messages" not in st.session_state:
    st.session_state["messages"] = []


# Render past messages
for m in st.session_state["messages"]:
    st.chat_message(m["role"]).markdown(m["content"])


# Chat input
prompt = st.chat_input("Type your message…")
if prompt:
    # Show user message
    st.session_state["messages"].append({"role": "user", "content": prompt})
    st.chat_message("user").markdown(prompt)

    # Send to Rasa
    with st.spinner("Contacting bot…"):
        replies = send_to_rasa(st.session_state.active_sender_id, prompt, endpoint)

    # Render bot replies
    for r in replies:
        # Prefer text; fallback to raw structure
        text = r.get("text")
        if not text:
            # Handle common fields loosely
            if "image" in r:
                text = f"[image] {r['image']}"
            elif "custom" in r:
                text = f"[custom] {json.dumps(r['custom'])}"
            else:
                text = json.dumps(r)

        st.session_state["messages"].append({"role": "assistant", "content": text})
        st.chat_message("assistant").markdown(text)


col1, col2 = st.columns(2)
with col1:
    if st.button("Quick test: report issue"):
        test_msg = "I need help with my order"
        st.session_state["messages"].append({"role": "user", "content": test_msg})
        st.chat_message("user").markdown(test_msg)
        with st.spinner("Contacting bot…"):
            replies = send_to_rasa(st.session_state.active_sender_id, test_msg, endpoint)
        for r in replies:
            text = r.get("text") or json.dumps(r)
            st.session_state["messages"].append({"role": "assistant", "content": text})
            st.chat_message("assistant").markdown(text)
    with col2:
        if st.button("Reset chat"):
            # Clear local transcript
            st.session_state["messages"] = []
            # Reset tracker on Rasa side for the current conversation
            restart_conversation(st.session_state.active_sender_id)
            # Rotate to a fresh sender id to ensure a clean start
            st.session_state.active_sender_id = f"streamlit-{uuid4().hex[:8]}"
            st.experimental_rerun()


st.caption("If messages fail, ensure the Rasa core server (5006) is running with REST enabled and actions server (5055) is up.")