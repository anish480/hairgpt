# HairGPT — Design Language & Implementation Spec

> **Source:** Figma file `BXB0RktooAqWiU6HI8g6Ov` (Page 1: "final", "HAIRGPT", "HAIRGPT- Chat Page", "HAIRGPT- Upload Icon")
> **Target platform:** Mobile-first (393 × 852 viewport), embedded as Shopify Theme App Extension widget
> **Last updated:** 2026-06-16

---

## 1. Screens Overview

The design consists of **three core screens** plus a **product listing context screen**:

| # | Screen Name | Figma Node | Dimensions | Purpose |
|---|-------------|------------|------------|---------|
| 1 | **Home / Landing** | `61:161` (HAIRGPT) | 393 × 760 | Entry point — mascot, photo upload CTAs, suggested questions, message input |
| 2 | **Chat Conversation** | `61:78` (HAIRGPT- Chat Page) | 393 × 858 | Active chat — bot messages (left-aligned), user messages (right-aligned, bubbles), input bar |
| 3 | **Upload Popup** | `70:310` (HAIRGPT- Upload Icon) | 393 × 858 | Same as Chat, with a popup offering "Upload Files" and "Take Photo" |
| 4 | **Product Listing Context** | `1:755` (final) | 393 × 3702 | Moxie website PLP showing how HairGPT coexists with product grid — for reference only |

---

## 2. Color Palette

### Primary Colors

| Name | Hex | Usage |
|------|-----|-------|
| **Moxie Teal** | `#7EC8B7` | Primary accent — send button, camera icon fill, active tab highlight, CTA buttons |
| **Moxie Teal Light** | `#B5DDD3` | Secondary accent — upload/photo action button borders, light interactive elements |
| **Warm Yellow** | `#F5E6A3` | Background gradient warm tone (top of gradient), mascot accent |
| **Soft Green** | `#E8F5E9` | Background gradient cool tone (bottom of gradient), chat background lower area |
| **White** | `#FFFFFF` | Card backgrounds, input field background, bot message background |
| **Off-White** | `#FAFFF8` | Page background base tint |
| **Dark Text** | `#2D2D2D` | Primary body text |
| **Medium Gray** | `#9E9E9E` | Placeholder text ("Type a message..."), timestamps |
| **Light Gray** | `#E0E0E0` | Input field border, dividers |

### Background Gradient

The app background uses a **full-bleed gradient image** (`Background.jpg` from Drive) that transitions:
- **Top:** Warm yellow/cream (`~#FDF6D8`)
- **Middle:** Soft transition zone
- **Bottom:** Pale mint/green (`~#E8F5E9`)

This gradient image is applied as a **fixed background** behind all screens. UI elements float on top of it.

---

## 3. Typography

### Font Families

| Role | Font | Weight | Notes |
|------|------|--------|-------|
| **Logo / Brand** | Custom / Display font | Bold | The "HAIR·GPT" logotype uses a distinctive display typeface with a mid-dot separator. Delivered as `Logo.png` asset — render as image, not text. |
| **Body Text** | Haskoy stack | Regular (400) | `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif` |
| **Bot Messages** | Haskoy | Regular (400) | Left-aligned, dark text on transparent/white background |
| **User Messages** | Haskoy | Regular (400) | Right-aligned, dark text inside teal-tinted bubble |
| **Suggested Questions** | Haskoy | Regular (400) | Inside bordered cards |
| **Timestamps** | Haskoy | Regular (400) | Small, gray |
| **CTA Buttons** | Haskoy | Medium (500) | Inside bordered pill buttons |
| **Section Headers** | Haskoy | Semi-bold (600) | "Have questions like this? Ask us!" — teal colored |

### Type Scale

| Element | Size (px) | Line Height | Color | Notes |
|---------|-----------|-------------|-------|-------|
| Logo | — | — | — | Rendered as image asset, ~142px wide × ~30px tall |
| Section header ("Have questions...") | 18–20 | 1.4 | Moxie Teal `#7EC8B7` | Centered, friendly tone |
| Bot message text | 14 | 1.5 | `#2D2D2D` | Left-aligned, no bubble background |
| User message text | 13–14 | 1.5 | `#2D2D2D` | Inside rounded bubble |
| Suggested question text | 14 | 1.5 | `#666666` | Inside bordered card |
| Timestamp | 8–10 | 1.2 | `#9E9E9E` | Below messages, format "4:19 PM" |
| Input placeholder | 14 | 1.5 | `#9E9E9E` | "Type a message..." |
| Upload popup labels | 12 | 1.4 | `#2D2D2D` | "Upload Files" / "Take Photo" |

---

## 4. Spacing & Layout

### Global

| Property | Value |
|----------|-------|
| Viewport width | 393px (mobile-first) |
| Horizontal padding (page) | 20–26px |
| Background | Full-bleed gradient image (fixed) |

### Home Screen Layout (top → bottom)

| Section | Top Offset (approx) | Height | Details |
|---------|---------------------|--------|---------|
| Logo | ~60px from top | ~42px | Centered horizontally, rendered as `Logo.png` |
| Mascot illustration | ~150px from top | ~140px | Centered, rendered as `Mascot.png` |
| Action buttons row | ~360px from top | ~50px | Two pill buttons side-by-side: "Upload a photo" + "Take a photo" |
| Section header | ~460px from top | ~40px | "Have questions like this? Ask us!" — centered, teal |
| Suggested questions | ~520px from top | ~160px | 3 stacked bordered cards |
| Message input bar | Bottom-fixed | ~50px | Input field + camera icon + send button |

### Chat Screen Layout

| Section | Position | Details |
|---------|----------|---------|
| Header bar | Fixed top, 0–84px | Dark overlay on gradient, back arrow (left), Logo (center) |
| Chat messages area | 84px → 770px | Scrollable, full width with 20–26px padding |
| Message input bar | Fixed bottom, ~783–820px | Input field + camera icon + send button |

### Message Bubbles

| Type | Alignment | Background | Border Radius | Max Width | Padding |
|------|-----------|------------|---------------|-----------|---------|
| **Bot message** | Left-aligned | Transparent (no bubble) | — | ~348px (full width minus padding) | 0 |
| **User message** | Right-aligned | `#F0F0F0` / light gray | 12–16px (all corners) | ~230px | 12–16px |
| **Timestamp** | Below message, same alignment | — | — | — | 0, margin-top: 4px |

---

## 5. Components

### 5.1 Header Bar (Chat Screens)

```
┌─────────────────────────────────────────┐
│  [←]          HAIR·GPT logo             │  height: 84px
│  back                                   │  bg: semi-transparent dark overlay
└─────────────────────────────────────────┘
```

- **Back arrow:** Left-aligned, ~20px from left, Moxie Teal circle background (`#7EC8B7`), white `<` chevron inside
- **Logo:** Centered, `Logo.png` rendered as image, ~142×30px
- **Background:** Rectangle overlay with slight opacity over the gradient

### 5.2 Message Input Bar

```
┌─────────────────────────────────────────┐
│ ┌─────────────────────────┐  [📷] [▶]  │
│ │ Type a message...       │             │  height: ~37px input + padding
│ └─────────────────────────┘             │
└─────────────────────────────────────────┘
```

- **Input field:** Rounded rectangle, `border-radius: 18px`, white/light background, `#E0E0E0` border
- **Camera icon:** `#7EC8B7` teal circle, ~27px diameter, camera icon inside (white)
- **Send button:** `#7EC8B7` teal circle, ~27px diameter, paper-plane/arrow icon inside (white)
- **Layout:** Input takes remaining width, icons on right with ~4px gap between them
- **Position:** Fixed to bottom of viewport

### 5.3 Upload Popup (appears above input bar)

```
┌──────────────────────────────┐
│  Upload Files  │  Take Photo │  height: ~25px
└──────────────────────────────┘
```

- **Container:** Small rounded pill, `border-radius: 12px`, white background, subtle shadow
- **Position:** Floats above the input bar, right-aligned (~169px from left)
- **Divider:** Vertical line between the two options
- **"Take Photo"** includes a small camera icon to its left
- **Width:** ~152px total
- **Trigger:** Tapping the camera icon in the input bar

### 5.4 Suggested Question Cards (Home Screen)

```
┌─────────────────────────────────────┐
│  What is my hair type?              │  height: ~38px
└─────────────────────────────────────┘
```

- **Border:** 1px solid `#E0E0E0`
- **Border radius:** 8–12px
- **Background:** White / very slight transparency
- **Text:** 14px, `#666666`, left-aligned with ~12px padding
- **Left accent:** Subtle left border or left-padding emphasis (2–3px teal left border)
- **Spacing between cards:** ~8–12px
- **Example questions:**
  1. "What is my hair type?"
  2. "What should I use for dandruff?"
  3. "What's the difference between Curl Cream and Serum Gel?"

### 5.5 Action Buttons (Home Screen)

```
┌──────────────────┐  ┌──────────────────┐
│  Upload a photo  │  │  Take a photo    │
│      [icon]      │  │     [📷]         │
└──────────────────┘  └──────────────────┘
```

- **Layout:** Two buttons side-by-side, equal width, ~8px gap
- **Border:** 1px solid `#E0E0E0`
- **Border radius:** 12px
- **Background:** White / slight transparency
- **Text:** 14px, `#2D2D2D`, centered
- **Icon:** Below text, small teal-colored icon (upload icon / camera icon)
- **Height:** ~50px each
- **The upload icon** is a teal-filled circle with a folder/upload symbol
- **The camera icon** is a teal-outlined camera

### 5.6 Bot Message

```
Can you tell me more about your hair texture?
4:19 PM
```

- **No bubble/background** — text renders directly on the gradient background
- **Full width** (minus page padding)
- **Font:** 14px, `#2D2D2D`
- **Timestamp:** Below, 8–10px, `#9E9E9E`

### 5.7 User Message

```
                    ┌─────────────────────────┐
                    │ My hair is frizzy with   │
                    │ dry ends. I think I have │
                    │ 3B hair type             │
                    └─────────────────────────┘
                                       4:19 PM
```

- **Right-aligned**
- **Bubble background:** `#F0F0F0` (light gray)
- **Border radius:** 12–16px all corners
- **Max width:** ~230px
- **Padding:** 12–16px
- **Font:** 13–14px, `#2D2D2D`
- **Timestamp:** Below-right, 8–10px, `#9E9E9E`

---

## 6. Iconography

| Icon | Usage | Style | Asset |
|------|-------|-------|-------|
| **Back arrow** | Chat header, top-left | White `<` chevron inside Moxie Teal circle (~29×27px) | SVG or CSS |
| **Camera** | Input bar, upload popup | White camera outline inside Moxie Teal circle (~24×26px) | `Icon.png` or SVG |
| **Send / Paper plane** | Input bar, right-most | White arrow/plane inside Moxie Teal circle (~20×20px) | SVG or CSS |
| **Upload / Folder** | Upload popup, home screen | Small folder icon, teal | SVG |
| **Mascot** | Home screen, centered | Duck-character illustration | `Mascot.png` |
| **Logo** | Home screen + chat header | "HAIR·GPT" display logotype | `Logo.png` |

---

## 7. Assets Required

| Asset | Source | Format | Usage |
|-------|--------|--------|-------|
| `background.png` | hairgpt/design/other_assets | PNG, 147KB | Full-bleed app background gradient |
| `bot_logo.png` | hairgpt/design/other_assets | PNG, 3KB | Brand logotype for header + home screen |
| `mascot.png` | hairgpt/design/other_assets | PNG, 5KB | Mascot illustration on home screen |
| `send.svg` | hairgpt/design/icons | SVG | Button for sending typed messages
| `back.svg` | hairgpt/design/icons | SVG | Back button in the chat UI for exiting the chat interface
| `upload.svg` | hairgpt/design/icons | SVG | Button for image upload option from local, triggers hair analysis post-upload
| `camera.svg` | hairgpt/design/icons | SVG | Button for image capture utility, triggers hair analysis post-capture
| `folder_popup.svg` | hairgpt/design/icons | SVG | Button for image upload option from local after chat has started, triggers hair analysis post-upload
| `camera_popup.svg` | hairgpt/design/icons | SVG | Button for image capture utility after chat has started, triggers hair analysis post-capture 

> **Note:** All assets are on the local disk, in the hairgpt project folder, directory addresses are mentioned above

---

## 8. Interaction & Animation Notes

### Screen Transitions
- **Home → Chat:** Slide-in from right, or fade transition
- **Chat → Home (back):** Slide-out to right via back arrow

### Upload Popup
- **Trigger:** Tapping camera icon in message input bar
- **Appearance:** Small popover appears directly above the input bar
- **Dismiss:** Tap outside the popup, or after selecting an option
- **Options:** "Upload Files" (opens file picker) | "Take Photo" (opens device camera)

### Suggested Questions (Home Screen)
- **Tap behavior:** Tapping a question card sends it as the user's first message, transitioning to the Chat screen
- **Visual feedback:** Slight press/scale animation on tap

### Message Input
- **Send button:** Enabled (full opacity) only when input is non-empty; disabled (reduced opacity) otherwise
- **Enter key:** Sends message on mobile keyboard "Send" action

### Chat Scroll
- **New messages:** Auto-scroll to bottom when new messages arrive
- **User scroll:** Allow free scrolling through history; pause auto-scroll if user has scrolled up

---

## 9. Responsive Considerations

The design is **mobile-first at 393px width**. For the Shopify widget implementation:

- The chat widget should render as a **fixed-position overlay** or **slide-in panel** on the Moxie website
- On mobile: Full-screen takeover (393px viewport)
- On desktop: Right-side panel, max-width ~400px, with slight shadow/elevation
- The background gradient image should be `background-size: cover; background-position: center;`
- All measurements in this spec are for the 393px mobile viewport; scale proportionally for other sizes

---

## 10. Figma Reference Quick-Links

- **Full Figma file:** https://www.figma.com/design/BXB0RktooAqWiU6HI8g6Ov/HairGPT?node-id=0-1
- **Home Screen node:** `61:161`
- **Chat Screen node:** `61:78`
- **Upload Popup Screen node:** `70:310`
- **Product listing context node:** `1:755`

---

## 11. Implementation Checklist for Claude Code

- [ ] Set up mobile-first viewport (393px base)
- [ ] Implement background gradient using `Background.jpg`
- [ ] Build Home screen with Logo, Mascot, action buttons, suggested questions, input bar
- [ ] Build Chat screen with header (back + logo), message list, input bar
- [ ] Implement bot messages (left, no bubble) and user messages (right, gray bubble)
- [ ] Implement timestamps below each message
- [ ] Build upload popup component (triggered by camera icon)
- [ ] Wire suggested question cards to send first message
- [ ] Implement auto-scroll behavior for chat
- [ ] Add send button enable/disable state
- [ ] Use the exact color palette from Section 2
- [ ] Use system font stack for all text
- [ ] Render Logo.png and Mascot.png as image assets (not text)
- [ ] Ensure fixed positioning for header and input bars
