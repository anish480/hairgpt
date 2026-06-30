"""MoxieBuddy demo UI — Streamlit chat interface.

Run:
    # Terminal 1: Start the FastAPI backend
    uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

    # Terminal 2: Start this UI
    uv run streamlit run scripts/demo_ui.py
"""

import base64
import re

import httpx
import streamlit as st

API_URL = "http://localhost:8000"

# --- MoxieBuddy avatar SVG (gender-neutral, squarish face, curly medium hair) ---

_AVATAR_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">
  <defs>
    <clipPath id="bg-clip"><rect x="5" y="5" width="90" height="90" rx="16"/></clipPath>
  </defs>
  <rect x="5" y="5" width="90" height="90" rx="16" fill="#F5E6D3"/>
  <g clip-path="url(#bg-clip)">
    <!-- Hair mass: single shape hugging the head + side curls -->
    <path d="M14,55 C14,68 16,78 20,85 L10,95 L-5,95 L-5,20
             C-5,5 15,-5 50,-5 C85,-5 105,5 105,20
             L105,95 L90,95 L80,85 C84,78 86,68 86,55
             C92,52 95,45 93,38 C91,31 86,28 82,28
             C82,18 70,6 50,6 C30,6 18,18 18,28
             C14,28 9,31 7,38 C5,45 8,52 14,55Z"
          fill="#4A3728"/>
    <!-- Curl texture overlays -->
    <circle cx="24" cy="10" r="10" fill="#5C4033"/>
    <circle cx="42" cy="4" r="11" fill="#5C4033"/>
    <circle cx="60" cy="4" r="11" fill="#5C4033"/>
    <circle cx="76" cy="10" r="10" fill="#5C4033"/>
    <circle cx="14" cy="22" r="8" fill="#5C4033"/>
    <circle cx="86" cy="22" r="8" fill="#5C4033"/>
    <!-- Side curl ringlets flowing from the hair mass -->
    <circle cx="10" cy="44" r="7" fill="#5C4033"/>
    <circle cx="90" cy="44" r="7" fill="#5C4033"/>
    <circle cx="8" cy="57" r="6.5" fill="#4A3728"/>
    <circle cx="92" cy="57" r="6.5" fill="#4A3728"/>
    <circle cx="10" cy="69" r="6" fill="#5C4033"/>
    <circle cx="90" cy="69" r="6" fill="#5C4033"/>
    <circle cx="14" cy="80" r="5.5" fill="#4A3728"/>
    <circle cx="86" cy="80" r="5.5" fill="#4A3728"/>
    <!-- Face: squarish proportions, natural contour -->
    <path d="M22,38 C22,30 30,24 50,24 C70,24 78,30 78,38
             L78,62 C78,66 77,70 74,74
             Q68,84 50,84 Q32,84 26,74
             C23,70 22,66 22,62Z"
          fill="#D4A574"/>
    <!-- Forehead hair overlap for seamless transition -->
    <path d="M22,38 C22,32 30,24 50,24 C70,24 78,32 78,38
             C75,34 65,30 50,30 C35,30 25,34 22,38Z"
          fill="#4A3728" opacity="0.45"/>
    <!-- Eyes -->
    <ellipse cx="38" cy="52" rx="3.8" ry="4.2" fill="#2C1810"/>
    <ellipse cx="62" cy="52" rx="3.8" ry="4.2" fill="#2C1810"/>
    <circle cx="36.5" cy="50.5" r="1.4" fill="white"/>
    <circle cx="60.5" cy="50.5" r="1.4" fill="white"/>
    <!-- Eyebrows -->
    <path d="M31 44 Q38 40 44 44" stroke="#3D2B1F" stroke-width="2" fill="none" stroke-linecap="round"/>
    <path d="M56 44 Q62 40 69 44" stroke="#3D2B1F" stroke-width="2" fill="none" stroke-linecap="round"/>
    <!-- Nose -->
    <path d="M48 57 Q50 61 52 57" stroke="#B8885C" stroke-width="1.5" fill="none" stroke-linecap="round"/>
    <!-- Smile -->
    <path d="M41 67 Q50 74 59 67" stroke="#2C1810" stroke-width="2" fill="none" stroke-linecap="round"/>
    <!-- Blush -->
    <ellipse cx="32" cy="64" rx="5" ry="3" fill="#E8A090" opacity="0.45"/>
    <ellipse cx="68" cy="64" rx="5" ry="3" fill="#E8A090" opacity="0.45"/>
  </g>
</svg>"""

_AVATAR_B64 = base64.b64encode(_AVATAR_SVG.encode()).decode()
_AVATAR_URI = f"data:image/svg+xml;base64,{_AVATAR_B64}"

# --- Camera SVG icon ---

_CAMERA_SVG_B64 = base64.b64encode(
    b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none"'
    b' stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    b'<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>'
    b'<circle cx="12" cy="13" r="4"/></svg>'
).decode()

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
    page_title="MoxieBuddy",
    page_icon="✨",
    layout="centered",
)

st.markdown(
    f"""
    <style>
    .stApp {{ max-width: 800px; margin: 0 auto; }}

    /* --- Header --- */
    .header-row {{
        display: flex; align-items: center; justify-content: center;
        gap: 0.6rem; margin-bottom: 1.5rem;
    }}
    .header-row img {{ width: 44px; height: 44px; border-radius: 10px; }}
    .header-row h1 {{ margin: 0; font-size: 1.8rem; }}

    /* --- Chat bubbles --- */
    [data-testid="stChatMessage"] {{
        background: transparent !important;
        border: none !important;
        padding: 0.25rem 0 !important;
    }}
    /* Hide default avatars */
    [data-testid="stChatMessage"] [data-testid="stAvatar"],
    [data-testid="stChatMessage"] .stAvatar {{
        display: none !important;
    }}

    /* User bubble: right-aligned */
    [data-testid="stChatMessage"][data-testid-type="user"] > div {{
        display: flex; flex-direction: column; align-items: flex-end;
    }}
    [data-testid="stChatMessage"][data-testid-type="user"] .stMarkdown p,
    [data-testid="stChatMessage"][data-testid-type="user"] .stMarkdown {{
        background: #DCF8C6; color: #1a1a1a;
        padding: 0.6rem 0.9rem; border-radius: 16px 16px 4px 16px;
        max-width: 80%; display: inline-block; text-align: left;
    }}

    /* AI bubble: left-aligned */
    [data-testid="stChatMessage"][data-testid-type="assistant"] > div {{
        display: flex; flex-direction: column; align-items: flex-start;
    }}
    [data-testid="stChatMessage"][data-testid-type="assistant"] .stMarkdown p,
    [data-testid="stChatMessage"][data-testid-type="assistant"] .stMarkdown {{
        background: #F0F0F0; color: #1a1a1a;
        padding: 0.6rem 0.9rem; border-radius: 16px 16px 16px 4px;
        max-width: 80%; display: inline-block;
    }}

    /* Typing indicator */
    .typing-indicator {{
        display: flex; align-items: center; gap: 4px;
        padding: 0.6rem 0.9rem; background: #F0F0F0;
        border-radius: 16px 16px 16px 4px; width: fit-content;
    }}
    .typing-indicator span {{
        width: 8px; height: 8px; border-radius: 50%;
        background: #999; display: inline-block;
        animation: bounce 1.4s infinite ease-in-out both;
    }}
    .typing-indicator span:nth-child(1) {{ animation-delay: -0.32s; }}
    .typing-indicator span:nth-child(2) {{ animation-delay: -0.16s; }}
    @keyframes bounce {{
        0%, 80%, 100% {{ transform: scale(0); }}
        40% {{ transform: scale(1); }}
    }}

    </style>

    <div class="header-row">
        <img src="{_AVATAR_URI}" alt="MoxieBuddy" />
        <h1>MoxieBuddy</h1>
    </div>
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
if "_attached_photo" not in st.session_state:
    st.session_state._attached_photo = None
if "_photo_widget_key" not in st.session_state:
    st.session_state._photo_widget_key = 0

# --- Chat input (always rendered unconditionally to prevent disappearance) ---

pending = st.session_state.pop("_pending", None)

prompt = None

if pending:
    prompt = pending

# --- Chat history ---

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            render_message_with_videos(msg["content"])
        else:
            if msg.get("image_bytes"):
                st.image(msg["image_bytes"], width=300)
            st.markdown(msg["content"])

# --- Suggested option buttons ---

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
    "My hair is so frizzy, help!",
    "I have wavy hair — what routine should I follow?",
    "How do I use the curl cream?",
    "What's the difference between the leave-in conditioner and the curl cream?",
]

if not st.session_state.messages:
    st.markdown("**Try asking:**")
    cols = st.columns(2)
    for i, ex in enumerate(EXAMPLES):
        col = cols[i % 2]
        if col.button(ex, key=f"ex_{i}", use_container_width=True):
            st.session_state._pending = ex
            st.rerun()

# --- Inline chat input with photo button ---

_wkey = st.session_state._photo_widget_key
_has_photo = st.session_state._attached_photo is not None

_col_photo, _col_chat = st.columns([1, 14], vertical_alignment="center")

with _col_photo:
    with st.popover("📷✓" if _has_photo else "📷"):
        if _has_photo:
            st.image(st.session_state._attached_photo["bytes"], width=200)
            _bc1, _bc2 = st.columns(2)
            if _bc1.button("📤 Send", key="send_photo", use_container_width=True):
                st.session_state._pending_photo_send = True
                st.rerun()
            if _bc2.button("✕ Remove", key="remove_photo", use_container_width=True):
                st.session_state._attached_photo = None
                st.session_state._photo_widget_key += 1
                st.rerun()
        else:
            _tab_upload, _tab_camera = st.tabs(["📁 Upload", "📸 Take Photo"])
            with _tab_upload:
                _photo_up = st.file_uploader(
                    "Choose a photo",
                    type=["jpg", "jpeg", "png", "webp", "heic"],
                    key=f"photo_upload_{_wkey}",
                )
                if _photo_up:
                    st.session_state._attached_photo = {
                        "bytes": _photo_up.getvalue(),
                        "name": _photo_up.name,
                        "type": _photo_up.type or "image/jpeg",
                    }
                    st.rerun()
            with _tab_camera:
                _camera_shot = st.camera_input(
                    "Take a photo of your hair",
                    key=f"camera_{_wkey}",
                )
                if _camera_shot:
                    st.session_state._attached_photo = {
                        "bytes": _camera_shot.getvalue(),
                        "name": "camera_photo.jpg",
                        "type": "image/jpeg",
                    }
                    st.rerun()

with _col_chat:
    chat_value = st.chat_input("Ask me anything about hair care...")
    if chat_value and not pending:
        prompt = chat_value

# --- Handle input ---

_photo_send = st.session_state.pop("_pending_photo_send", False)
_attached = st.session_state.get("_attached_photo")

if prompt or (_photo_send and _attached):
    user_display = prompt or ""
    image_bytes = _attached["bytes"] if _attached else None
    user_msg = {"role": "user", "content": user_display}
    if image_bytes:
        user_msg["image_bytes"] = image_bytes
    st.session_state.messages.append(user_msg)

    with st.chat_message("user"):
        if image_bytes:
            st.image(image_bytes, width=300)
        if user_display:
            st.markdown(user_display)

    # Typing indicator
    typing_placeholder = st.empty()
    typing_placeholder.markdown(
        '<div class="typing-indicator"><span></span><span></span><span></span></div>',
        unsafe_allow_html=True,
    )

    try:
        actual_message = user_display

        if image_bytes:
            mime_type = _attached["type"] if _attached else "image/jpeg"
            file_name = _attached["name"] if _attached else "photo.jpg"
            files = {"file": (file_name, image_bytes, mime_type)}
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
        st.session_state.suggested_options = data.get("suggested_options", [])
    except Exception as e:
        answer = f"Sorry, I hit a snag: {e}"
        st.session_state.suggested_options = []

    typing_placeholder.empty()

    with st.chat_message("assistant"):
        render_message_with_videos(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})

    if _attached:
        st.session_state._attached_photo = None
        st.session_state._photo_widget_key += 1

    if st.session_state.suggested_options or _attached:
        st.rerun()
