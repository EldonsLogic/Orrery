# 08 Product UI basics (PDF p.13)

In the product the brand shows up as restraint: Cobalt only where something can be done, exact numbers, and a calm Chalk and Panel surface.

| Component | Rule |
|---|---|
| Primary button | Cobalt fill, white label (dark mode: light Cobalt fill, Carbon label), 40 px high, 8 px radius, Readex Pro 500. One per view. |
| Secondary button | Transparent, Cobalt label, Cobalt border at 40% |
| Destructive button | Crimson fill, white label, always with a confirmation that names what will be deleted |
| Status pill | Icon and label in the status colour on a 14% tint: Jade for reported or paid, Ochre for attention, Crimson for rejected or failed |
| Amounts and tables | Tabular figures, aligned to the end of the column (right in English, left in Arabic) |
| Assistant messages | The mark in Cobalt at 20-24 px as the avatar, message on Panel |
| Focus | 2 px Cobalt ring, 2 px offset, on every interactive element |
| Motion | 150-200 ms ease-out, only to show a change of state; respect reduced-motion settings |

- **Empty states** say what to do next, in the brand voice.
- **Errors** name the problem and the fix, and never apologise.

Values live in `tokens/tokens.json` under `components`.
