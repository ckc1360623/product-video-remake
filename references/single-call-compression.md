# Single-call compression

This reference applies only when standard single-call mode is selected. High-fidelity mode follows the mode-selection and assembly rules in `workflow.md`.

## Duration choice

- Use an integer duration from 4 through 15 seconds.
- When the source is already within range, choose the nearest legal integer and scale sub-second timestamps carefully.
- When the source is shorter than 4 seconds, expand holds and motion continuity to 4 seconds without inventing a different story.
- When the source exceeds 15 seconds, default to 15 seconds unless the user asks for a shorter target.

## Value model

Rank shots and source elements by:

- `must_keep`
- Signature visual uniqueness
- Hook value
- Narrative dependency
- Person/object/scene state transition
- Product visibility and interaction
- Audio beat salience
- Payoff or CTA role

Remove repetitive exposition and duplicate proof before unique visual or state-change information.

## Compression operations

Allowed operations are script-level only:

- Shorten holds.
- Accelerate montage rhythm.
- Merge adjacent shots with the same narrative purpose into one timeline unit.
- Condense repeated dialogue.
- Represent a longer process with a match cut, time-lapse, or rapid visual progression inside the single generated video.

In standard mode, never create a second request, clip manifest, edit decision list, or assembly instruction.

## Fidelity accounting

Every omitted source element needs `omitted_with_reason`. Every must-keep element must map to a target timeline unit. If all must-keep actions cannot be individually staged, combine them into a clearly described rapid montage while retaining endpoints, causal order, and beat relationship.

`scripts/compress_for_single_call.py` is a deterministic candidate generator. Its result is not a substitute for semantic review. Refine descriptions and merged actions before compiling when the source is complex.
