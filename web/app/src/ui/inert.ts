/**
 * Makes everything outside `keep` inert (not focusable, hidden from assistive tech) and returns a function that restores it.
 * Used while a modal is open (WCAG 2.4.3, 4.1.2). Elements that were already inert stay inert after restore.
 */
export function inertOutside(keep: HTMLElement): () => void {
  const changed: HTMLElement[] = [];
  for (let node: HTMLElement | null = keep; node && node !== document.body; node = node.parentElement) {
    const parent: HTMLElement | null = node.parentElement;
    if (!parent) break;
    for (const sibling of Array.from(parent.children)) {
      if (sibling === node || !(sibling instanceof HTMLElement) || sibling.inert || sibling.tagName === 'SCRIPT') continue;
      sibling.inert = true;
      changed.push(sibling);
    }
  }
  return () => changed.forEach((el) => { el.inert = false; });
}
