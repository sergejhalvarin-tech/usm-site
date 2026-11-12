**Comparison target**

- Source visual truth: `C:\Users\FS\Documents\ChatGPT\Логистика\.prototype-assets\kiln\view1-15s.jpg` (848 × 464 px). This is a user-supplied video frame showing the actual CAD model of the kiln; it is used as the product-image source, not as a copied site layout.
- Implementation: browser-rendered prototype at `http://127.0.0.1:4173/`, in-app Browser tab 2, captured at the desktop browser's current 1264 × 710 CSS-px viewport. Browser capture was inspected in the current QA run; browser tooling does not expose a writable screenshot path.
- State: initial desktop hero, then `40+ т/мес` selected and lead modal opened.
- Density normalization: source was cropped and upscaled only for display (`public/assets/kiln/hero-cad.jpg`, 1600 px wide); the design review is based on subject, crop and hierarchy rather than a pixel-for-pixel UI recreation, because no source UI mock exists.

**Full-view comparison evidence**

The source provides a gray industrial CAD model with two chambers, chimneys, yellow handling hardware and a frontal perspective. The implementation retains that exact product geometry in the right-hand hero, crops away the editor interface, and pairs it with a deliberately new light engineering layout. This is intentional design direction, not visual drift from a supplied web mock.

Focused comparison was needed only for the hero product asset. The front-on chamber layout, stack placement and yellow mechanisms remain recognisable. The product is legible at the hero scale and does not function as a placeholder.

**Findings**

- [P3] CAD footage limits product-image polish.
  Location: hero and construction imagery.
  Evidence: the source is a camera recording of a monitor, so it has moiré, a soft edge and lower contrast than a direct CAD render.
  Impact: it is fully adequate for this prototype but would reduce the premium impression on a production site.
  Fix: export three direct 16:9 PNG/WebP renders from the original CAD software or Blender, with a neutral studio background and no editor UI.

**Required fidelity surfaces**

- Fonts and typography: intentionally new sans-serif editorial hierarchy; 48–82 px responsive display headline, 11–13 px monospaced technical labels, no truncation at the reviewed desktop viewport.
- Spacing and layout rhythm: two-column hero has substantial negative space; 64 px desktop shell gutter; section dividers and 80–130 px section rhythm are consistent.
- Colors and visual tokens: `#f2f0e8` mineral paper, `#17201d` graphite, `#d6552c` copper CTA and restrained green metadata create a separate identity from the competitor's black/orange approach.
- Image quality and asset fidelity: uses cropped user-supplied CAD frames, not placeholders or reconstructed CSS art. P3 direct-render replacement noted above.
- Copy and content: all copy is prototype-specific and describes configurable charcoal-production equipment; no competitor text or branding was retained.

**Primary interaction checks**

- Capacity selector updated the visible selected state to `40+ т/мес`.
- `Подобрать комплектацию` opened the lead modal with the correct heading.
- Browser console returned no errors.
- The form has a local success state and makes no external submission.

**3D model update verification**

- Source asset: `public/assets/kiln/kotel.gltf` plus `kotel.bin` and three referenced texture files, copied from the owner's existing Urman site model source.
- Runtime: Google Model Viewer is loaded as an ES module and renders the local `kotel.gltf` asset inside the hero.
- Browser-rendered evidence: the desktop in-app Browser showed the complete black/red two-chamber kiln with its chimneys and side mechanisms in the interactive hero. The visual label changed to `3D / ИНТЕРАКТИВНАЯ МОДЕЛЬ` and the model control exposes a user-operable canvas/poster control.
- Build and Sites packaging tests passed after the model was added.

**Comparison history**

1. Initial review: no P0/P1/P2 differences because the user supplied product imagery, not a UI mock to reproduce. The UI was assessed against the approved direction: a light, engineering-led independent identity using that model.
2. Post-check: desktop hierarchy, CTA visibility, asset crop, selector state and modal were verified. P3 direct-render improvement remains non-blocking.

**Implementation checklist**

1. Replace the three CAD-video crops with direct renders when available.
2. Replace the prototype brand and indicative copy/specifications with verified company data.
3. Connect the local lead form to the chosen CRM only after the production requirements are agreed.

**Follow-up polish**

- Add an interactive 360° model only from an original CAD/Blender export, not from monitor-recorded footage.
- Prepare a mobile-specific crop for the hero render.

final result: passed
