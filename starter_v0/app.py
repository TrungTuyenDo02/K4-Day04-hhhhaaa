from datetime import datetime
from pathlib import Path

import streamlit as st

from chat import now_iso, run_model_tool_loop, safe_slug, write_transcript
from env_loader import load_lab_env
from providers import make_provider
from tools import load_tool_declarations, to_openai_tools
from versioning import artifact_version_dict, build_artifact_version

ROOT = Path(__file__).parent
load_lab_env(ROOT)

st.set_page_config(page_title="IT Helpdesk Agent", layout="wide")

SYSTEM_PROMPT_PATH = ROOT / "artifacts" / "system_prompt.md"
TOOLS_PATH = ROOT / "artifacts" / "tools.yaml"
TRANSCRIPTS_DIR = ROOT / "transcripts"

with st.sidebar:
    st.header("Cấu hình")
    provider_name = st.selectbox("Provider", ["openrouter", "openai", "anthropic", "gemini"], index=0)
    version_label = st.text_input("Artifact version label", value="v4")
    max_tool_rounds = st.number_input("Max tool rounds", min_value=1, max_value=10, value=4)
    if st.button("Xoá hội thoại"):
        st.session_state.pop("messages", None)
        st.session_state.pop("transcript_id", None)
        st.rerun()

# Luôn đọc lại artifact từ đĩa để phản ánh đúng bản system_prompt.md/tools.yaml hiện tại.
system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
tool_decls = load_tool_declarations(TOOLS_PATH)
openai_tools = to_openai_tools(tool_decls)
artifact_ver = build_artifact_version(version_label, SYSTEM_PROMPT_PATH, TOOLS_PATH)

st.title("🛠️ IT Helpdesk Agent — Northstar Labs")
st.caption(f"Artifact Version Active: `{artifact_ver.artifact_version}` | Provider: `{provider_name}`")

if "messages" not in st.session_state:
    st.session_state.messages = []

if "transcript_id" not in st.session_state:
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    st.session_state.transcript_id = "_".join([safe_slug(version_label), safe_slug(provider_name), "streamlit", timestamp])

transcript_path = TRANSCRIPTS_DIR / f"{st.session_state.transcript_id}.transcript.json"

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("status") and msg["status"] != "answered":
            st.caption(f"status: {msg['status']}")
        if msg.get("tools"):
            with st.expander("🔍 Chi tiết Tool Calling Traces"):
                st.json(msg["tools"])

if prompt := st.chat_input("Nhập yêu cầu hỗ trợ IT..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    chat_history = [{"role": "system", "content": system_prompt}]
    for m in st.session_state.messages:
        chat_history.append({"role": m["role"], "content": m["content"]})

    with st.chat_message("assistant"):
        with st.spinner("Agent đang xử lý và kích hoạt tools..."):
            try:
                provider = make_provider(provider_name)
                result = run_model_tool_loop(
                    provider=provider,
                    messages=chat_history,
                    tools=openai_tools,
                    model=None,
                    max_tool_rounds=max_tool_rounds,
                )
                status = result["status"]
                reply = result["assistant_text"]
                tool_events = result.get("tool_events", [])
                st.markdown(reply)
                if status != "answered":
                    st.caption(f"status: {status}")
                if tool_events:
                    with st.expander("🔍 Chi tiết Tool Calling Traces"):
                        st.json(tool_events)
            except Exception as exc:
                status = "provider_error"
                reply = f"Lỗi provider: {type(exc).__name__}: {exc}"
                tool_events = []
                st.error(reply)

    st.session_state.messages.append({
        "role": "assistant",
        "content": reply,
        "status": status,
        "tools": tool_events,
    })

    write_transcript(transcript_path, {
        "transcript_id": st.session_state.transcript_id,
        **artifact_version_dict(artifact_ver),
        "provider": provider_name,
        "system_prompt": str(SYSTEM_PROMPT_PATH),
        "tools": str(TOOLS_PATH),
        "max_tool_rounds": max_tool_rounds,
        "created_at": now_iso(),
        "turns": st.session_state.messages,
    })
    st.caption(f"Transcript: `{transcript_path}`")
