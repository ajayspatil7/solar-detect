# Phase 2 Product Design QA

## Comparison inputs

- Selected source visual: `solar_defect_camera/design/phase2-soft-instrument-panel.png`
- Source dimensions: 1487 × 1058 pixels
- Implementation screenshot: `solar_defect_camera/design/phase2-implementation-final-empty.png`
- Implementation dimensions: 1425 × 1028 pixels at a 1440 × 1024 CSS viewport and 1× device pixel ratio
- Responsive screenshot: `solar_defect_camera/design/phase2-implementation-mobile.png`
- Responsive dimensions: 375 × 812 pixels from a 390 × 844 CSS viewport at 1× device pixel ratio
- Combined comparison: `solar_defect_camera/design/phase2-qa-comparison.png`
- Compared state: device online, live preview active, no image captured yet

## Full comparison

The source and implementation were placed side by side in the combined
comparison image and inspected together. The implementation retains the chosen
visual direction: warm off-white canvas, compact instrument header, dominant
live preview, right-side capture and analysis panels, pastel status accents,
quiet borders, and a bottom health strip.

The live-preview subject is intentionally different. The source visual uses a
representative solar-panel image, while the implementation shows the physical
ESP32-CAM feed. This is dynamic product content rather than a design mismatch.

## Focused checks

- Typography: passed. Avenir Next leads a robust local system-font stack with
  clear heading, label, metric, and helper-text hierarchy.
- Layout and spacing: passed. Desktop hierarchy matches the selected visual and
  the 390-pixel layout collapses to one readable column without horizontal
  overflow.
- Color and surfaces: passed. Sage, powder blue, apricot, and lavender accents
  remain restrained against warm neutral surfaces.
- Core workflow: passed. Capture, captured-image preview, retake, native JPEG
  download link, analysis eligibility, demo result, retry states, and health
  refresh are represented with explicit status feedback.
- Accessibility: passed. Semantic regions and headings, keyboard focus states,
  ARIA live status announcements, useful image alternatives, disabled states,
  and reduced-motion handling are present.
- Trust and safety: passed. The analysis is clearly marked Demo, images are
  described as temporary, and the interface avoids diagnostic certainty.

## Iteration history

1. The first implementation was taller and looser than the selected visual.
   Vertical spacing and card proportions were tightened.
2. The post-capture analysis prompt did not clearly change state. It was updated
   to explicitly say the image is ready for analysis.
3. The original programmatic download interaction was hard to observe in browser
   automation. It was replaced with a native anchor carrying a valid blob URL
   and timestamped `.jpg` download filename.
4. Desktop capture and retake were verified with real 640 × 480 JPEGs; the
   analysis result and preview reconnection were verified on the physical board.
5. The narrow layout was checked at 390 × 844 CSS pixels and showed no horizontal
   overflow. A transient stale MJPEG browser connection was cleared by releasing
   the old stream and resetting the board; the device health endpoint then
   returned normally.

## Residual low-priority notes

- The full desktop document can exceed the nominal viewport by a few pixels,
  depending on browser chrome and captured-result content. All primary controls
  remain visible and reachable.
- Browser automation did not expose a native download event, but the rendered
  control was verified to have both a blob URL and a valid JPEG filename.

## Final result

passed
