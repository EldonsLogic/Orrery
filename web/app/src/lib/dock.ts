// Phone "Ask Seshna" dock visibility (WEB-029). Pure, so the shell and the tests agree.
/** The on-screen keyboard takes at least this much of the layout viewport when it is open. */
export const KEYBOARD_MIN_PX = 150;

/** True when the visual viewport is shorter than the layout viewport by a keyboard's height. */
export const keyboardOpen = (layoutHeight: number, visualHeight: number | undefined): boolean =>
  visualHeight !== undefined && layoutHeight - visualHeight >= KEYBOARD_MIN_PX;

export type DockInputs = { onChat: boolean; keyboard: boolean; inlineAskInView: boolean };

/** The dock never covers content and never doubles a visible Ask field: hidden on the chat, with the keyboard open, or beside the inline Ask. */
export const dockShown = ({ onChat, keyboard, inlineAskInView }: DockInputs): boolean => !onChat && !keyboard && !inlineAskInView;
