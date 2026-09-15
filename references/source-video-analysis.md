# Source Video DNA analysis

Analyze the complete video, not a sparse synopsis. Use measured timestamps when available and confidence labels for visual estimates.

For local media, `scripts/prepare_analysis_pack.py` creates a cached V1.3 analysis pack. It decodes the source once for dense evidence frames, a zero-millisecond baseline plus scene-change candidates, and analysis-only audio, then builds chronological overview sheets from those evidence frames. Inspect every overview sheet first. Inspect original dense/cut frames around every boundary, rapid transition, transformation, product interaction, text, face, body, skin, object or scene uncertainty. If coverage is uncertain, fall back to every dense frame in that interval or extract an exact full-resolution frame with `scripts/extract_evidence_frame.py`. The extracted audio and all analysis images are internal evidence and must never be added to the Seedance request.

## Media layer

Record duration in milliseconds, frame rate, dimensions, ratio, audio presence, and rotation.

## Shot layer

For every hard cut, soft transition, speed-ramp boundary, or meaningful internal camera change, record:

- `source_start_ms`, `source_end_ms`, and duration.
- Visual description and narrative role.
- Shot size, camera height and angle.
- Composition, subject positions, foreground/midground/background.
- Camera movement type, direction, speed, acceleration, and stability.
- Lens class, perspective, depth of field, distortion, and confidence.
- Lighting direction, contrast, color palette, texture, and visual style.
- Transition in/out, motion blur, VFX, overlays, and text.

Do not pretend to know exact focal length without metadata. Prefer `lens_class`, an estimated range, observable perspective, and confidence.

## Subject and state layer

Track identities across shots. For people, capture body shape, face shape, skin tone and texture, visible marks, hair, makeup, clothing, pose, expression, energy, and gaze. For product, objects, and scene, capture before/during/after states.

Represent changes explicitly:

```json
{
  "id": "E_body_01",
  "type": "person_state_change",
  "description": "The lead changes from visibly fuller to visibly slimmer",
  "source_shot_ids": ["S001", "S006"],
  "must_keep": true,
  "from_state": "fuller body, rounded face, closed posture",
  "to_state": "slimmer body, narrower face, open confident posture"
}
```

## Audio layer

Record dialogue with timestamps, music sections, beat and downbeat anchors, sound effects, silence, loudness changes, and synchronization between sound, motion, product appearance, and cuts. For fast-cut videos, timestamps should come from signal analysis rather than language-model intuition whenever tooling is available.

## Narrative layer

Label the job of each shot: hook, problem, escalation, reveal, product entry, demonstration, proof, transformation, payoff, or CTA. Also record signature shots and retention devices.

## Fast-cut rule

Inspect frames densely around suspected cuts. A 0.3-second shot is still a shot. Preserve the source cut-energy curve even when a long video must be compressed into a single call.

When adjacent shots share the same person, action, and scene, do not treat them as duplicates until comparing outfit/state, pose, framing, camera distance, background geometry, and beat position. Record each meaningful difference as `visual_delta`; mark a shot `must_be_distinct` when merging it would flatten a transformation, proof sequence, repeated-use montage, or other intentional rhythm.

## Source-element ledger

Create `source_elements` for every replication-relevant camera event, audio event, state change, signature object/scene change, text event, transition, and product interaction. Mark indispensable details `must_keep: true`.
