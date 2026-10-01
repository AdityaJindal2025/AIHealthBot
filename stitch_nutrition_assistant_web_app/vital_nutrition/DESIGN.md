---
name: Vital Nutrition
colors:
  surface: '#edfef1'
  surface-dim: '#ceded2'
  surface-bright: '#edfef1'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#e7f8eb'
  surface-container: '#e1f2e5'
  surface-container-high: '#dcece0'
  surface-container-highest: '#d6e7da'
  on-surface: '#111e17'
  on-surface-variant: '#3f493f'
  inverse-surface: '#25342b'
  inverse-on-surface: '#e4f5e8'
  outline: '#6f7a6e'
  outline-variant: '#becabc'
  surface-tint: '#006d30'
  primary: '#00652c'
  on-primary: '#ffffff'
  primary-container: '#15803d'
  on-primary-container: '#d3ffd5'
  inverse-primary: '#79db8d'
  secondary: '#9d4300'
  on-secondary: '#ffffff'
  secondary-container: '#fd761a'
  on-secondary-container: '#5c2400'
  tertiary: '#415d4d'
  on-tertiary: '#ffffff'
  tertiary-container: '#597665'
  on-tertiary-container: '#dcfce7'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#95f8a7'
  primary-fixed-dim: '#79db8d'
  on-primary-fixed: '#00210a'
  on-primary-fixed-variant: '#005323'
  secondary-fixed: '#ffdbca'
  secondary-fixed-dim: '#ffb690'
  on-secondary-fixed: '#341100'
  on-secondary-fixed-variant: '#783200'
  tertiary-fixed: '#caead6'
  tertiary-fixed-dim: '#afceba'
  on-tertiary-fixed: '#042014'
  on-tertiary-fixed-variant: '#314d3e'
  background: '#edfef1'
  on-background: '#111e17'
  surface-variant: '#d6e7da'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 2.5rem
    fontWeight: '700'
    lineHeight: 3rem
    letterSpacing: -0.025em
  headline-lg:
    fontFamily: Inter
    fontSize: 2rem
    fontWeight: '600'
    lineHeight: 2.5rem
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 1.5rem
    fontWeight: '600'
    lineHeight: 2rem
    letterSpacing: -0.015em
  headline-sm:
    fontFamily: Inter
    fontSize: 1.25rem
    fontWeight: '600'
    lineHeight: 1.75rem
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Inter
    fontSize: 1.125rem
    fontWeight: '400'
    lineHeight: 1.8rem
  body-md:
    fontFamily: Inter
    fontSize: 1rem
    fontWeight: '400'
    lineHeight: 1.6rem
  body-sm:
    fontFamily: Inter
    fontSize: 0.875rem
    fontWeight: '400'
    lineHeight: 1.45rem
  label-lg:
    fontFamily: Inter
    fontSize: 0.9375rem
    fontWeight: '600'
    lineHeight: 1.25rem
    letterSpacing: 0.01em
  label-md:
    fontFamily: Inter
    fontSize: 0.8125rem
    fontWeight: '600'
    lineHeight: 1.125rem
    letterSpacing: 0.02em
  label-sm:
    fontFamily: Inter
    fontSize: 0.75rem
    fontWeight: '500'
    lineHeight: 1rem
    letterSpacing: 0.03em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1.5rem
  gutter-mobile: 1rem
  margin: 2rem
  margin-mobile: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.5rem
---

## Brand & Style

This design system establishes an evidence-based, compassionate digital sanctuary for nutrition, balanced meal composition, and kitchen food safety. It rejects punitive health metrics, calorie obsession, body monitoring, and rigid clinical austerity. Instead, the visual language draws vitality from morning sunlight, crisp market produce, regenerative habits, and clear scientific guidance.

The design movement combines **Modern Functionalism** with **Organic Wellness**:
- **Optimistic Utility:** Interface elements communicate clarity, confidence, and reassurance through balanced structural lines and soft environmental tints.
- **Supportive Humanity:** Guidance emphasizes nourishment and food safety without alarmist friction or moralizing language.
- **Tactile Freshness:** Generous negative space, soft ambient daylight shadows, and crisp organic borders frame actionable guidance in a clean, daylight-driven space.

## Colors

The palette establishes an immediate sensation of living vitality and credible safety.

- **Primary (`#15803D`):** Fresh leafy botanical green. Used for authoritative actions, confirmed verification markers, safe temperature checkpoints, and core navigational balance.
  - Hover state: `#166534`
  - Active / Pressed state: `#14532D`
  - Subtle Tint / Soft surface: `#DCFCE7`
- **Secondary / Accent (`#F97316`):** Energetic citrus orange. Drives active interactive highlights, calls attention to key dietary nutrients, and powers high-visibility accessibility rings.
  - Deep Accent Text / Contrast: `#C2410C`
- **Neutral Canvas & Tiers:**
  - Canvas App Background: `#F6FAF4` (calming herbal off-white)
  - Card & Panel Surface: `#FFFFFF`
  - Border Substrate: `#E3EAE0`
  - Primary Text (Neutral High): `#1C2A22` (deep evergreen charcoal for optimal reading comfort)
  - Secondary Text (Neutral Medium): `#5B6B61`
  - Muted Label / Subtle Text (Neutral Light): `#8D9E94`
- **Status & Food Safety Badges:**
  - Safe / Verified: Background `#DCFCE7`, Text `#15803D`
  - Attention / Critical Alert: Background `#FFEDD5`, Text `#C2410C`
  - Unverified / Neutral Status: Background `#ECEFEA`, Text `#3F4A43`

## Typography

The type system is powered entirely by `Inter` across all structural layers to maximize legibility and neutral clarity.

- **Headings:** Set with tight, intentional letter spacing and solid structural weights (`600` and `700`) to present nutritional breakdowns with authority and clarity.
- **Body:** Standardized on a `1rem` (16px) base with an open `1.6` line-height multiplier. Extended dietary notes, recipe descriptions, and food preservation protocols rely on this vertical air to prevent reading fatigue.
- **Labels & Micro-Metrics:** Rendered at `500` or `600` weight with positive letter spacing to maintain crisp legibility on small food safety tags, ingredient listings, and nutrient tables.

## Layout & Spacing

The web app employs a responsive 12-column grid designed for modular desktop multi-tasking (e.g., viewing an ingredient analysis panel beside safety thresholds).

- **Grid Architecture:** 12-column fluid grid constrained to a maximum content width of `1440px`. Column gutters rest at `1.5rem` (`24px`), with outer screen margins anchored at `2rem` (`32px`) to ensure the content never touches screen edges.
- **Spacial Rhythm:** Built upon an 8px base rhythm (`0.5rem`). Micro elements use `4px` (`0.25rem`) offsets, while internal card padding relies systematically on `1.5rem` (`space-lg`) to maintain a clean, airy roominess.
- **Form Factor Adaptations:**
  - **Desktop (1024px+):** Multi-pane split layouts; persistent nutrition summary sidebar paired with expansive recipe and ingredient workflows.
  - **Tablet (768px - 1023px):** 8-column layout, collateral panels collapse into slide-over sheets; gutter scales to `1.25rem`.
  - **Mobile (< 768px):** 4-column layout, margins compress to `1rem`, multi-step nutrition intake and safety steps transition to linear stacks.

## Elevation & Depth

This design system avoids harsh artificial dropshadows, relying instead on ambient, organic daylight diffusion combined with low-contrast structural outlines.

- **Level 0 (Flat Canvas):** `#F6FAF4` base background layer. Displays zero elevation.
- **Level 1 (Card & Module Resting):** Surface `#FFFFFF`, framed with a precise 1px stroke of `#E3EAE0`. Elevation is suggested with a soft leafy ambient shadow: `box-shadow: 0 2px 8px -2px rgba(28, 42, 34, 0.04), 0 1px 3px -1px rgba(28, 42, 34, 0.02)`.
- **Level 2 (Hover & Active Interactive Cards):** Smoothly transitions on cursor proximity to: `box-shadow: 0 10px 20px -4px rgba(28, 42, 34, 0.06), 0 4px 6px -2px rgba(28, 42, 34, 0.03)`.
- **Level 3 (Modals, Safety Alerts & Overlays):** Float above backdrops with high diffusion: `box-shadow: 0 20px 32px -8px rgba(28, 42, 34, 0.12), 0 8px 12px -4px rgba(28, 42, 34, 0.04)`.

## Shapes

The interface embraces organic curvature without feeling juvenile or overly bubbly. 

- **Primary Geometry:** Base elements (inputs, standard cards, and buttons) utilize a 12px (`0.75rem`) to 16px (`1rem`) corner radius, reflecting `roundedness: 2`.
- **Container Panels:** Large macro cards and modal windows employ `1rem` to `1.5rem` (`rounded-xl`) radii.
- **Tags & Status Badges:** Formed as continuous full pills (`rounded-full` / `9999px`) to visually separate metadata, pantry storage flags, and nutritional metrics from actionable block components.

## Components

### Buttons
- **Primary:** Filled `#15803D` with text `#FFFFFF`, 12px corner radius, padding `0.75rem 1.5rem`. Hover `#166534`, Active `#14532D`.
- **Secondary:** Surface `#FFFFFF`, border 1px solid `#E3EAE0`, text `#1C2A22`. Hover `#F6FAF4` with border `#15803D`.
- **Accent Action:** Filled `#F97316` with text `#FFFFFF` for primary food safety flags or culinary timers. Hover `#EA580C`.
- **Focus Rings:** All buttons use an explicit, accessible 2px offset ring: `outline: 2px solid #F97316; outline-offset: 2px`.

### Badges & Pill Chips
- **Pill Geometry:** Height 28px, full pill border radius (`9999px`), padding `0.25rem 0.75rem`, font `label-sm`.
- **Verified Safe Badge:** Background `#DCFCE7`, text `#15803D`, optional leading green checkmark.
- **Unverified / Raw Badge:** Background `#ECEFEA`, text `#3F4A43`.
- **Citrus Attention Badge:** Background `#FFEDD5`, text `#C2410C`.

### Cards & Panels
- Resting on `#FFFFFF` surface with 1px border `#E3EAE0` and 16px (`1rem`) border radius.
- Padding: `1.5rem` uniform spacing.
- Subdivided content blocks inside cards use a `#E3EAE0` divider line or a soft `#F6FAF4` inset container.

### Input Fields & Controls
- **Form Inputs:** 44px touch-friendly height, border 1px solid `#E3EAE0`, background `#FFFFFF`, text `#1C2A22`, placeholder `#8D9E94`.
- **Input Focus:** Border color transitions to `#15803D` with a sharp focus ring in `#F97316` (`2px`).
- **Checkboxes & Radios:** 20px size, 4px rounded radius for checkboxes, full circle for radios. Active filled with `#15803D`.

### Nutrition Assistant Domain Components
- **Macro Balance Meter:** Multi-segment horizontal bar depicting complex carbs, healthy proteins, and unsaturated fats using muted vegetal hues without reference to caloric restriction or punishment.
- **Food Safety Indicator Card:** Prominent storage duration card featuring safe internal cooking temperatures, cross-contamination guidance, and shelf-life countdowns with explicit `#15803D` (Safe) or `#C2410C` (Consume Immediately) pill tags.