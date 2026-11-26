import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsUpDown,
  CircleCheck,
  CircleDashed,
  CircleX,
  Clock,
  Download,
  FileSpreadsheet,
  FileText,
  History,
  Inbox,
  Lock,
  Plus,
  Search,
  Settings,
  Upload,
  X,
  House,
  Menu,
  MessageSquare,
  Package,
  Palette,
  PanelLeftClose,
  PanelLeftOpen,
  ReceiptText,
  ShoppingCart,
  Square,
  TriangleAlert,
  Users,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import { cx } from './cx';
import styles from './Icon.module.css';

/**
 * The one icon component (WEB-029). PLACEHOLDER glyphs from Lucide (ISC) until the Seshna icon set exists (built from the
 * Nuqta S geometry); swapping the set means changing this file only. One family: stroke 1.5, 16 px in buttons and badges
 * (sm), 20 px in navigation (md). Decorative: the visible text beside an icon carries the meaning.
 */
const GLYPHS = {
  arrowDown: ArrowDown,
  arrowUp: ArrowUp,
  back: ArrowLeft,
  chevronDown: ChevronDown,
  chevronsUpDown: ChevronsUpDown,
  pageBack: ChevronLeft,
  pageForward: ChevronRight,
  statusDone: CircleCheck,
  statusOpen: CircleDashed,
  statusStopped: CircleX,
  statusWaiting: Clock,
  download: Download,
  sheet: FileSpreadsheet,
  file: FileText,
  history: History,
  empty: Inbox,
  lock: Lock,
  plus: Plus,
  search: Search,
  settings: Settings,
  upload: Upload,
  close: X,
  home: House,
  menu: Menu,
  chat: MessageSquare,
  package: Package,
  palette: Palette,
  railCollapse: PanelLeftClose,
  railExpand: PanelLeftOpen,
  receipt: ReceiptText,
  cart: ShoppingCart,
  stop: Square,
  warning: TriangleAlert,
  users: Users,
  workflow: Workflow,
} as const satisfies Record<string, LucideIcon>;

export type IconName = keyof typeof GLYPHS;
export type IconSize = 'sm' | 'md';
export const ICON_STROKE = 1.5;
/** Glyphs that point along the reading direction and flip in right-to-left layouts (brand marks never flip). */
const DIRECTIONAL: ReadonlySet<IconName> = new Set<IconName>(['railCollapse', 'railExpand', 'back', 'pageBack', 'pageForward']);

export type IconProps = { name: IconName; size?: IconSize; className?: string };

export function Icon({ name, size = 'sm', className }: IconProps) {
  const Glyph = GLYPHS[name];
  return (
    <Glyph
      aria-hidden="true"
      focusable="false"
      strokeWidth={ICON_STROKE}
      data-icon={name}
      data-directional={DIRECTIONAL.has(name) ? 'true' : undefined}
      className={cx(styles.root, styles[size], className)}
    />
  );
}
