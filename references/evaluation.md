# Evaluation protocol

This protocol measures whether the skill improves Seedance remake quality in standard and high-fidelity modes. It is not part of external generation.

## Fixed runtime conditions

For every generation case:

- Submit exactly the request or requests declared by the selected package.
- Submit only the standalone prompt and product images; keep the source video offline.
- For standard mode, do not split or edit generation.
- For high-fidelity mode, apply only the deterministic trims and hard-cut order in `assembly-plan.json`.
- Use the same Seedance model version, seed policy, duration, resolution, and generation budget across compared systems.

## Evaluation layers

### Package validation

Run the skill validator and unit tests. Require valid frontmatter and schemas, exactly one prompt plus product-image roles in every request, legal parameters, complete image placeholders, continuous target timelines, a valid editing contract, no internal timeline IDs in prompts, and complete must-keep coverage.

### Analysis accuracy

Compare Source Video DNA with human annotations for shot boundaries, beat anchors, camera and composition, dialogue and text, subject identity, state changes, product interaction, scene changes, transitions, and narrative roles.

Initial target gates:

- Shot-boundary precision and recall at least 95% within 100 ms.
- Must-keep state-change recall at least 95%.
- Source-element coverage at least 98%.
- Request-schema validity 100%.

### Compression fidelity

For sources longer than 15 seconds, have reviewers check that the one-call plan retains the hook, signature visual, causal order, product entry, key interaction, transformation endpoints, payoff, and salient audio beats. Penalize unrecorded omissions more heavily than recorded lower-value omissions.

### External generation result

After an external program submits the declared request package and performs any declared deterministic assembly, run postflight and compare source and result for:

- Shot order and relative timing
- Cut-energy curve and beat alignment
- Camera movement, composition, perspective, and lighting
- Person identity, action, expression, and state trajectory
- Object, product, and scene state trajectory
- Target-product identity and appearance
- Text, effects, transitions, dialogue, music, and sound design
- Narrative and emotional arc

Critical failures override the weighted score: missing required transformation, wrong product, major identity drift, missing signature shot, reversed narrative order, source-dependent prompt wording, or a video/audio item in the request.

## Test matrix

Start with 30 diagnostic cases. Expand to about 300 authorized cases:

- Cover the video families in `video-type-routing.md`.
- Cross same, adjacent, functionally related, and distant product replacements.
- Include Chinese, English, Spanish, Portuguese, and Arabic where speech or text matters.
- Include 1:1, 9:16, 16:9, and uncommon source ratios.
- Include silent video, music-only, dense dialogue, 0.3-second cuts, multiple people, multiple products, blurry product images, one-view products, 60-second sources, strong transformations, animation, VFX, and unseen formats.

Keep development, validation, and hidden test sets separate. Do not tune on the hidden set.

## Baselines and blind review

Compare:

1. The existing `video-clone` workflow.
2. A generic single-prompt baseline.
3. The new standard mode.
4. The new high-fidelity mode for dense timelines.
5. An expert-authored request package where available.

Use at least three blind raters per result. Show raters the source video and target product, but not which workflow produced the output. Track win rate, mean fidelity score, critical failure rate, inter-rater agreement, and cost per accepted result.

An initial evidence bar for a strong release is at least 70% blind win rate against the old skill, mean fidelity at least 4.2/5, critical-detail omission below 5%, and product-identity failure below 5%. Treat these as targets to validate, not achievements to claim before testing.
