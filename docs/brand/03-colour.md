# 03 Colour (PDF p.7 and 8)

Eight tokens in light and dark. Every text pair passes WCAG AA. Coral is for graphics only.

| Token | Role | Light | Dark | CSS variable |
|---|---|---|---|---|
| Chalk / Carbon | Background | #F3F4F6 | #0E1117 | `--color-background` |
| Panel | Surface | #FFFFFF | #171B23 | `--color-surface` |
| Carbon / Chalk | Text | #12151B | #E8EAEF | `--color-text` |
| Cobalt | Primary | #2443D0 | #86A0FF | `--color-primary` |
| Coral | Accent | #E0552C | #FF8A63 | `--color-accent` |
| Jade | Success | #13795B | #4CC79A | `--color-success` |
| Ochre | Warning | #9E5600 | #F2A541 | `--color-warning` |
| Crimson | Danger | #C21F3A | #FF6B81 | `--color-danger` |

## Contrast of the main pairs (WCAG 2.x, as stated in the PDF; verified by `tools/check_contrast.py`)
| Pair | Light | Dark | Result |
|---|---|---|---|
| Text on background | 16.61:1 | 15.70:1 | AA |
| Text on surface | 18.28:1 | 14.33:1 | AA |
| Primary text and links on surface | 7.53:1 | 6.97:1 | AA |
| Button label on primary (white light, Carbon dark) | 7.53:1 | 7.64:1 | AA |
| Success text on surface | 5.37:1 | 8.17:1 | AA |
| Warning text on surface | 5.55:1 | 8.41:1 | AA |
| Danger text on surface | 5.91:1 | 6.30:1 | AA |
| Accent graphic on background (non-text, 3:1 minimum) | 3.47:1 | 8.16:1 | AA |

## Rules
- **Proportion.** About 70% Chalk and Panel, 20% Carbon text, 8% Cobalt, 2% Coral. Cobalt marks what is actionable; Coral marks one highlight per view.
- Coral is never used for text on light backgrounds, for errors, or for the wordmark.
- Status colours always come with an icon and a label, never colour alone.
- Charts: Cobalt for the main series, Carbon at 40% for comparison, Coral for the one point that matters. Status colours only when the data is a status.
- Dark mode is a full token set, not an inversion. Primary buttons in dark mode use a Carbon label on light Cobalt.
- Note: dark button label Carbon is #0E1117 (matches the 7.64:1 claim); #12151B would give 7.39:1.
