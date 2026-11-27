'use client';

import { createContext } from 'react';

/** A screen with its own inline Ask field reports whether it is in view, so the shell's phone dock does not repeat it. */
export const InlineAskContext = createContext<(inView: boolean) => void>(() => {});
