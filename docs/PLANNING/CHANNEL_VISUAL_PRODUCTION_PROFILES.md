# Voxora Studio — Channel & Visual Production Profile Catalogue

> Status: Approved planning scope added at the user's direction on 2026-11-20.
> Parent plan: [Master Product Plan & Delivery Registry](./README.md)
> This is a planning catalogue, not a claim that these profiles or engines are implemented.

## 1. Product-level rules

Voxora has one Universal Visual Production Engine and one automated production workflow. Channel profiles are configuration and creative-policy packages; they are not separate applications or duplicated render engines.

The primary workflow remains: supplied script + supplied narration audio + channel profile + optional structured Visual Direction Package → automatic complete MP4. Script is the semantic source of truth; supplied narration is the timing/synchronization master. No user-facing NLE or manual scene-by-scene asset assignment is a prerequisite.

The AI Production Director chooses a visual treatment per scene/shot using the channel profile, script semantics, factual requirements, available assets, provider capabilities and resource budget. A profile defines preferences and constraints, not a rigid template: a documentary may use real archival photography for a real event, then maps, sketches or motion graphics to explain context.

### Shared visual production capabilities

- 2D cartoon and character animation, including reusable character identity, pose/expression/action libraries, interaction and continuity.
- Stickman animation as a first-class specialized style, not merely a generic fallback.
- Vox-style motion graphics, typography, infographic and data visualization.
- Geographic maps, route/territory changes and location explainers.
- Sketch, pencil/ink, whiteboard and hand-drawn illustration.
- 2.5D layered/parallax composition and camera movement.
- 3D/scientific visualization when it materially improves understanding.
- Documentary photography and video/archival collage, with factual source verification.
- Timelines, diagrams, blueprints, newspaper/document collage and evidence boards.
- Procedural graphics, captions, transitions and narration-synchronized motion.

### Asset truth, rights and provenance

1. Prefer user-supplied assets, then verified/licensed sources compatible with the intended use, then appropriately licensed/public-domain/Creative Commons sources, then configured generation providers for illustrative material, then profile-compatible procedural graphics.
2. For real people, real places and historical/current events, retrieve genuine photographs/footage when a factual depiction is needed and suitable rights/usage are available. Keep source, creator, license, attribution and retrieval/provenance metadata.
3. Never present an AI-generated reconstruction as a genuine photograph, archival image, eyewitness recording or documentary evidence. Label reconstructions/illustrations clearly.
4. Respect privacy, dignity, sensitive events, copyright, platform policies and source terms. Do not fabricate quotes, evidence, dates, events or historical details.
5. If a suitable asset is unavailable or its rights/status cannot be established, use a clearly illustrative sketch, map, diagram, silhouette or procedural graphic—or report the gap. Do not silently imply authenticity.

## 2. Channel profile catalogue

The following 14 channel profiles are included in the product plan. Some are current channels and some are future channel concepts; implementation priority is governed by the delivery roadmap and user approval, not by this catalogue's numbering.

### CP-01 — Quasivanta
**Niche:** Space, astronomy, astrophysics and science.

Preferred treatments:
- Cinematic 2D space illustration and 2.5D parallax.
- 3D planets, stars, spacecraft, orbital and celestial-body visualization.
- Vox-style science explainers, scientific infographics and scale comparisons.
- Solar-system, galaxy, orbit and mission maps/diagrams.
- Technical sketches, spacecraft/satellite explainers and animated data.
- Genuine NASA/ESA/observatory imagery and footage when relevant and usable.

Director rules: distinguish observed data, scientific model, artist impression and speculative concept; never present an artist impression as a telescope photograph. Use labels/units and scale caveats where necessary.

### CP-02 — Veltracis
**Niche:** History, mystery, ancient civilizations and unexplained historical stories.

Preferred treatments:
- Historical pencil/ink sketch and hand-drawn reconstruction.
- Animated maps, borders, routes and historical geography.
- Ancient city/architecture 2D and 2.5D reconstructions.
- Documentary photo/archival collage and genuine historical footage.
- Timelines, newspaper/document collage and silhouette mystery visuals.
- 2.5D cinematic scenes; optional stickman explainers where suitable.

Director rules: separate established history, disputed interpretation, legend and speculation; mark reconstructions and avoid inventing historical evidence.

### CP-03 — Sizzjin
**Niche:** Horror, suspense and original frightening stories.

Preferred treatments:
- Dark 2D cartoon and character-based animation.
- Horror stickman, silhouette and paper-cutout animation.
- Sketch horror, shadow/environment animation and 2.5D cinematic scenes.
- Camera suspense movement, atmospheric particles/light and minimalist motion graphics.
- Character action, expression and continuity; sound cues synchronized to narration.

Director rules: preserve story continuity and intentional suspense; avoid repetitive stock templates and gratuitous graphic imagery.

### CP-04 — Drowsehaven
**Niche:** Adult sleep stories, mythology, fantasy and calming narration.

Preferred treatments:
- Watercolor storybook illustration and soft 2D cartoon.
- Gentle 2.5D environments, dreamlike landscapes and illustrated characters.
- Slow camera movement, subtle weather/particles/light and calm transitions.
- Consistent character/environment design across long-form chapters.

Director rules: calm pacing and restrained visual change; avoid flashes, abrupt cuts and excessive effects. Protect long-form visual continuity.

### CP-05 — Rihvaya
**Niche:** Islamic stories, Quran, authentic Hadith, Prophets, Sahaba, Islamic history/civilization and education.

Preferred treatments:
- Respectful 2D Islamic cartoon and historical storytelling animation.
- Character-based educational animation for ordinary people and historical context.
- Islamic geography/maps, architecture and civilization reconstructions.
- Arabic calligraphy/typography, Quranic concept diagrams and educational infographics.
- Sketch art, 2.5D cinematic scenes and documentary imagery for modern Islamic topics.

User-defined representation convention for Prophets: a human body/robe may be depicted, but the entire face area must be concealed by bright light with no eyes, nose, mouth or facial details. Ordinary people may have visible faces. Treat this as the user's chosen creative convention; do not present it as a universally agreed religious ruling. Use respectful treatment for Sahaba and other revered figures. Do not invent scriptural events, dialogue or claims; verify Quran/Hadith references and distinguish authentic sources from disputed reports. Thumbnails may follow the user's no-face preference.

### CP-06 — Niq Exposed
**Niche:** Investigative documentary, exposés, public-interest stories and evidence-led explainers.

Preferred treatments:
- Genuine public-figure photographs and documentary footage where relevant and lawfully usable.
- Newspaper/document collage, timelines, maps and evidence-board graphics.
- Vox-style motion graphics, data visualization and 2.5D explanatory scenes.
- Sketch reconstruction and procedural diagrams when genuine visuals are unavailable.

Director rules: source every material factual claim; distinguish allegation, verified fact, opinion and unresolved question. Do not fabricate documents, quotes, screenshots or evidence. Use AI reconstructions only as clearly labelled illustrations.

### CP-07 — Deep Ocean Creatures
**Niche:** Marine biology, deep-sea life, ocean ecosystems and unusual aquatic species.

Preferred treatments:
- Scientific 2D creature illustrations and 3D creature animation.
- Underwater/deep-sea environments, bioluminescence and habitat visuals.
- Depth, pressure, anatomy and ecosystem infographics.
- Ocean-floor maps, size comparisons, scientific sketches and genuine underwater photos/footage.
- Cinematic deep-sea documentary collage.

Director rules: scientific appearance and behavior should be evidence-based; label hypothetical reconstructions and avoid presenting invented species/behavior as observed fact.

### CP-08 — Crime Documentary
**Niche:** True crime, investigations, criminal cases and justice-system explainers.

Preferred treatments:
- Verified documentary photography and licensed/publicly usable footage.
- Case timelines, location maps, procedural diagrams and evidence/document collage.
- Sketch reconstructions, stickman explainers and restrained 2D character reconstruction.
- Data/investigation graphics and courtroom/police-process illustrations.
- 2.5D scenes where they clarify chronology or geography.

Director rules: preserve presumption of innocence where applicable; distinguish allegation, charge, conviction and confirmed fact. Do not fabricate crime-scene evidence or depict speculation as fact. Protect victims, minors, private individuals and sensitive personal information; avoid gratuitous graphic imagery.

### CP-09 — Educational Explainer
**Niche:** General education, psychology, knowledge, science and practical explainers.

Preferred treatments:
- Stickman and 2D cartoon character storytelling.
- Vox-style motion graphics, infographics and data visualization.
- Sketch/whiteboard explanation, 2.5D scenes, maps and diagrams.
- Genuine photos or footage where real-world examples materially help.
- Character-led examples and step-by-step visual metaphors.

Director rules: optimize for comprehension, visual hierarchy and accurate labels; avoid decorative motion that competes with the explanation.

### CP-10 — Inventions & Discoveries
**Niche:** Inventions, inventors, engineering, technology and discoveries.

Preferred treatments:
- 2D invention explainers and technical cutaway diagrams.
- Blueprint/engineering sketch and historical illustration.
- Genuine inventor photographs and historical documentary imagery.
- Animated maps/timelines and stickman educational storytelling.
- 2.5D product/machine visualization and scientific infographics.

Director rules: distinguish original invention, later improvement, patent date, prototype and commercial release; do not attribute an invention to a person without evidence.

### CP-11 — Cartoon & Animated Stories
**Niche:** Original 2D cartoon stories, animated adventures, comedy and short films.

Preferred treatments:
- 2D cartoon character animation and frame-by-frame animation.
- Character rigging/skeletal animation where suitable.
- Stickman stories, comedy timing and expressive character acting.
- Fantasy/adventure environments and 2.5D cartoon scenes.
- Character dialogue/lip-sync when dialogue audio exists.
- Multi-character interaction, props, background/environment animation and cinematic camera movement.
- Character voices, non-verbal vocals, SFX and BGM through the shared audio system.

Specialized requirements:
- Persistent Character Bible: stable identity, silhouette, proportions, palette, clothing, accessories, personality and voice identity.
- Reusable poses, expressions, actions and interaction choreography.
- Scene-to-scene continuity checks for character appearance, props, geography and screen direction.
- Narration/dialogue-synchronized action and mouth movement where supported.
- Automated fallback to limited animation, pose changes, camera moves and motion graphics when full character animation is unavailable; do not claim full animation if only still images are rendered.

### CP-12 — Biography & Famous Personalities
**Niche:** Biographies of notable people from science, business, leadership, arts, literature, sports and other fields.

Preferred treatments:
- Genuine documentary portraits, archival photographs and licensed footage.
- Chronological life timeline: origins, education, turning points, achievements, setbacks and legacy.
- Vox-style motion graphics and data visualization for influence/impact.
- Historical sketch animation and 2D illustrative reconstructions.
- 2.5D parallax portraits, maps of relevant places and newspaper/archive collage.
- Character-based animation only when it adds clarity and is clearly illustrative.

Director rules:
- Real photographs are preferred for real-person factual representation.
- Verify identity, date, context, source and usage rights before assigning a photograph to a person/event.
- Do not generate a synthetic image that could be mistaken for a genuine photograph or quote from a real person.
- Label illustrative reconstructions; avoid false endorsements, fabricated quotes or misleading depictions.
- Keep chronology and claims about achievements, controversies and legacy source-grounded.

### CP-13 — Animals & Wildlife
**Niche:** Animal kingdom, wildlife, rare species, animal behavior, evolution and ecosystems.

Preferred treatments:
- Genuine wildlife photography and documentary footage.
- 2D animal animation and scientific creature illustration.
- 3D animal anatomy/locomotion visualization when scientifically useful.
- Animal behavior reconstruction, habitat and geographic maps.
- Food-chain/ecosystem infographics and size comparisons.
- Underwater/deep-sea animation and 2.5D nature documentary scenes.
- Scientific sketch and procedural diagrams.

Director rules: distinguish observed footage from staged, stock, generated or reconstructed visuals. Verify species, range, behavior and conservation facts; label uncertain or illustrative behavior.

### CP-14 — Science & Discovery
**Niche:** Physics, chemistry, biology, technology, scientific discoveries, experiments and open scientific questions.

Preferred treatments:
- Vox-style science explainers and 2D scientific animation.
- 3D scientific visualization, molecular/atomic and human-anatomy animation.
- Physics simulation and motion graphics.
- Mathematical/data visualization, technical sketch and blueprint.
- Scientific maps/diagrams and genuine documentary photography/footage.
- 2.5D cinematic science animation.

Director rules: distinguish measured evidence, established theory, model, hypothesis and speculation. Use correct units, scales and labels; never imply that a conceptual visualization is direct experimental footage.

## 3. Cross-profile Director selection policy

For each shot, the Director should classify:
- narrative purpose and spoken interval;
- factual/fictional status and whether a real-world subject must be shown;
- visual subject (person, place, event, process, concept, creature, map, data or story character);
- channel profile preferences and per-project overrides;
- required continuity (person/character, costume, location, period, props, palette);
- available verified assets, licenses and provider capabilities;
- target-PC resource budget and output requirements.

Then select the least-cost, profile-compatible treatment that meets the shot's purpose. The same video may combine real documentary assets, maps, sketches, animation and motion graphics when the narration calls for them. A channel profile is a default creative policy, not a prohibition on a necessary factual visual.

## 4. Implementation mapping and acceptance

| Capability | Planning home | Minimum acceptance evidence |
|---|---|---|
| Versioned channel profiles and precedence | VXP-03 | Profile schema, validation, import/export and override tests |
| Shared visual style and engine capability catalogue | VXP-08 | Capability matching and deterministic fallback tests |
| Character Bible, stickman/cartoon continuity | VXP-08 / VXP-11 | Repeated character across multiple narration-timed scenes with identity/continuity checks |
| Documentary source acquisition and provenance | VXP-04 / VXP-11 | Source, license, attribution and factual/illustrative status retained end-to-end |
| Maps, timelines, data graphics and sketch engines | VXP-08 / VXP-11 | Narration-aligned output, correct data/labels and render validation |
| Automatic profile-aware shot selection | VXP-05 / VXP-10 | Script + supplied narration + profile produces a complete MP4 without manual asset assignment |
| Real-person/biography factual visuals | VXP-04 / VXP-11 | Verified image identity/context and rights metadata; generated reconstructions visibly labelled |
| Automated visual QC | VXP-09 / VXP-10 | Detect missing media, black frames, timing gaps, insufficient coverage and provenance failures |

### Product boundary for timeline/review

The internal timeline/timebase/track/composition model remains necessary for synchronization and rendering. VXP-12 must be treated as optional production review/correction UX, not a full user-facing NLE roadmap. Clip-level review, selective regeneration and limited corrections may be provided where useful, but no full multitrack manual editor is required for the primary product outcome. Auto Produce must work without the user opening or editing a timeline.

### Not an implementation claim

Adding these profiles to the plan does not mean their engines, visual acquisition, animation, character rigging, factual verification or end-to-end automation already exist. Those remain explicit implementation gaps and must be delivered in small VXP phases with tests and target-PC acceptance. Do not mark a profile as production-ready merely because its configuration record exists.
