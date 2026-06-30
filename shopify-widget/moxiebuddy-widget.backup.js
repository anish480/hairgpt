/**
 * MoxieBuddy Chat Widget — Shopify Injection Script
 * Drop this into a <script> tag in theme.liquid to add the floating chat widget.
 *
 * Configuration (set via window.MoxieBuddyConfig before loading this script):
 *   - apiBaseUrl:  Backend URL (default: "http://localhost:8000")
 *   - shopContext: { pageType, productHandle, customerId } — typically set from Liquid
 */
(function () {
  "use strict";

  /* ───────────────────────── Configuration ───────────────────────── */

  var cfg = window.MoxieBuddyConfig || {};
  var API = (cfg.apiBaseUrl || "http://localhost:8000").replace(/\/+$/, "");
  var shopContext = cfg.shopContext || {};

  /* ───────────────────────── Session persistence ───────────────────────── */

  var STORAGE_KEY = "moxiebuddy_session";

  function loadSession() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (raw) return JSON.parse(raw);
    } catch (_) {}
    return { sessionId: "", history: [], messages: [], hairContext: null };
  }

  function saveSession() {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          sessionId: state.sessionId,
          history: state.history,
          messages: state.messages,
          hairContext: state.hairContext,
        })
      );
    } catch (_) {}
  }

  var state = loadSession();
  if (!state.messages) state.messages = [];
  if (!state.history) state.history = [];
  if (!state.sessionId) state.sessionId = "";
  state.suggestedOptions = [];
  state.isOpen = false;
  state.isSending = false;

  /* ───────────────────────── Avatar SVG ───────────────────────── */

  var AVATAR_SVG =
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">' +
    '<defs><clipPath id="mb-bg-clip"><rect x="5" y="5" width="90" height="90" rx="16"/></clipPath></defs>' +
    '<rect x="5" y="5" width="90" height="90" rx="16" fill="#F5E6D3"/>' +
    '<g clip-path="url(#mb-bg-clip)">' +
    '<path d="M14,55 C14,68 16,78 20,85 L10,95 L-5,95 L-5,20 C-5,5 15,-5 50,-5 C85,-5 105,5 105,20 L105,95 L90,95 L80,85 C84,78 86,68 86,55 C92,52 95,45 93,38 C91,31 86,28 82,28 C82,18 70,6 50,6 C30,6 18,18 18,28 C14,28 9,31 7,38 C5,45 8,52 14,55Z" fill="#4A3728"/>' +
    '<circle cx="24" cy="10" r="10" fill="#5C4033"/><circle cx="42" cy="4" r="11" fill="#5C4033"/>' +
    '<circle cx="60" cy="4" r="11" fill="#5C4033"/><circle cx="76" cy="10" r="10" fill="#5C4033"/>' +
    '<circle cx="14" cy="22" r="8" fill="#5C4033"/><circle cx="86" cy="22" r="8" fill="#5C4033"/>' +
    '<circle cx="10" cy="44" r="7" fill="#5C4033"/><circle cx="90" cy="44" r="7" fill="#5C4033"/>' +
    '<circle cx="8" cy="57" r="6.5" fill="#4A3728"/><circle cx="92" cy="57" r="6.5" fill="#4A3728"/>' +
    '<circle cx="10" cy="69" r="6" fill="#5C4033"/><circle cx="90" cy="69" r="6" fill="#5C4033"/>' +
    '<circle cx="14" cy="80" r="5.5" fill="#4A3728"/><circle cx="86" cy="80" r="5.5" fill="#4A3728"/>' +
    '<path d="M22,38 C22,30 30,24 50,24 C70,24 78,30 78,38 L78,62 C78,66 77,70 74,74 Q68,84 50,84 Q32,84 26,74 C23,70 22,66 22,62Z" fill="#D4A574"/>' +
    '<path d="M22,38 C22,32 30,24 50,24 C70,24 78,32 78,38 C75,34 65,30 50,30 C35,30 25,34 22,38Z" fill="#4A3728" opacity="0.45"/>' +
    '<ellipse cx="38" cy="52" rx="3.8" ry="4.2" fill="#2C1810"/><ellipse cx="62" cy="52" rx="3.8" ry="4.2" fill="#2C1810"/>' +
    '<circle cx="36.5" cy="50.5" r="1.4" fill="white"/><circle cx="60.5" cy="50.5" r="1.4" fill="white"/>' +
    '<path d="M31 44 Q38 40 44 44" stroke="#3D2B1F" stroke-width="2" fill="none" stroke-linecap="round"/>' +
    '<path d="M56 44 Q62 40 69 44" stroke="#3D2B1F" stroke-width="2" fill="none" stroke-linecap="round"/>' +
    '<path d="M48 57 Q50 61 52 57" stroke="#B8885C" stroke-width="1.5" fill="none" stroke-linecap="round"/>' +
    '<path d="M41 67 Q50 74 59 67" stroke="#2C1810" stroke-width="2" fill="none" stroke-linecap="round"/>' +
    '<ellipse cx="32" cy="64" rx="5" ry="3" fill="#E8A090" opacity="0.45"/>' +
    '<ellipse cx="68" cy="64" rx="5" ry="3" fill="#E8A090" opacity="0.45"/>' +
    "</g></svg>";

  /* ───────────────────────── YouTube helper ───────────────────────── */

  var YT_RE = /https?:\/\/(?:www\.)?(?:youtube\.com\/(?:shorts\/|watch\?v=)|youtu\.be\/)([\w-]{11})/g;
  var MD_YT_LINK = /\[([^\]]*)\]\((https?:\/\/(?:www\.)?(?:youtube\.com\/(?:shorts\/|watch\?v=)|youtu\.be\/)[\w-]{11})\)/g;

  function renderMarkdownText(text) {
    // Strip markdown YouTube links to plain URLs
    var cleaned = text.replace(MD_YT_LINK, "$1: $2");
    var parts = [];
    var lastIndex = 0;
    var match;
    var regex = new RegExp(YT_RE.source, "g");
    while ((match = regex.exec(cleaned)) !== null) {
      if (match.index > lastIndex) {
        parts.push({ type: "text", value: cleaned.slice(lastIndex, match.index) });
      }
      parts.push({ type: "youtube", videoId: match[1], url: match[0] });
      lastIndex = regex.lastIndex;
    }
    if (lastIndex < cleaned.length) {
      parts.push({ type: "text", value: cleaned.slice(lastIndex) });
    }
    return parts;
  }

  function simpleMarkdown(text) {
    // Minimal markdown: bold, italic, line breaks
    var s = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/\*(.+?)\*/g, "<em>$1</em>");
    s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    s = s.replace(/\n/g, "<br>");
    return s;
  }

  /* ───────────────────────── CSS ───────────────────────── */

  var CSS = `
    #mb-widget *,#mb-widget *::before,#mb-widget *::after{box-sizing:border-box;margin:0;padding:0;}
    #mb-widget{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-size:14px;line-height:1.45;color:#1a1a1a;position:fixed;bottom:20px;right:20px;z-index:999999;}

    /* Floating bubble */
    #mb-bubble{width:60px;height:60px;border-radius:50%;background:#4A3728;border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 16px rgba(0,0,0,0.2);transition:transform .2s ease,box-shadow .2s ease;}
    #mb-bubble:hover{transform:scale(1.08);box-shadow:0 6px 24px rgba(0,0,0,0.28);}
    #mb-bubble svg{width:36px;height:36px;border-radius:8px;}

    /* Panel */
    #mb-panel{display:none;flex-direction:column;width:380px;height:600px;max-height:calc(100vh - 100px);background:#fff;border-radius:16px;box-shadow:0 8px 40px rgba(0,0,0,0.18);overflow:hidden;position:fixed;bottom:90px;right:20px;z-index:999999;}
    #mb-panel.mb-open{display:flex;}
    @media(max-width:440px){#mb-panel{width:calc(100vw - 16px);right:8px;bottom:80px;height:calc(100vh - 100px);border-radius:12px;}}

    /* Header */
    #mb-header{display:flex;align-items:center;gap:10px;padding:14px 16px;background:#4A3728;color:#fff;flex-shrink:0;}
    #mb-header svg{width:36px;height:36px;border-radius:8px;flex-shrink:0;}
    #mb-header-title{font-size:16px;font-weight:700;flex:1;}
    #mb-close-btn{background:none;border:none;color:#fff;font-size:22px;cursor:pointer;padding:4px 8px;line-height:1;opacity:0.8;transition:opacity .15s;}
    #mb-close-btn:hover{opacity:1;}

    /* Messages area */
    #mb-messages{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:8px;background:#fafaf8;}
    #mb-messages::-webkit-scrollbar{width:5px;}
    #mb-messages::-webkit-scrollbar-thumb{background:#ccc;border-radius:4px;}

    /* Message bubbles */
    .mb-msg{max-width:82%;padding:10px 14px;border-radius:16px;word-wrap:break-word;font-size:14px;line-height:1.45;}
    .mb-msg a{color:#4A3728;text-decoration:underline;}
    .mb-msg-user{align-self:flex-end;background:#DCF8C6;color:#1a1a1a;border-bottom-right-radius:4px;}
    .mb-msg-bot{align-self:flex-start;background:#f0f0f0;color:#1a1a1a;border-bottom-left-radius:4px;}
    .mb-msg-bot .mb-avatar-inline{display:inline-block;width:20px;height:20px;vertical-align:middle;margin-right:4px;border-radius:4px;}

    /* Image preview in chat */
    .mb-msg-user img.mb-chat-img{max-width:200px;border-radius:10px;margin-bottom:6px;display:block;}

    /* YouTube embed */
    .mb-yt-embed{margin:8px 0;border-radius:10px;overflow:hidden;position:relative;padding-bottom:56.25%;height:0;}
    .mb-yt-embed iframe{position:absolute;top:0;left:0;width:100%;height:100%;border:0;}

    /* Typing indicator */
    .mb-typing{align-self:flex-start;display:flex;align-items:center;gap:4px;padding:10px 14px;background:#f0f0f0;border-radius:16px 16px 16px 4px;width:fit-content;}
    .mb-typing span{width:7px;height:7px;border-radius:50%;background:#999;display:inline-block;animation:mb-bounce 1.4s infinite ease-in-out both;}
    .mb-typing span:nth-child(1){animation-delay:-0.32s;}
    .mb-typing span:nth-child(2){animation-delay:-0.16s;}
    @keyframes mb-bounce{0%,80%,100%{transform:scale(0);}40%{transform:scale(1);}}

    /* Suggested options */
    #mb-options{display:flex;flex-wrap:wrap;gap:6px;padding:0 16px 10px 16px;background:#fafaf8;flex-shrink:0;}
    .mb-opt-btn{background:#fff;border:1.5px solid #4A3728;color:#4A3728;border-radius:20px;padding:7px 14px;font-size:13px;cursor:pointer;transition:background .15s,color .15s;white-space:nowrap;}
    .mb-opt-btn:hover{background:#4A3728;color:#fff;}

    /* Example prompts (shown on empty chat) */
    #mb-examples{padding:0 16px 10px;display:flex;flex-direction:column;gap:6px;background:#fafaf8;flex-shrink:0;}
    #mb-examples-label{font-size:13px;font-weight:600;color:#666;margin-bottom:2px;}
    .mb-ex-btn{background:#fff;border:1px solid #ddd;border-radius:12px;padding:8px 12px;font-size:13px;cursor:pointer;text-align:left;color:#333;transition:border-color .15s,background .15s;}
    .mb-ex-btn:hover{border-color:#4A3728;background:#fdf9f5;}

    /* Input area */
    #mb-input-area{display:flex;align-items:flex-end;gap:8px;padding:10px 12px;border-top:1px solid #eee;background:#fff;flex-shrink:0;}
    #mb-text-input{flex:1;border:1.5px solid #ddd;border-radius:20px;padding:9px 14px;font-size:14px;outline:none;resize:none;max-height:80px;min-height:36px;font-family:inherit;line-height:1.35;transition:border-color .15s;}
    #mb-text-input:focus{border-color:#4A3728;}
    #mb-text-input::placeholder{color:#aaa;}

    /* Photo upload button */
    #mb-photo-btn{background:none;border:none;cursor:pointer;padding:6px;opacity:0.6;transition:opacity .15s;flex-shrink:0;}
    #mb-photo-btn:hover{opacity:1;}
    #mb-photo-btn svg{width:22px;height:22px;stroke:#4A3728;fill:none;}
    #mb-photo-input{display:none;}

    /* Send button */
    #mb-send-btn{background:#4A3728;border:none;border-radius:50%;width:36px;height:36px;display:flex;align-items:center;justify-content:center;cursor:pointer;flex-shrink:0;transition:opacity .15s;}
    #mb-send-btn:disabled{opacity:0.4;cursor:not-allowed;}
    #mb-send-btn svg{width:18px;height:18px;fill:#fff;}

    /* Notification badge on bubble (hidden by default, shown via .mb-show) */
    #mb-badge{display:none;position:absolute;top:-2px;right:-2px;background:#e74c3c;color:#fff;font-size:11px;font-weight:700;width:20px;height:20px;border-radius:50%;align-items:center;justify-content:center;line-height:1;}
    #mb-badge.mb-show{display:flex;}
  `;

  /* ───────────────────────── Build DOM ───────────────────────── */

  function buildWidget() {
    var container = document.createElement("div");
    container.id = "mb-widget";

    // Inject CSS
    var style = document.createElement("style");
    style.textContent = CSS;
    container.appendChild(style);

    // Floating bubble
    var bubble = document.createElement("button");
    bubble.id = "mb-bubble";
    bubble.setAttribute("aria-label", "Open MoxieBuddy chat");
    bubble.innerHTML = AVATAR_SVG;
    container.appendChild(bubble);

    // Chat panel
    var panel = document.createElement("div");
    panel.id = "mb-panel";
    panel.innerHTML =
      '<div id="mb-header">' +
      AVATAR_SVG +
      '<span id="mb-header-title">MoxieBuddy</span>' +
      '<button id="mb-close-btn" aria-label="Close chat">&times;</button>' +
      "</div>" +
      '<div id="mb-messages"></div>' +
      '<div id="mb-options"></div>' +
      '<div id="mb-examples"></div>' +
      '<div id="mb-input-area">' +
      '<label id="mb-photo-btn" aria-label="Upload a photo">' +
      '<svg viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>' +
      '<circle cx="12" cy="13" r="4"/>' +
      "</svg>" +
      '<input type="file" id="mb-photo-input" accept="image/jpeg,image/png,image/webp,image/heic">' +
      "</label>" +
      '<textarea id="mb-text-input" placeholder="Ask me anything about hair care..." rows="1"></textarea>' +
      '<button id="mb-send-btn" aria-label="Send message" disabled>' +
      '<svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>' +
      "</button>" +
      "</div>";
    container.appendChild(panel);

    document.body.appendChild(container);
  }

  /* ───────────────────────── DOM helpers ───────────────────────── */

  function $(id) {
    return document.getElementById(id);
  }

  function scrollToBottom() {
    var el = $("mb-messages");
    if (el) el.scrollTop = el.scrollHeight;
  }

  function addMessageToDOM(role, html, imageDataUrl) {
    var msgDiv = document.createElement("div");
    msgDiv.className = "mb-msg " + (role === "user" ? "mb-msg-user" : "mb-msg-bot");
    var inner = "";
    if (imageDataUrl && role === "user") {
      inner += '<img class="mb-chat-img" src="' + imageDataUrl + '" alt="Uploaded photo">';
    }
    inner += html;
    msgDiv.innerHTML = inner;
    $("mb-messages").appendChild(msgDiv);
    scrollToBottom();
  }

  function renderBotMessage(text) {
    var parts = renderMarkdownText(text);
    var html = "";
    for (var i = 0; i < parts.length; i++) {
      if (parts[i].type === "text") {
        html += simpleMarkdown(parts[i].value.trim());
      } else if (parts[i].type === "youtube") {
        html +=
          '<div class="mb-yt-embed"><iframe src="https://www.youtube.com/embed/' +
          parts[i].videoId +
          '?rel=0" allowfullscreen loading="lazy"></iframe></div>';
      }
    }
    return html;
  }

  function showTyping() {
    var el = document.createElement("div");
    el.className = "mb-typing";
    el.id = "mb-typing";
    el.innerHTML = "<span></span><span></span><span></span>";
    $("mb-messages").appendChild(el);
    scrollToBottom();
  }

  function hideTyping() {
    var el = $("mb-typing");
    if (el) el.remove();
  }

  function renderOptions(options) {
    var container = $("mb-options");
    container.innerHTML = "";
    if (!options || options.length === 0) return;
    for (var i = 0; i < options.length; i++) {
      var btn = document.createElement("button");
      btn.className = "mb-opt-btn";
      btn.textContent = options[i];
      btn.addEventListener(
        "click",
        (function (text) {
          return function () {
            sendMessage(text);
          };
        })(options[i])
      );
      container.appendChild(btn);
    }
  }

  function renderExamples() {
    var container = $("mb-examples");
    container.innerHTML = "";
    if (state.messages.length > 0) return;
    var examples = [
      "My hair is so frizzy, help!",
      "I have wavy hair — what routine should I follow?",
      "How do I use the curl cream?",
      "What's the difference between the leave-in conditioner and the curl cream?",
    ];
    var label = document.createElement("div");
    label.id = "mb-examples-label";
    label.textContent = "Try asking:";
    container.appendChild(label);
    for (var i = 0; i < examples.length; i++) {
      var btn = document.createElement("button");
      btn.className = "mb-ex-btn";
      btn.textContent = examples[i];
      btn.addEventListener(
        "click",
        (function (text) {
          return function () {
            sendMessage(text);
          };
        })(examples[i])
      );
      container.appendChild(btn);
    }
  }

  function clearExamples() {
    var container = $("mb-examples");
    if (container) container.innerHTML = "";
  }

  /* ───────────────────────── Restore chat history in DOM ───────────────────────── */

  function restoreMessages() {
    var messagesEl = $("mb-messages");
    messagesEl.innerHTML = "";
    for (var i = 0; i < state.messages.length; i++) {
      var msg = state.messages[i];
      if (msg.role === "user") {
        var escaped = simpleMarkdown(msg.text || "");
        addMessageToDOM("user", escaped, msg.imageDataUrl || null);
      } else {
        addMessageToDOM("bot", renderBotMessage(msg.text));
      }
    }
    renderOptions(state.suggestedOptions);
    renderExamples();
    scrollToBottom();
  }

  /* ───────────────────────── API calls ───────────────────────── */

  function sendMessage(text, imageFile, imageDataUrl) {
    if (state.isSending) return;
    if (!text && !imageFile) return;

    state.isSending = true;
    clearExamples();
    $("mb-options").innerHTML = "";
    updateSendButton();

    // Show user message
    var userDisplay = text || "";
    var userMsg = { role: "user", text: userDisplay };
    if (imageDataUrl) userMsg.imageDataUrl = imageDataUrl;
    state.messages.push(userMsg);
    addMessageToDOM("user", simpleMarkdown(userDisplay), imageDataUrl || null);
    saveSession();

    // Clear input
    var input = $("mb-text-input");
    input.value = "";
    autoResizeTextarea(input);
    updateSendButton();

    showTyping();

    var actualMessage = userDisplay;

    // If there's an image, first call /photo/analyze, then /chat
    if (imageFile) {
      analyzePhoto(imageFile)
        .then(function (photoData) {
          var summary = photoData.summary;
          state.hairContext = {
            classification: photoData.classification,
            summary: summary,
          };
          actualMessage =
            "[User uploaded a hair photo. Analysis: " +
            summary +
            "]\n\nPlease respond to this hair analysis naturally.";
          if (userDisplay) {
            actualMessage += "\n\nThe user also said: " + userDisplay;
          }
          return callChat(actualMessage);
        })
        .then(function (data) {
          handleChatResponse(data);
        })
        .catch(function (err) {
          handleChatError(err);
        });
    } else {
      // Prepend hair context if available and not yet in history
      if (state.hairContext && state.hairContext.summary) {
        var prefix = "[Hair photo analysis: " + state.hairContext.summary + "]\n\n";
        var alreadyInHistory = state.history.some(function (m) {
          return m.content && m.content.indexOf(prefix) !== -1;
        });
        if (!alreadyInHistory) {
          actualMessage = prefix + actualMessage;
        }
      }
      callChat(actualMessage)
        .then(function (data) {
          handleChatResponse(data);
        })
        .catch(function (err) {
          handleChatError(err);
        });
    }
  }

  function callChat(message) {
    return fetch(API + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: message,
        session_id: state.sessionId,
        history: state.history,
      }),
    }).then(function (res) {
      if (!res.ok) throw new Error("Chat API error: " + res.status);
      return res.json();
    });
  }

  function analyzePhoto(file) {
    var formData = new FormData();
    formData.append("file", file);
    return fetch(API + "/photo/analyze", {
      method: "POST",
      body: formData,
    }).then(function (res) {
      if (!res.ok) throw new Error("Photo API error: " + res.status);
      return res.json();
    });
  }

  function handleChatResponse(data) {
    hideTyping();
    state.sessionId = data.session_id || state.sessionId;
    state.history = data.history || state.history;
    state.suggestedOptions = data.suggested_options || [];

    var answer = data.response || "";
    state.messages.push({ role: "bot", text: answer });
    addMessageToDOM("bot", renderBotMessage(answer));
    renderOptions(state.suggestedOptions);
    saveSession();
    state.isSending = false;
    updateSendButton();
  }

  function handleChatError(err) {
    hideTyping();
    var errText = "Sorry, I hit a snag. Please try again in a moment.";
    state.messages.push({ role: "bot", text: errText });
    addMessageToDOM("bot", simpleMarkdown(errText));
    state.suggestedOptions = [];
    renderOptions([]);
    saveSession();
    state.isSending = false;
    updateSendButton();
    console.error("MoxieBuddy error:", err);
  }

  /* ───────────────────────── Textarea auto-resize ───────────────────────── */

  function autoResizeTextarea(el) {
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 80) + "px";
  }

  function updateSendButton() {
    var btn = $("mb-send-btn");
    var input = $("mb-text-input");
    if (btn && input) {
      btn.disabled = state.isSending || !input.value.trim();
    }
  }

  /* ───────────────────────── Event wiring ───────────────────────── */

  function wireEvents() {
    // Toggle panel
    $("mb-bubble").addEventListener("click", function () {
      state.isOpen = !state.isOpen;
      $("mb-panel").classList.toggle("mb-open", state.isOpen);
      if (state.isOpen) {
        scrollToBottom();
        $("mb-text-input").focus();
      }
    });

    $("mb-close-btn").addEventListener("click", function () {
      state.isOpen = false;
      $("mb-panel").classList.remove("mb-open");
    });

    // Send on click
    $("mb-send-btn").addEventListener("click", function () {
      var text = $("mb-text-input").value.trim();
      if (text) sendMessage(text);
    });

    // Send on Enter (Shift+Enter = newline)
    $("mb-text-input").addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        var text = this.value.trim();
        if (text && !state.isSending) sendMessage(text);
      }
    });

    // Auto-resize textarea
    $("mb-text-input").addEventListener("input", function () {
      autoResizeTextarea(this);
      updateSendButton();
    });

    // Photo upload
    $("mb-photo-input").addEventListener("change", function () {
      var file = this.files && this.files[0];
      if (!file) return;
      // Create data URL for preview
      var reader = new FileReader();
      reader.onload = function (e) {
        var text = $("mb-text-input").value.trim();
        sendMessage(text, file, e.target.result);
      };
      reader.readAsDataURL(file);
      // Reset input so same file can be re-uploaded
      this.value = "";
    });

    // Close on Escape
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && state.isOpen) {
        state.isOpen = false;
        $("mb-panel").classList.remove("mb-open");
      }
    });
  }

  /* ───────────────────────── Welcome message on first open ───────────────────────── */

  function ensureWelcome() {
    if (state.messages.length === 0) {
      var welcome =
        "Hey there! I'm MoxieBuddy, your hair-care sidekick. " +
        "Tell me about your hair, ask about a product, or upload a photo and I'll help you figure out what works.";
      state.messages.push({ role: "bot", text: welcome });
      state.suggestedOptions = [
        "My hair is frizzy",
        "I need a routine",
        "I have a product question",
        "Upload a photo of my hair",
      ];
      saveSession();
    }
  }

  /* ───────────────────────── Init ───────────────────────── */

  function init() {
    buildWidget();
    ensureWelcome();
    restoreMessages();
    wireEvents();
  }

  // Wait for DOM
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
