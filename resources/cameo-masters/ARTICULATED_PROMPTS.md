# Articulated assets — built-in ImageGen

No CLI fallback, external key or third-party generator was used.

## Hermione left curl repair

Reference/edit target: unchanged `grangerpet/assets/character.png`.
Generated original: `hermione-hair-repair-source.png`. Only the occluded left
curl and lower fringe are consumed after fitting to the original hair bounds.
The lower fringe replaces garment fragments between curls. The face, bangs,
upper/middle hair, central costume and footwear retain the approved artwork.

Prompt:

> Edit target: the attached approved 512x512 2D chibi Hermione sprite. Produce a technically precise animation HEAD LAYER ONLY, on transparent background. Preserve exactly the original face, eyes, bangs, hair color, wavy hair silhouette, ink line thickness, cream highlights, relative position and scale of the existing head. Absolutely no portrait redesign, no different art style, no new face. Keep all the brown hair including long outer curls, their tips and the complete right outer silhouette. Remove the wand that crosses the left outer hair, remove the small hand and sleeve crossing that hair, and restore the tiny occluded hair area with the same original hand-drawn curls. Remove all costume/body/legs/arms below the chin, leaving only the original head, face and hair including side hair hanging down. Preserve the original O mouth; this will be animated by code. Canvas same 512x512, head in exact same original location, no enlargement, no shadows, no labels, no checkerboard.

The generator changed canvas framing and included low-alpha specks. The build
script removes alpha <=8, fits significant hair bounds, consumes only the left
curl, and records both hashes. It does not replace the approved whole head.

## Independent Harry master

Reference: approved Hermione, style and scale only. Output archived as
`harry-independent-source.png`, normalized to `assets/scenes/harry-v2.png`.
The old Ron-derived `harry.png` remains preserved and is no longer active.

Prompt:

> Create a matching full-body 2D chibi boy sprite for the attached hand-drawn desktop companion style. Character: Harry Potter as an ordinary schoolboy, messy uneven jet-black hair, round thin glasses, green eyes, a tiny lightning scar on forehead, white shirt, burgundy and gold striped tie, charcoal school robe with burgundy lining, dark trousers and brown school shoes. No wand, no props. Friendly slightly hesitant neutral closed-mouth expression, arms relaxed down close to sides, hands visible, facing front with slight three-quarter angle. Independent drawing and distinct hair/face/silhouette; do not recolor another boy. Match reference head-to-body ratio, warm thin dark-brown ink outlines, warm soft flat shading, small hand-drawn highlights, simple compact school costume. Same visual age, same flat 2D illustration, no 3D, no photorealism, no poster, no text. Complete feet, transparent background, square composition. This is a separate matching guest character; do not alter the reference girl.
