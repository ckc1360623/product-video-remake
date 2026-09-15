# Product understanding and adaptation

## Evidence model

Never collapse observation and inference. Store product knowledge as:

- `observed`: packaging text and visual traits directly visible in the images.
- `inferred`: probable category, use action, name, or selling point with confidence.
- `user_confirmed`: facts supplied or confirmed by the user.
- `unknown`: facts that cannot be supported by the inputs.

Use observed and user-confirmed product identity first. Use high-confidence inference to keep the flow low-friction, but do not invent precise ingredients, specifications, or mechanisms that the image does not support.

## Visual identity

Capture shape, proportions, dominant and accent colors, material, cap or opening mechanism, logo position, label hierarchy, visible text, and which sides are actually shown. With one front image, avoid requiring an exact unseen back panel. This is an accuracy rule, not a content-review rule.

## Product distance

Judge distance across category, shape and scale, use affordance, scene fit, transformation target, and narrative role.

### Same category

Replace identity and copy. Preserve original product handling, timing, state changes, and visual grammar.

### Adjacent category

Preserve structure and transformations. Make only the smallest physical interaction change, such as steeping tea becoming mixing a powder.

### Functionally related category

Preserve every feasible visual detail and the same state-change arc. Remap only the product-causality action that would otherwise look physically wrong.

### Distant category

Still preserve shot count pattern, timing curve, camera, composition, audio accents, people, emotion, scene progression, contrast, text timing, and transitions. Replace impossible product interactions locally. Do not use category distance as permission to write a new advertisement.

## Adaptation ledger

For each product-related source detail record:

```json
{
  "source_detail": "The actor drinks from the original tea cup",
  "decision": "minimally_adapted",
  "target_instruction": "The actor sits onto the target chair at the same beat",
  "preserved_features": ["start time", "screen position", "expression change", "push-in speed"],
  "reason": "The target product cannot be consumed"
}
```

All unrelated details remain `preserved` by default.
