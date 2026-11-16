# Clavius landing page

The landing lives at `/`; the existing lunar explorer lives at `/app`.

## Visual target

Primary reference: the supplied Superwhisper screenshot, using its midnight-blue to pale-lilac sky palette and full-bleed composition. Secondary reference: `annnimate-floating-navbar.mp4`, for the wide header contracting into a centered pill. Per the follow-up requests, navigation stays fixed and visible throughout scrolling, and the hero now includes the white Inter headline “Mission Planning from Earth to the Moon” and a blue Get started pill linking to `/app`.

The navbar carries the supplied `Subtract (3).svg` brandmark, the capitalized Clavius wordmark in Inter with −4% tracking (`-.04em`), links to the overview, surface mission, lunar atlas and intended users, and a blue Get started pill with white text, matching the hero button. The supplied SVG is stored unchanged in `public/images/clavius-mark.svg`, rendered white against the dark page, and also adapted for the favicon. Inter is served locally from `public/fonts/inter-latin-variable.woff2`, with its license alongside it.

The sections use the explanatory chapters and interactive demonstrations of [Aaru’s simulation page](https://aaru.com/simulation) as a layout reference. Clavius pairs its own lunar panorama with a three-state mission walkthrough and an illustrated dataset chapter. Generous gutters, black sections and indigo skies separate the chapters. The footer contains the brand and a return link.

## Implementation

- `src/landing.js`: markup, navbar scroll state, seeded canvas stars and rockets, visibility and reduced-motion handling, cleanup on route changes.
- `src/landing-content.js`: project sections, workflow, case study and benchmark disclosures, source links, and footer.
- `src/landing.css`: landing-only styling and responsive navigation.
- `public/images/clavius-twilight.webp`: generated sky, 1586 × 992, encoded as WebP at quality 92 using Pillow. The asset is decorative art, not astronomical observation or lunar dataset material.
- `src/main.js`: route mounting; hash anchors use native navigation.

Thirty rockets on desktop, sixteen on mobile. The animation runs at up to 30 frames per second, caps pixel density at 1.75, and stops while the scene is offscreen or the document is hidden. Reduced motion renders a still frame and removes navigation transitions.

## Sky asset provenance and final prompt

Generated with the built-in Image Gen tool on 14 November 2026. Original retained at `/Users/Aayush/.codex/generated_images/01a1dbd1-3ae4-7cf0-abda-33736800e6aa/exec-6130163a-3eb3-40d4-b241-ce89eeda3ed7.png`.

Final prompt:

> Use case: photorealistic-natural. Asset type: full-bleed background image for a minimal space exploration website. Create a cinematic, highly realistic twilight SKY ONLY, wide landscape 16:10 composition. Smooth immense atmospheric expanse: almost black midnight navy at the top 20%, deep cobalt blue in the middle, luminous muted lavender and pale dusty lilac along the lower 25%, closely resembling the dark blue-to-lilac gradient of the user's supplied website reference. Restrained extremely fine stars mainly in the upper half, very delicate high-altitude wisps of translucent cirrus and faint atmospheric haze near the bottom, subtle natural film grain, premium photographic realism and endless spaciousness. No ground, no horizon line, no planets, no moon, no mountains, no people, no objects, no rockets (these will be animated in code), no typography, no logos, no UI, no text. Keep the center clean and quiet. Atmospheric and luminous but understated, never bright fantasy nebula or busy galaxy. Edge-to-edge image.

## Section artwork

The built-in Image Gen tool generated the following concept illustrations. They are used only on the landing page.

- `public/images/polar-ridge.webp` — Landscape 16:9 ultra-wide photorealistic editorial art for Clavius. An astronaut's telephoto view across the Moon's rugged south polar highlands, no atmosphere, beautifully defined fine granular grey lunar regolith, layers of sunlit jagged ridges and craters receding to the horizon, very low grazing sunlight. Stark silver and muted slate-violet charcoal shadows, completely black sky, modern restrained analog lunar photography. Strong asymmetric panorama: lit ridgeline concentrated across right two thirds, left foreground in deep quiet crater shadow for white text, horizon at upper third. No text, no graphic lines, no spacecraft, no Earth, no humans, no branding.
- `public/images/rover-study.webp` — Landscape 3:2 editorial engineering photograph-style concept art. Single small plausible lunar robotic research rover, six rugged mesh wheels on articulated rocker-bogie suspension, graphite and titanium instrument chassis, subtle gold thermal foil, one slim stereo camera mast, dark solar array top. Low three-quarter front angle, rover facing left, centered fully visible with clear silhouette, dominant in frame. Moon dust with wheel tracks, long natural shadows, distant lunar hills and a black airless sky. Extreme crisp mechanical detail, restrained pewter and charcoal monochrome, analog film grain, honest natural lunar sunlight, premium documentary art direction. No lettering, logos, flags, graphic elements or people.
