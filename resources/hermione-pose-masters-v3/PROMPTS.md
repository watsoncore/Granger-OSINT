# Pose art provenance — Hermione v3

Tool: built-in `image_gen.imagegen`, transparent_background=true. No CLI fallback,
external API key, installer or additional model/runtime. Every successful request
used `grangerpet/assets/character.png` as its single edit target. The complete
generated drawings are archived here; the build consumes only reviewed sleeve
and hand masks. Generated faces, hair, torso and shoes are not runtime replacements.

## cheek-source.png — exact prompt

Use case: identity-preserve. Asset type: production 2D hand-drawn chibi animation POSE MASTER, not a screenshot, not concept poster. Edit target is the attached approved Hermione sprite. Keep this exact character identity, face, bushy chestnut hair silhouette, original head/body proportions, school costume, robe burgundy lining, tie, skirt and brown shoes, ink palette and soft flat shading. Full body, same front/three-quarter view and framing as target, on genuinely transparent background, no text, no props, no wand. Change ONLY her arm/torso pose into a shy cheek-touch pose: her anatomical LEFT arm (viewer right) bends upward naturally from the shoulder, elbow clearly visible low beside ribs, forearm rises continuously to a small wrist and relaxed hand at the OUTER lower cheek on viewer right. Fingers lie delicately along the cheek below the outer eye, never cover the eye or mouth. Her other arm bends modestly with a relaxed hand at upper chest, not a severed fist. Draw finished connected anatomy from shoulder through elbow and sleeve to wrist and palm. Robe sleeves have broad upper fabric but taper to a fitted small cuff, with a clear dark cuff opening and a short cream wrist that joins the palm naturally. Small expressive chibi hands with thumb and 3 simplified grouped fingers, not realistic detailed hands and not huge palms. Include carefully drawn folds indicating elbow and forearm direction, slightly lighter charcoal inner-plane shading and original warm brown ink. NO triangular black sticks, NO mittens floating beyond wide bell sleeves, NO detached white stumps, NO duplicate hands or old wand hand, NO anime redesign or different hair. Slight shoulder lift and tiny torso lean express shyness; feet stay in the original stance and size. Prioritize a convincing hand-drawn arm silhouette while preserving every other design invariant. Output just one complete sprite with generous transparent margins and all hair and feet intact.

## reading-source.png and folded-source.png — shared prefix, followed by variant

Edit target: the attached approved 2D Hermione chibi sprite. Production pose master for an existing animated character, not a screenshot. Preserve exact original face, chestnut bushy wavy hair silhouette and color, head/body proportions, front three-quarter view, robe, burgundy lining, white shirt, striped tie, skirt and brown shoes, warm brown ink, gentle flat charcoal shadows, no style redesign. Full body on real transparent background, no labels, no props of any kind, no wand. Draw anatomically continuous expressive small chibi arms from shoulders through elbows and tapered sleeves into short cream wrists and small hands. Use fitted white shirt cuffs inside robe cuffs, believable fabric folds at elbows and forearms, small thumbs and grouped fingers, no severed white blobs, no floating hands, no black stick polygons. Keep face and head size unchanged; feet stay on original baseline.

### reading variant

A special READING BODY POSE WITHOUT THE BOOK. Both elbows bend down and outward beside the waist. Both forearms slope upward and inward to hands at lower chest in front of the torso. The two small hands are separated horizontally by about the width of her neck, shaped as open curved supporting grips for the lower corners of an imaginary book. Palms support from below, thumbs point up and fingers curl around an imaginary edge; draw a complete convincing hand silhouette without actually drawing any book or rectangle. Gentle forward upper-body engagement and relaxed shoulders. The pose alone must read as holding an open book. Show both complete connected arms and cuffs, not hands pasted on chest.

### folded variant

A special FOLDED ARMS pose expressing Hermione's mild cute annoyance. Both forearms cross convincingly across the ribcage under the tie. The near sleeve is drawn over the far forearm with a readable elbow and fabric creases. Small wrists and hands tuck into or against the opposite upper arm; only a small natural part of the fingers should show, never two disconnected fists in the middle. Shoulders slightly raised, hip weight subtly shifted without changing the actual body proportions. Draw the completed crossed-arm silhouette specifically for this pose, not two straight horizontal bars.

## rest-source.png — exact prompt

Edit the reference sprite into a neutral standing pose with both arms relaxed down by her sides, small relaxed hands visible just below the sleeve cuffs. Keep the exact original 2D chibi character, face, hair color and shape, head/body proportions, Hogwarts school uniform and shoes. Remove the wand. Improve the robe sleeve artwork with gentle fabric folds, tapered cuffs, a small peek of white shirt cuff, and naturally joined small hands. Same compact 2D hand-drawn style and original brown outline palette. Full body on transparent background, no other objects, no text. This is a production costume/arm pose master; every other design detail is unchanged.

## chin-source.png — exact prompt

Edit the reference sprite into a thoughtful pose: one small hand gently supports the chin, the other arm folds loosely across the ribs to support that elbow. The sleeves and cuffs clearly show the continuous bent arms. Keep the exact original character, face and chestnut hair, body/head proportions and school uniform; do not change the head or costume. Original flat hand-drawn 2D chibi style with warm brown ink and gentle charcoal fabric shadows. Remove the wand. Full body, real transparent background, no text and no props.

## Other artwork

Phone and hip generation attempts returned output moderation errors; they are
not successful source drawings. `hip-right.svg`, `point-hand.svg`, `wand-hand.svg`
and `reach-arms.svg` are editable original vector drawings made in this workspace.
The wand sleeve is isolated from the preserved approved character master.
`rig.json` records reviewed masks and landmarks; the build records source hashes.
