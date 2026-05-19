"""HairGPT demo UI — Streamlit chat interface.

Run:
    # Terminal 1: Start the FastAPI backend
    uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

    # Terminal 2: Start this UI
    uv run streamlit run scripts/demo_ui.py
"""

import re

import httpx
import streamlit as st

API_URL = "http://localhost:8000"

# --- YouTube embed helper ---

_MD_YT_LINK = re.compile(
    r"\[([^\]]*)\]\((https?://(?:www\.)?(?:youtube\.com/(?:shorts/|watch\?v=)|youtu\.be/)[\w-]{11})\)"
)
_YT_RE = re.compile(
    r"(https?://(?:www\.)?(?:youtube\.com/(?:shorts/|watch\?v=)|youtu\.be/)([\w-]{11}))"
)


def render_message_with_videos(text: str) -> None:
    text = _MD_YT_LINK.sub(r"\1: \2", text)
    parts = _YT_RE.split(text)
    # re.split with 2 capture groups produces: [text, full_url, video_id, text, ...]
    i = 0
    while i < len(parts):
        if i % 3 == 0:
            if parts[i].strip():
                st.markdown(parts[i].strip())
        elif i % 3 == 2:
            st.video(f"https://www.youtube.com/watch?v={parts[i]}")
        i += 1


# --- Page config ---

st.set_page_config(
    page_title="HairGPT by Moxie Beauty",
    page_icon="💇‍♀️",
    layout="centered",
)

st.markdown(
    """
    <style>
    .stApp { max-width: 800px; margin: 0 auto; }
    .title-block { text-align: center; margin-bottom: 0.5rem; }
    .title-block h1 { margin-bottom: 0; }
    .subtitle { text-align: center; color: #888; font-size: 1rem; margin-bottom: 2rem; }
    /* Replace the + attach icon with a camera icon */
    [data-testid="stChatInputFileUploadButton"] button svg { display: none; }
    [data-testid="stChatInputFileUploadButton"] button::after {
        content: "📷";
        font-size: 1.3rem;
        line-height: 1;
    }
    </style>
    <div class="title-block"><h1>HairGPT</h1></div>
    <div class="subtitle">by Moxie Beauty — Your AI Hair Consultant</div>
    """,
    unsafe_allow_html=True,
)

# --- Session state ---

if "messages" not in st.session_state:
    st.session_state.messages = []
if "api_history" not in st.session_state:
    st.session_state.api_history = []
if "suggested_options" not in st.session_state:
    st.session_state.suggested_options = []
if "hair_context" not in st.session_state:
    st.session_state.hair_context = None

# --- Chat history ---

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            render_message_with_videos(msg["content"])
        else:
            if msg.get("image_bytes"):
                st.image(msg["image_bytes"], width=300)
            st.markdown(msg["content"])

# --- Suggested option buttons (most recent message only) ---

if st.session_state.suggested_options:
    cols = st.columns(min(len(st.session_state.suggested_options), 3))
    for i, option in enumerate(st.session_state.suggested_options):
        col = cols[i % len(cols)]
        if col.button(option, key=f"opt_{i}", use_container_width=True):
            st.session_state.suggested_options = []
            st.session_state._pending = option
            st.rerun()

# --- Example prompts for empty chat ---

EXAMPLES = [
    "My hair is so frizzy in this weather, help!",
    "I have 2B wavy hair — what routine should I follow?",
    "How do I use the curl cream?",
    "What's the difference between the leave-in and the curl cream?",
    "I have coloured hair and it's really damaged",
]

if not st.session_state.messages:
    st.markdown("**Try asking:**")
    cols = st.columns(2)
    for i, ex in enumerate(EXAMPLES):
        col = cols[i % 2]
        if col.button(ex, key=f"ex_{i}", use_container_width=True):
            st.session_state._pending = ex
            st.rerun()

# --- Chat input (with inline 📷 for photo upload) ---

pending = st.session_state.pop("_pending", None)

uploaded_file = None
prompt = None

if pending:
    prompt = pending
else:
    chat_value = st.chat_input(
        "Ask me anything about hair care...",
        accept_file=True,
        file_type=["jpg", "jpeg", "png", "webp", "heic"],
    )
    if chat_value:
        prompt = chat_value.text or ""
        if chat_value["files"]:
            uploaded_file = chat_value["files"][0]

# --- Handle input ---

if prompt or uploaded_file:
    # Show user message
    user_display = prompt or ""
    image_bytes = uploaded_file.read() if uploaded_file else None
    user_msg = {"role": "user", "content": user_display}
    if image_bytes:
        user_msg["image_bytes"] = image_bytes
    st.session_state.messages.append(user_msg)

    with st.chat_message("user"):
        if image_bytes:
            st.image(image_bytes, width=300)
        if user_display:
            st.markdown(user_display)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                actual_message = user_display

                # Photo analysis flow
                if image_bytes:
                    mime_type = uploaded_file.type or "image/jpeg"
                    files = {"file": (uploaded_file.name, image_bytes, mime_type)}
                    photo_resp = httpx.post(
                        f"{API_URL}/photo/analyze", files=files, timeout=30.0
                    )
                    photo_resp.raise_for_status()
                    photo_data = photo_resp.json()
                    summary = photo_data["summary"]

                    st.session_state.hair_context = {
                        "classification": photo_data["classification"],
                        "summary": summary,
                    }

                    actual_message = (
                        f"[User uploaded a hair photo. Analysis: {summary}]\n\n"
                        "Please respond to this hair analysis naturally."
                    )
                    if user_display:
                        actual_message += f"\n\nThe user also said: {user_display}"

                # Inject hair context into subsequent messages (if not a photo message)
                elif (
                    st.session_state.hair_context
                    and st.session_state.hair_context.get("summary")
                ):
                    hair_prefix = f"[Hair photo analysis: {st.session_state.hair_context['summary']}]\n\n"
                    if not any(
                        hair_prefix in m.get("content", "")
                        for m in st.session_state.api_history
                    ):
                        actual_message = hair_prefix + actual_message

                # Send to chat
                resp = httpx.post(
                    f"{API_URL}/chat",
                    json={
                        "message": actual_message,
                        "history": st.session_state.api_history,
                    },
                    timeout=60.0,
                )
                resp.raise_for_status()
                data = resp.json()
                answer = data["response"]
                st.session_state.api_history = data["history"]
                st.session_state.suggested_options = data.get(
                    "suggested_options", []
                )
            except Exception as e:
                answer = f"Sorry, I hit a snag: {e}"
                st.session_state.suggested_options = []

        render_message_with_videos(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    if st.session_state.suggested_options:
        st.rerun()
