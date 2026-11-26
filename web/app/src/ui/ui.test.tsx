import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Select,
  Spinner,
  Stack,
  Table,
  TextField,
  VisuallyHidden,
} from './index';

const html = (node: React.ReactElement) => renderToString(node);

describe('TextField', () => {
  it('wires label, hint and error to the input', () => {
    const out = html(<TextField id="f" label="Name" hint="Hint text" error="Bad value" required />);
    expect(out).toContain('<label for="f"');
    expect(out).toMatch(/<input[^>]*id="f"/);
    expect(out).toContain('aria-describedby="f-hint f-error"');
    expect(out).toContain('aria-invalid="true"');
    expect(out).toContain('id="f-error"');
    expect(out).toContain('dir="auto"');
    expect(out).toContain('required');
  });
  it('has no aria-invalid or describedby when valid and bare', () => {
    const out = html(<TextField id="f" label="Name" />);
    expect(out).not.toContain('aria-invalid');
    expect(out).not.toContain('aria-describedby');
  });
  it('labelHidden keeps the label for assistive technology only', () => {
    const out = html(<TextField id="h" label="Primary colour" labelHidden />);
    expect(out).toContain('<label for="h"');
    expect(out).toContain('data-label-hidden="true"');
    expect(out).toContain('Primary colour');
  });
  it('numeric fields keep LTR digits and a decimal keyboard', () => {
    const out = html(<TextField id="n" label="Amount" numeric />);
    expect(out).toContain('dir="ltr"');
    expect(out).toContain('inputMode="decimal"');
  });
});

describe('Select and Checkbox', () => {
  it('Select is a native select with the same wiring', () => {
    const out = html(
      <Select id="s" label="Terms" error="Pick one">
        <option value="a">A</option>
      </Select>,
    );
    expect(out).toMatch(/<select[^>]*id="s"/);
    expect(out).toContain('aria-invalid="true"');
    expect(out).toContain('aria-describedby="s-error"');
  });
  it('Checkbox links label and error', () => {
    const out = html(<Checkbox id="c" label="Agree" error="Required" />);
    expect(out).toContain('type="checkbox"');
    expect(out).toContain('<label for="c"');
    expect(out).toContain('aria-describedby="c-error"');
    expect(out).toContain('aria-invalid="true"');
  });
});

describe('Button', () => {
  it('loading disables and sets aria-busy, keeping the label', () => {
    const out = html(<Button loading>Saving</Button>);
    expect(out).toContain('disabled');
    expect(out).toContain('aria-busy="true"');
    expect(out).toContain('Saving');
    expect(out).toContain('type="button"');
  });
  it('idle button has no aria-busy', () => {
    expect(html(<Button>Go</Button>)).not.toContain('aria-busy');
  });
});

describe('Alert, Badge, Spinner', () => {
  it('chooses the role by tone', () => {
    expect(html(<Alert tone="danger">x</Alert>)).toContain('role="alert"');
    expect(html(<Alert tone="warning">x</Alert>)).toContain('role="alert"');
    expect(html(<Alert tone="info">x</Alert>)).toContain('role="status"');
    expect(html(<Alert tone="success">x</Alert>)).toContain('role="status"');
  });
  it('Badge carries text and hides its icon from assistive technology', () => {
    const out = html(<Badge tone="success" icon={<i />}>Paid</Badge>);
    expect(out).toContain('Paid');
    expect(out).toContain('aria-hidden="true"');
  });
  it('Spinner is named by its label prop, or hidden when decorative', () => {
    const named = html(<Spinner label="Loading" />);
    expect(named).toContain('role="status"');
    expect(named).toContain('Loading');
    expect(html(<Spinner decorative />)).toContain('aria-hidden="true"');
  });
});

describe('Table', () => {
  const out = html(
    <Table
      caption="Invoices"
      rows={[{ id: 'a', total: 5 }]}
      rowKey={(r) => r.id}
      columns={[
        { key: 'id', header: 'Number', rowHeader: true },
        { key: 'total', header: 'Total', numeric: true },
      ]}
    />,
  );
  it('has a caption, column scopes and a row header', () => {
    expect(out).toContain('<caption');
    expect(out).toContain('Invoices');
    expect(out.match(/scope="col"/g)).toHaveLength(2);
    expect(out).toContain('scope="row"');
  });
  it('can hide the caption visually but keep it', () => {
    const hidden = html(<Table caption="Cap" captionHidden rows={[]} rowKey={() => 0} columns={[]} />);
    expect(hidden).toContain('<caption');
    expect(hidden).toContain('Cap');
  });
});

describe('layout helpers', () => {
  it('Stack sets spacing through a unit multiple, not a pixel value', () => {
    const out = html(<Stack gap={3}>x</Stack>);
    expect(out).toContain('--stack-gap:3');
    expect(out).not.toMatch(/px/);
  });
  it('Card and VisuallyHidden render children', () => {
    expect(html(<Card as="section">c</Card>)).toContain('<section');
    expect(html(<VisuallyHidden>v</VisuallyHidden>)).toContain('>v<');
  });
});

describe('no colour or copy baked in', () => {
  const all = html(
    <div>
      <Button loading>b</Button>
      <TextField label="l" error="e" />
      <Alert tone="danger" title="t">a</Alert>
      <Badge tone="warning">w</Badge>
      <Spinner label="s" />
    </div>,
  );
  it('has no inline colour literals', () => {
    expect(all).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/);
    expect(all).not.toContain('style="color');
  });
  it('has no text other than what was passed in', () => {
    const text = all.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim().split(' ').sort();
    expect(text).toEqual(['a', 'b', 'e', 'l', 's', 't', 'w']);
  });
});

describe('stylesheets obey the token rules', () => {
  it('every .module.css in src/ui passes check-tokens-only', async () => {
    const scriptPath = join(process.cwd(), 'scripts', 'check-tokens-only.mjs');
    const mod = (await import(/* @vite-ignore */ scriptPath)) as {
      scanText: (text: string, file?: string) => Array<{ file: string; line: number; rule: string }>;
    };
    const files = readdirSync(__dirname).filter((f) => f.endsWith('.css'));
    expect(files.length).toBeGreaterThan(10);
    const found = files.flatMap((f) => mod.scanText(readFileSync(join(__dirname, f), 'utf8'), f));
    expect(found).toEqual([]);
  });
});
