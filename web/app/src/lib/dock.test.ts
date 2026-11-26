import { describe, expect, it } from 'vitest';
import { dockShown, keyboardOpen } from './dock';

describe('phone dock (WEB-029)', () => {
  it('shows only away from the chat, with no keyboard and no inline Ask in view', () => {
    expect(dockShown({ onChat: false, keyboard: false, inlineAskInView: false })).toBe(true);
    expect(dockShown({ onChat: true, keyboard: false, inlineAskInView: false })).toBe(false);
    expect(dockShown({ onChat: false, keyboard: true, inlineAskInView: false })).toBe(false);
    expect(dockShown({ onChat: false, keyboard: false, inlineAskInView: true })).toBe(false);
  });
  it('detects the on-screen keyboard from the visual viewport', () => {
    expect(keyboardOpen(812, 812)).toBe(false);
    expect(keyboardOpen(812, 760)).toBe(false);
    expect(keyboardOpen(812, 480)).toBe(true);
    expect(keyboardOpen(812, undefined)).toBe(false);
  });
});
