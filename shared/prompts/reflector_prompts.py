"""
Reflector Agent Prompts

Implements: Directional Stimulus Prompting
Purpose: Guide LLM attention to relevant aspects, ignore irrelevant differences
"""

# Directional Stimulus for intermediate step verification
# Guides what to IGNORE vs FOCUS on during validity checks
DIRECTIONAL_STIMULUS = """
EVALUATION CRITERIA (Directional Stimulus):

IGNORE these differences (do not penalize):
- System-level indicators: clock time, battery percentage, wifi signal strength, notification icons
- Minor visual artifacts: anti-aliasing, sub-pixel rendering, font smoothing differences
- Scroll position variations if all content is present
- Color/brightness variations from screenshot compression
- Status bar elements that vary by device state

FOCUS on these aspects (critical for correctness):
- Structural layout of UI elements
- Text content in primary fields and labels
- Presence/absence of required interactive elements
- Screen transitions (new screen vs same screen)
- Error messages or loading states
- Core user-visible state changes
"""

# Directional Stimulus specifically for final step verification
# Stronger guidance when comparing against Figma Gold Standard
FINAL_STEP_STIMULUS = """
CRITICAL FINAL VERIFICATION (3-WAY MATCH REQUIRED):
You must perform a comprehensive 3-way verification comparing:
1. The LIVE APP SCREENSHOT (what the app currently shows)
2. The ULTIMATE EXPECTED RESULT (textual description of success)
3. The FIGMA GOLD STANDARD (design reference image)

DIRECTIONAL STIMULUS FOR FINAL VERIFICATION:

STRICTLY IGNORE (these are NOT failures):
- Status bar differences: time display, battery icon, network signal strength
- Device-specific UI chrome: navigation bar style, system fonts
- Minor rendering differences: anti-aliasing, shadow softness, corner radius
- Slight color variations from different color spaces or compression
- Scroll position if all required content is visible
- Empty space distribution if layout structure matches

CRITICALLY FOCUS ON (these ARE failures if mismatched):
- Core UI elements: Are all expected buttons, fields, and labels present?
- Text content accuracy: Do primary text fields match exactly?
- Layout structure: Is element positioning and hierarchy correct?
- Missing elements: Are any required components absent?
- Extra elements: Are there unexpected popups, errors, or overlays?
- Functional state: Are interactive elements in correct enabled/disabled state?

VERDICT GUIDANCE:
- PASS: Core functionality and layout match; minor visual differences acceptable
- FAIL: Missing core elements, incorrect text, wrong screen, or structural mismatch
"""

# Additional stimuli for specific check types
LOADING_STIMULUS = """
DIRECTIONAL STIMULUS FOR LOADING CHECK:

IGNORE:
- Static content that is fully rendered
- UI elements that are stable and complete

FOCUS ON:
- Animated spinners or circular progress indicators
- Linear progress bars
- Skeleton screens (grey placeholder shapes)
- Shimmer/pulse animations
- Partially rendered lists where items appear one-by-one
- Blank content areas that should have data
"""

UI_CHANGE_STIMULUS = """
DIRECTIONAL STIMULUS FOR UI CHANGE CHECK:

IGNORE:
- System-level changes: clock, battery, notifications, signal bars
- Screenshot timestamp differences
- Minor pixel noise or compression artifacts

FOCUS ON:
- New screens or views that appeared
- New content, list items, or elements becoming visible
- Form fields being filled with text
- Button state changes (enabled/disabled)
- Dialogs, modals, or popups appearing
- Navigation transitions between screens
- Content that was previously hidden now visible
"""
