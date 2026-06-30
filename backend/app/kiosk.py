"""Kiosk mode for Flipkart brand events — full-screen quiz flow on iPads."""

import json
import logging

from app.db import get_pool
from app.recommendations import recommend_routine

logger = logging.getLogger(__name__)

CONCERN_MAP = {
    "definition": {"primary_concern": "curl_definition"},
    "frizz": {"primary_concern": "frizz_control", "has_frizz": True},
    "dryness": {"primary_concern": "damage_repair"},
    "dandruff": {"primary_concern": "general_care", "has_scalp_concern": True},
    "damage": {"primary_concern": "damage_repair", "is_chemically_treated": True},
}

FALLBACK_CONCERN = "general_care"


def build_routine(hair_analysis: dict, primary_concern: str) -> dict:
    hair_type = hair_analysis.get("hair_type", "2A")
    formation = hair_analysis.get("formation", "wavy")
    texture = hair_analysis.get("texture", "medium")
    frizz = hair_analysis.get("frizz", "none")

    concerns = [c.strip() for c in primary_concern.split(",") if c.strip()] if primary_concern else []
    first_concern = concerns[0] if concerns else FALLBACK_CONCERN
    overrides = CONCERN_MAP.get(first_concern, {})

    all_flags = {}
    is_unmapped = False
    for c in concerns:
        mapped = CONCERN_MAP.get(c)
        if mapped:
            all_flags.update(mapped)
        else:
            is_unmapped = True

    routine = recommend_routine(
        hair_type=hair_type,
        formation=formation,
        texture=texture,
        primary_concern=overrides.get("primary_concern", FALLBACK_CONCERN),
        has_frizz=all_flags.get("has_frizz", frizz in ("medium", "high")),
        is_chemically_treated=all_flags.get("is_chemically_treated", False),
        is_colored=False,
        has_scalp_concern=all_flags.get("has_scalp_concern", False),
    )

    if is_unmapped and not all_flags:
        routine["fallback"] = True
        routine["fallback_note"] = (
            "We've matched you with our signature Rinse & Shine routine based on your hair type. "
            "We're working on specialised products for your concern — stay tuned!"
        )

    return routine


_IMAGE_FIXES = {
    "https://cdn.shopify.com/s/files/1/0762/7862/8674/files/FFHS.jpg?v=1734962525":
        "https://cdn.shopify.com/s/files/1/0762/7862/8674/files/moxie-beauty-frizz-fighting-hair-serum.jpg?v=1779943192",
    "https://cdn.shopify.com/s/files/1/0762/7862/8674/files/HARS_1.webp?v=1747294851":
        "https://cdn.shopify.com/s/files/1/0762/7862/8674/files/moxie-beauty-hyaluronic-acid-repairing-shampoo.webp?v=1779775725",
    "https://cdn.shopify.com/s/files/1/0762/7862/8674/files/HARC_1.webp?v=1747294945":
        "https://cdn.shopify.com/s/files/1/0762/7862/8674/files/moxie-beauty-hyaluronic-acid-repairing-conditioner.webp?v=1779775760",
    "https://cdn.shopify.com/s/files/1/0762/7862/8674/files/HAHS_1.webp?v=1747295015":
        "https://cdn.shopify.com/s/files/1/0762/7862/8674/files/moxie-hyaluronic-acid-hair-serum.webp?v=1779775564",
}


async def ensure_sampler_column():
    pool = await get_pool()
    await pool.execute(
        "ALTER TABLE kiosk_sessions ADD COLUMN IF NOT EXISTS sampler_given BOOLEAN NOT NULL DEFAULT FALSE"
    )
    for old_url, new_url in _IMAGE_FIXES.items():
        await pool.execute(
            """
            UPDATE kiosk_sessions
            SET routine_steps = replace(routine_steps::text, $1, $2)::jsonb
            WHERE routine_steps::text LIKE '%' || $1 || '%'
            """,
            old_url,
            new_url,
        )


async def save_kiosk_session(
    user_name: str,
    phone: str,
    hair_analysis: dict,
    primary_concern: str,
    routine_name: str,
    routine_steps: list[dict],
    event_name: str = "flipkart_jun2026",
) -> str:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO kiosk_sessions (event_name, user_name, phone, hair_type, hair_analysis, primary_concern, routine_name, routine_steps)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8::jsonb)
        RETURNING id::text
        """,
        event_name,
        user_name,
        phone,
        hair_analysis.get("hair_type", "unknown"),
        json.dumps(hair_analysis),
        primary_concern,
        routine_name,
        json.dumps(routine_steps),
    )
    return row["id"]


async def list_pending_sessions(event_name: str = "flipkart_jun2026") -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT id::text, user_name, phone, hair_type, primary_concern,
               routine_name, routine_steps, created_at
        FROM kiosk_sessions
        WHERE event_name = $1 AND sampler_given = FALSE
        ORDER BY created_at DESC
        """,
        event_name,
    )
    return [
        {
            "id": r["id"],
            "user_name": r["user_name"],
            "phone": r["phone"],
            "hair_type": r["hair_type"],
            "primary_concern": r["primary_concern"],
            "routine_name": r["routine_name"],
            "routine_steps": json.loads(r["routine_steps"]) if isinstance(r["routine_steps"], str) else r["routine_steps"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


async def mark_sampler_given(session_id: str) -> bool:
    pool = await get_pool()
    result = await pool.execute(
        "UPDATE kiosk_sessions SET sampler_given = TRUE WHERE id = $1::uuid AND sampler_given = FALSE",
        session_id,
    )
    return result == "UPDATE 1"


KIOSK_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <title>Moxie Hair Quiz</title>
  <style>
    @font-face {
      font-family: 'Haskoy';
      src: url('/static/fonts/haskoy-variable.woff2') format('woff2');
      font-weight: 100 900;
      font-display: swap;
    }

    :root {
      --coral: #E8735A;
      --coral-dark: #D4604A;
      --cream: #FFF8F5;
      --charcoal: #2D2D2D;
      --warm-gray: #6B6B6B;
      --light-gray: #F0EDEB;
      --green: #7EC8B7;
      --green-dark: #5FB5A2;
    }

    * { margin: 0; padding: 0; box-sizing: border-box; -webkit-tap-highlight-color: transparent; }

    html, body {
      height: 100%; width: 100%;
      overflow: hidden;
      font-family: 'Haskoy', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: var(--cream);
      color: var(--charcoal);
      touch-action: manipulation;
      -webkit-user-select: none; user-select: none;
      background: #D8F34F;
    }

    .screen {
      position: absolute; inset: 0;
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      padding: 40px;
      opacity: 0; pointer-events: none;
      transition: opacity 0.4s ease;
    }
    .screen.active { opacity: 1; pointer-events: auto; }

    .logo { margin-bottom: 5vh; }
    .logo img { height: 40px; }
    .tagline { font-size: 15px; color: var(--warm-gray); margin-bottom: 48px; }

    h2 { font-size: 28px; font-weight: 700; margin-bottom: 12px; text-align: center; }
    .subtitle { font-size: 16px; color: var(--warm-gray); margin-bottom: 36px; text-align: center; max-width: 500px; }

    input[type="text"], input[type="tel"] {
      width: 100%; max-width: 420px;
      padding: 16px 20px; margin-bottom: 16px;
      border: 2px solid var(--light-gray); border-radius: 12px;
      font-size: 18px; background: #fff;
      outline: none; transition: border-color 0.2s;
      -webkit-user-select: text; user-select: text;
    }
    input:focus { border-color: var(--green); }

    .btn {
      display: inline-flex; align-items: center; justify-content: center;
      padding: 16px 48px; border: none; border-radius: 50px;
      font-size: 16px; font-weight: 600; cursor: pointer;
      transition: transform 0.15s, background 0.2s;
      min-width: 200px;
    }
    .btn:active { transform: scale(0.96); }
    .btn-coral { background: var(--green); color: #fff; }
    .btn-coral:hover { background: var(--green-dark); }
    .btn-coral:disabled { background: #ccc; cursor: not-allowed; }
    .btn-green { background: var(--green); color: #fff; }
    .btn-green:hover { background: var(--green-dark); }
    .btn-outline {
      background: var(--green); color: #fff;
      border: none; padding: 16px 48px; font-size: 16px;
    }

    /* Screen 1: Welcome */
    #screen-welcome .form-wrap { width: 100%; max-width: 420px; display: flex; flex-direction: column; align-items: center; }
    .form-card {
      background: rgba(255,255,255,0.92); border-radius: 24px;
      padding: 48px 40px 40px; width: 100%; max-width: 440px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.08);
      display: flex; flex-direction: column; align-items: center;
    }

    /* Screen 2: Photo */
    .camera-wrap {
      position: relative; width: 480px; height: 320px;
      border-radius: 20px; overflow: hidden;
      border: none; margin-bottom: 32px;
      background: #000;
    }
    .camera-wrap video {
      width: 100%; height: 100%; object-fit: cover;
      transform: scaleX(-1);
    }
    .camera-wrap img {
      width: 100%; height: 100%; object-fit: cover;
    }
    .privacy-note {
      font-size: 12px; color: var(--warm-gray); text-align: center;
      max-width: 400px; margin-top: 20px; line-height: 1.4;
    }
    .camera-controls { display: flex; gap: 16px; align-items: center; }
    .capture-btn {
      width: 72px; height: 72px; border-radius: 50%;
      border: 4px solid #333; background: #fff;
      cursor: pointer; position: relative;
      display: flex; align-items: center; justify-content: center;
    }
    .capture-btn::after {
      content: ''; width: 56px; height: 56px; border-radius: 50%;
      background: #333; display: block;
    }
    .capture-btn:active::after { background: #444; }

    /* Screen 3: Concern */
    .concern-grid {
      display: flex; flex-wrap: wrap; justify-content: center;
      gap: 12px; width: 100%; max-width: 560px; margin-bottom: 24px;
    }
    .concern-card {
      padding: 12px 24px; border: 2px solid var(--light-gray);
      border-radius: 50px; text-align: center; cursor: pointer;
      transition: all 0.2s; background: #fff;
      font-size: 15px; font-weight: 500;
    }
    .concern-card:active { transform: scale(0.96); }
    .concern-card.selected { border-color: var(--green); background: #EFF9F6; }

    /* Screen 4: Routine */
    .routine-card {
      background: rgba(255,255,255,0.92); border-radius: 24px;
      padding: 32px 28px 28px; width: 100%; max-width: 700px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.08);
      display: flex; flex-direction: column; align-items: center;
      overflow-y: auto; max-height: calc(100vh - 160px);
      -webkit-overflow-scrolling: touch;
    }
    .routine-name {
      font-size: 22px; font-weight: 700; color: var(--charcoal);
      text-align: center; margin-bottom: 24px;
    }
    .fallback-note {
      background: #FFF3E0; border-radius: 12px; padding: 14px 20px;
      font-size: 14px; color: #8D6E28; text-align: center;
      margin-bottom: 20px; line-height: 1.5; width: 100%;
    }
    .hair-badge {
      display: inline-block; background: var(--light-gray);
      padding: 6px 16px; border-radius: 20px;
      font-size: 14px; color: var(--warm-gray);
      margin-bottom: 20px;
    }
    .routine-steps-list { width: 100%; }
    .step-card {
      display: flex; align-items: center; gap: 20px;
      background: var(--light-gray); border-radius: 16px;
      padding: 16px 20px; margin-bottom: 12px;
    }
    .step-num {
      width: 36px; height: 36px; border-radius: 50%;
      background: var(--green); color: #fff;
      display: flex; align-items: center; justify-content: center;
      font-weight: 700; font-size: 16px; flex-shrink: 0;
    }
    .step-img {
      width: 64px; height: 64px; border-radius: 12px;
      object-fit: cover; flex-shrink: 0; background: #fff;
    }
    .step-info { flex: 1; min-width: 0; }
    .step-name { font-size: 15px; font-weight: 600; margin-bottom: 4px; color: var(--charcoal); }
    .step-why { font-size: 13px; color: var(--warm-gray); line-height: 1.4; }


    /* Screen 5: Thank You */
    .check-circle {
      width: 100px; height: 100px; border-radius: 50%;
      background: var(--green); color: #fff;
      display: flex; align-items: center; justify-content: center;
      font-size: 48px; margin-bottom: 32px;
    }
    .countdown { font-size: 14px; color: var(--warm-gray); margin-top: 24px; }

    /* Loading spinner */
    .spinner {
      width: 40px; height: 40px; border: 4px solid var(--light-gray);
      border-top-color: var(--green); border-radius: 50%;
      animation: spin 0.8s linear infinite; margin: 20px auto;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    .analyzing-text { font-size: 16px; color: var(--warm-gray); text-align: center; margin-top: 12px; }

    .error-toast {
      position: fixed; bottom: 40px; left: 50%; transform: translateX(-50%);
      background: #D32F2F; color: #fff; padding: 14px 28px;
      border-radius: 12px; font-size: 15px; z-index: 100;
      opacity: 0; transition: opacity 0.3s; pointer-events: none;
    }
    .error-toast.show { opacity: 1; }

  </style>
</head>
<body>

<div class="error-toast" id="error-toast"></div>

<!-- Screen 1: Welcome -->
<div class="screen active" id="screen-welcome">
  <div class="form-card">
    <div class="logo"><img src="/static/hairgpt-logo.png" alt="HairGPT"></div>
    <div class="tagline">Find your perfect hair routine in 60 seconds</div>
    <div class="form-wrap">
      <input type="text" id="inp-name" placeholder="Your name" autocomplete="off" autocapitalize="words">
      <input type="tel" id="inp-phone" placeholder="Phone number" autocomplete="off" maxlength="10" inputmode="numeric" pattern="[0-9]*">
      <div style="height:12px"></div>
      <button class="btn btn-coral" id="btn-start" onclick="goToPhoto()">Next</button>
    </div>
  </div>
</div>

<!-- Screen 2: Photo -->
<div class="screen" id="screen-photo">
  <h2>Let's see your hair!</h2>
  <div class="subtitle">Take a quick photo so we can identify your hair type</div>
  <div class="camera-wrap">
    <video id="cam-video" autoplay playsinline muted></video>
    <img id="cam-preview" style="display:none">
  </div>
  <div class="camera-controls" id="cam-controls">
    <button class="capture-btn" id="btn-capture" onclick="capturePhoto()"></button>
  </div>
  <div id="photo-actions" style="display:none">
    <div style="display:flex;gap:16px;margin-top:8px">
      <button class="btn btn-outline" onclick="retakePhoto()">Retake</button>
      <button class="btn btn-coral" onclick="analyzePhoto()">Use This Photo</button>
    </div>
  </div>
  <div id="photo-loading" style="display:none">
    <div class="spinner"></div>
    <div class="analyzing-text">Analyzing your hair...</div>
  </div>
  <div class="privacy-note">Your photo will not be saved or used for any other purpose — it is only used for hair analysis.</div>
</div>

<!-- Screen 3: Concern -->
<div class="screen" id="screen-concern">
  <h2>What's your top hair concern?</h2>
  <div class="subtitle" id="hair-type-label"></div>
  <div class="concern-grid">
    <div class="concern-card" data-concern="definition" onclick="selectConcern(this)">Defined Curls / Waves</div>
    <div class="concern-card" data-concern="frizz" onclick="selectConcern(this)">Frizz</div>
    <div class="concern-card" data-concern="dryness" onclick="selectConcern(this)">Dryness</div>
    <div class="concern-card" data-concern="dandruff" onclick="selectConcern(this)">Dandruff</div>
    <div class="concern-card" data-concern="damage" onclick="selectConcern(this)">Damage</div>
  </div>
  <input type="text" id="inp-concern" placeholder="Or type your concern here..." style="margin-bottom:24px" oninput="onConcernType(this)">
  <button class="btn btn-coral" id="btn-concern" disabled onclick="submitQuiz()">Get My Routine</button>
</div>

<!-- Screen 4: Routine -->
<div class="screen" id="screen-routine">
  <div class="routine-card">
    <h2>Your Moxie Routine</h2>
    <div class="hair-badge" id="routine-badge"></div>
    <div class="routine-name" id="routine-label"></div>
    <div class="fallback-note" id="fallback-note" style="display:none"></div>
    <div class="routine-steps-list" id="routine-steps"></div>
    <div style="height:16px"></div>
    <button class="btn btn-green" onclick="showThankYou()">Get Your Samples</button>
  </div>
</div>

<!-- Screen 5: Thank You -->
<div class="screen" id="screen-thankyou">
  <div class="check-circle">✓</div>
  <h2>You're all set!</h2>
  <div class="subtitle">Grab your Moxie samplers from our team. Enjoy the event!</div>
  <div class="countdown" id="countdown">Starting over in 5s...</div>
</div>

<canvas id="cam-canvas" style="display:none"></canvas>

<script>
const API = window.location.origin;
let state = { name:'', phone:'', hairAnalysis:null, concern:'', stream:null };

function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
}

function showError(msg) {
  const t = document.getElementById('error-toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 3500);
}

function goToPhoto() {
  const name = document.getElementById('inp-name').value.trim();
  const phone = document.getElementById('inp-phone').value.trim();
  if (!name) { showError('Please enter your name'); return; }
  if (!/^[6-9]\d{9}$/.test(phone)) { showError('Please enter a valid 10-digit phone number'); return; }
  state.name = name; state.phone = phone;
  showScreen('screen-photo');
  startCamera();
}

async function startCamera() {
  try {
    const s = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 640 } }
    });
    state.stream = s;
    const v = document.getElementById('cam-video');
    v.srcObject = s; v.style.display = 'block';
    document.getElementById('cam-preview').style.display = 'none';
    document.getElementById('cam-controls').style.display = 'flex';
    document.getElementById('photo-actions').style.display = 'none';
    document.getElementById('photo-loading').style.display = 'none';
  } catch(e) {
    showError('Camera access needed for hair analysis');
  }
}

function capturePhoto() {
  const v = document.getElementById('cam-video');
  const c = document.getElementById('cam-canvas');
  c.width = v.videoWidth; c.height = v.videoHeight;
  c.getContext('2d').drawImage(v, 0, 0);
  const img = document.getElementById('cam-preview');
  img.src = c.toDataURL('image/jpeg', 0.85);
  img.style.display = 'block';
  v.style.display = 'none';
  document.getElementById('cam-controls').style.display = 'none';
  document.getElementById('photo-actions').style.display = 'block';
}

function retakePhoto() {
  document.getElementById('cam-preview').style.display = 'none';
  document.getElementById('cam-video').style.display = 'block';
  document.getElementById('cam-controls').style.display = 'flex';
  document.getElementById('photo-actions').style.display = 'none';
}

async function analyzePhoto() {
  document.getElementById('photo-actions').style.display = 'none';
  document.getElementById('photo-loading').style.display = 'block';

  const c = document.getElementById('cam-canvas');
  const blob = await new Promise(r => c.toBlob(r, 'image/jpeg', 0.85));
  const form = new FormData();
  form.append('file', blob, 'hair.jpg');

  try {
    const resp = await fetch(API + '/photo/analyze?is_retry=true', { method: 'POST', body: form });
    if (!resp.ok) throw new Error('Analysis failed');
    const data = await resp.json();

    if (!data.classification.classifiable) {
      showError('Could not analyze hair — please retake your photo');
      document.getElementById('photo-loading').style.display = 'none';
      retakePhoto();
      return;
    }

    state.hairAnalysis = data.classification;
    stopCamera();

    const ht = data.classification.hair_type || '?';
    const form2 = data.classification.formation || '?';
    document.getElementById('hair-type-label').textContent =
      'Your hair type: ' + form2.charAt(0).toUpperCase() + form2.slice(1) + ' (' + ht + ')';
    showScreen('screen-concern');
  } catch(e) {
    showError('Something went wrong — please try again');
    document.getElementById('photo-loading').style.display = 'none';
    retakePhoto();
  }
}

function stopCamera() {
  if (state.stream) { state.stream.getTracks().forEach(t => t.stop()); state.stream = null; }
}

function selectConcern(el) {
  el.classList.toggle('selected');
  const selected = [...document.querySelectorAll('.concern-card.selected')].map(c => c.dataset.concern);
  state.concern = selected.join(',');
  if (selected.length) document.getElementById('inp-concern').value = '';
  document.getElementById('btn-concern').disabled = !state.concern;
}

function onConcernType(el) {
  if (el.value.trim()) {
    document.querySelectorAll('.concern-card').forEach(c => c.classList.remove('selected'));
    state.concern = el.value.trim();
    document.getElementById('btn-concern').disabled = false;
  } else {
    const selected = [...document.querySelectorAll('.concern-card.selected')].map(c => c.dataset.concern);
    state.concern = selected.join(',');
    document.getElementById('btn-concern').disabled = !state.concern;
  }
}

async function submitQuiz() {
  const btn = document.getElementById('btn-concern');
  btn.disabled = true; btn.textContent = 'Loading...';

  try {
    const resp = await fetch(API + '/kiosk/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: state.name,
        phone: state.phone,
        hair_analysis: state.hairAnalysis,
        primary_concern: state.concern,
      }),
    });
    if (!resp.ok) throw new Error('Submit failed');
    const data = await resp.json();
    renderRoutine(data);
    showScreen('screen-routine');
  } catch(e) {
    showError('Something went wrong — please try again');
  } finally {
    btn.disabled = false; btn.textContent = 'Get My Routine';
  }
}

function renderRoutine(data) {
  const ht = state.hairAnalysis.hair_type || '?';
  const form = state.hairAnalysis.formation || '?';
  document.getElementById('routine-badge').textContent =
    form.charAt(0).toUpperCase() + form.slice(1) + ' hair • Type ' + ht;
  document.getElementById('routine-label').textContent = data.routine.routine;

  const fnote = document.getElementById('fallback-note');
  if (data.routine.fallback && data.routine.fallback_note) {
    fnote.textContent = data.routine.fallback_note;
    fnote.style.display = 'block';
  } else {
    fnote.style.display = 'none';
  }

  const wrap = document.getElementById('routine-steps');
  wrap.innerHTML = '';
  data.routine.steps.forEach(s => {
    const card = document.createElement('div');
    card.className = 'step-card';
    card.innerHTML =
      '<div class="step-num">' + s.step + '</div>' +
      (s.image ? '<img class="step-img" src="' + s.image + '" alt="">' : '') +
      '<div class="step-info"><div class="step-name">' + s.name + '</div>' +
      '<div class="step-why">' + s.why + '</div></div>';
    wrap.appendChild(card);
  });
}

function showThankYou() {
  showScreen('screen-thankyou');
  let sec = 5;
  const cd = document.getElementById('countdown');
  const iv = setInterval(() => {
    sec--;
    cd.textContent = 'Starting over in ' + sec + 's...';
    if (sec <= 0) { clearInterval(iv); resetQuiz(); }
  }, 1000);
}

function resetQuiz() {
  state = { name:'', phone:'', hairAnalysis:null, concern:'', stream:null };
  document.getElementById('inp-name').value = '';
  document.getElementById('inp-phone').value = '';
  document.getElementById('inp-concern').value = '';
  document.querySelectorAll('.concern-card').forEach(c => c.classList.remove('selected'));
  document.getElementById('btn-concern').disabled = true;
  document.getElementById('routine-steps').innerHTML = '';
  document.getElementById('fallback-note').style.display = 'none';
  showScreen('screen-welcome');
}
</script>
</body>
</html>
"""

KIOSK_ADMIN_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Kiosk Admin — Sampler Tracker</title>
  <style>
    @font-face {
      font-family: 'Haskoy';
      src: url('/static/fonts/haskoy-variable.woff2') format('woff2');
      font-weight: 100 900;
      font-display: swap;
    }

    :root {
      --coral: #E8735A;
      --cream: #FFF8F5;
      --charcoal: #2D2D2D;
      --warm-gray: #6B6B6B;
      --light-gray: #F0EDEB;
      --green: #7EC8B7;
      --green-dark: #5FB5A2;
    }

    * { margin: 0; padding: 0; box-sizing: border-box; }

    html, body {
      min-height: 100%; width: 100%;
      font-family: 'Haskoy', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #D8F34F;
      color: var(--charcoal);
    }

    .admin-wrap {
      max-width: 800px; margin: 0 auto;
      padding: 32px 20px 60px;
    }

    .admin-header {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 28px;
    }
    .admin-header h1 { font-size: 24px; font-weight: 700; }
    .admin-header .count-badge {
      background: var(--charcoal); color: #D8F34F;
      padding: 6px 16px; border-radius: 20px;
      font-size: 14px; font-weight: 600;
    }

    .refresh-btn {
      background: var(--green); color: #fff; border: none;
      padding: 10px 24px; border-radius: 50px;
      font-size: 14px; font-weight: 600; cursor: pointer;
      transition: background 0.2s;
    }
    .refresh-btn:hover { background: var(--green-dark); }

    .empty-state {
      background: rgba(255,255,255,0.92); border-radius: 20px;
      padding: 60px 24px; text-align: center;
      box-shadow: 0 4px 24px rgba(0,0,0,0.08);
    }
    .empty-state .icon { font-size: 48px; margin-bottom: 16px; }
    .empty-state p { color: var(--warm-gray); font-size: 16px; }

    .session-card {
      background: rgba(255,255,255,0.92); border-radius: 20px;
      padding: 20px 24px; margin-bottom: 16px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.08);
      transition: opacity 0.4s ease, transform 0.4s ease;
    }
    .session-card.removing {
      opacity: 0; transform: translateX(60px);
    }

    .session-top {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 12px;
    }
    .session-name { font-size: 18px; font-weight: 700; }
    .session-phone { font-size: 14px; color: var(--warm-gray); margin-left: 8px; }
    .session-time { font-size: 13px; color: var(--warm-gray); }

    .session-meta {
      display: flex; flex-wrap: wrap; gap: 8px;
      margin-bottom: 14px;
    }
    .meta-pill {
      background: var(--light-gray); padding: 4px 12px;
      border-radius: 16px; font-size: 13px; color: var(--warm-gray);
    }

    .session-routine-label {
      font-size: 15px; font-weight: 600; color: var(--green-dark);
      margin-bottom: 10px;
    }

    .mini-steps {
      display: flex; flex-wrap: wrap; gap: 8px;
      margin-bottom: 16px;
    }
    .mini-step {
      display: flex; align-items: center; gap: 8px;
      background: var(--light-gray); border-radius: 12px;
      padding: 8px 12px; font-size: 13px;
    }
    .mini-step-img {
      width: 36px; height: 36px; border-radius: 8px;
      object-fit: cover; flex-shrink: 0; background: #fff;
    }
    .mini-step-name { font-weight: 500; }

    .done-btn {
      display: flex; align-items: center; gap: 8px;
      background: var(--green); color: #fff; border: none;
      padding: 12px 28px; border-radius: 50px;
      font-size: 14px; font-weight: 600; cursor: pointer;
      transition: background 0.2s, transform 0.15s;
      margin-left: auto;
    }
    .done-btn:hover { background: var(--green-dark); }
    .done-btn:active { transform: scale(0.96); }
    .done-btn:disabled { background: #ccc; cursor: not-allowed; }
    .done-btn .tick { font-size: 18px; }

    .toast {
      position: fixed; bottom: 32px; left: 50%; transform: translateX(-50%);
      background: var(--charcoal); color: #fff; padding: 12px 24px;
      border-radius: 12px; font-size: 14px; z-index: 100;
      opacity: 0; transition: opacity 0.3s; pointer-events: none;
    }
    .toast.show { opacity: 1; }
  </style>
</head>
<body>
<div class="admin-wrap">
  <div class="admin-header">
    <div>
      <h1>Sampler Tracker</h1>
    </div>
    <div style="display:flex;align-items:center;gap:12px">
      <span class="count-badge" id="count-badge">0 pending</span>
      <button class="refresh-btn" onclick="loadSessions()">Refresh</button>
    </div>
  </div>
  <div id="session-list"></div>
</div>
<div class="toast" id="toast"></div>

<script>
const API = window.location.origin;

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

function timeAgo(iso) {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return Math.floor(diff / 86400) + 'd ago';
}

async function loadSessions() {
  try {
    const resp = await fetch(API + '/kioskadmin/sessions');
    if (!resp.ok) throw new Error();
    const data = await resp.json();
    renderSessions(data.sessions);
  } catch(e) {
    showToast('Failed to load sessions');
  }
}

function renderSessions(sessions) {
  const wrap = document.getElementById('session-list');
  const badge = document.getElementById('count-badge');
  badge.textContent = sessions.length + ' pending';

  if (!sessions.length) {
    wrap.innerHTML =
      '<div class="empty-state">' +
      '<div class="icon">\\u2728</div>' +
      '<p>All samplers handed out — nice work!</p>' +
      '</div>';
    return;
  }

  wrap.innerHTML = '';
  sessions.forEach(s => {
    const card = document.createElement('div');
    card.className = 'session-card';
    card.id = 'card-' + s.id;

    let stepsHtml = '';
    if (s.routine_steps && s.routine_steps.length) {
      stepsHtml = '<div class="mini-steps">';
      s.routine_steps.forEach(st => {
        stepsHtml +=
          '<div class="mini-step">' +
          (st.image ? '<img class="mini-step-img" src="' + st.image + '" alt="">' : '') +
          '<span class="mini-step-name">' + (st.name || st.handle || '') + '</span>' +
          '</div>';
      });
      stepsHtml += '</div>';
    }

    card.innerHTML =
      '<div class="session-top">' +
        '<div><span class="session-name">' + s.user_name + '</span>' +
        '<span class="session-phone">' + s.phone + '</span></div>' +
        '<span class="session-time">' + timeAgo(s.created_at) + '</span>' +
      '</div>' +
      '<div class="session-meta">' +
        '<span class="meta-pill">Hair: ' + (s.hair_type || '?') + '</span>' +
        '<span class="meta-pill">Concern: ' + (s.primary_concern || '?') + '</span>' +
      '</div>' +
      '<div class="session-routine-label">' + (s.routine_name || 'Custom Routine') + '</div>' +
      stepsHtml +
      '<button class="done-btn" onclick="markDone(\\'' + s.id + '\\')">' +
        '<span class="tick">\\u2713</span> Sampler Given' +
      '</button>';

    wrap.appendChild(card);
  });
}

async function markDone(id) {
  const card = document.getElementById('card-' + id);
  const btn = card.querySelector('.done-btn');
  btn.disabled = true; btn.textContent = '...';

  try {
    const resp = await fetch(API + '/kioskadmin/mark-given', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: id }),
    });
    if (!resp.ok) throw new Error();

    card.classList.add('removing');
    setTimeout(() => {
      card.remove();
      const remaining = document.querySelectorAll('.session-card').length;
      document.getElementById('count-badge').textContent = remaining + ' pending';
      if (!remaining) {
        document.getElementById('session-list').innerHTML =
          '<div class="empty-state">' +
          '<div class="icon">\\u2728</div>' +
          '<p>All samplers handed out — nice work!</p>' +
          '</div>';
      }
    }, 400);
    showToast('Marked as given \\u2713');
  } catch(e) {
    btn.disabled = false; btn.innerHTML = '<span class="tick">\\u2713</span> Sampler Given';
    showToast('Failed — try again');
  }
}

loadSessions();
setInterval(loadSessions, 5000);
</script>
</body>
</html>
"""
