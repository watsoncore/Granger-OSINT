# Articulated assets — built-in ImageGen

No CLI fallback, external key or third-party generator was used.

## Hermione left curl repair

Reference/edit target: unchanged `grangerpet/assets/character.png`.
Generated original: `hermione-hair-repair-source.png`. Only the occluded left
curl is consumed after fitting to the original hair bounds. The face, bangs,
other hair, costume and footwear are retained from the approved master.

Prompt:

> Edit target: the attached approved 512x512 2D chibi Hermione sprite. Produce a technically precise animation HEAD LAYER ONLY, on transparent background. Preserve exactly the original face, eyes, bangs, hair color, wavy hair silhouette, ink line thickness, cream highlights, relative position and scale of the existing head. Absolutely no portrait redesign, no different art style, no new face. Keep all the brown hair including long outer curls, their tips and the complete right outer silhouette. Remove the wand that crosses the left outer hair, remove the small hand and sleeve crossing that hair, and restore the tiny occluded hair area with the same original hand-drawn curls. Remove all costume/body/legs/arms below the chin, leaving only the original head, face and hair including side hair hanging down. Preserve the original O mouth; this will be animated by code. Canvas same 512x512, head in exact same original location, no enlargement, no shadows, no labels, no checkerboard.

The generator changed canvas framing and included low-alpha specks. The build
script removes alpha <=8, fits significant hair bounds, consumes only the left
curl, and records both hashes. It does not replace the approved whole head.
