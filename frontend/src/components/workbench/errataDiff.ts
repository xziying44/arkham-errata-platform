export type DiffSegmentKind = 'equal' | 'added' | 'removed' | 'changed';

export interface DiffSegment {
  kind: DiffSegmentKind;
  text: string;
}

export interface ErrataFieldDiff {
  key: string;
  label: string;
  originalText: string;
  modifiedText: string;
  status: 'added' | 'removed' | 'changed';
  segments: DiffSegment[];
}

export interface ErrataDiffSummary {
  changedFields: ErrataFieldDiff[];
  changedFieldKeys: Set<string>;
}

export interface JsonStringDecoration {
  key: string;
  kind: Exclude<DiffSegmentKind, 'equal' | 'removed'>;
  startOffset: number;
  endOffset: number;
}

const fieldLabels: Record<string, string> = {
  name: '名称',
  subtitle: '副名称',
  traits: '特性',
  body: '正文',
  flavor: '风味文本',
};

const preferredFieldOrder = ['name', 'subtitle', 'traits', 'body', 'flavor'];

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) return JSON.stringify(value.map((item) => normalizeValue(item)));
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const normalized = Object.fromEntries(
      Object.keys(record)
        .sort()
        .map((key) => [key, normalizeValue(record[key])]),
    );
    return JSON.stringify(normalized);
  }
  return JSON.stringify(value ?? null);
}

function normalizeValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map((item) => normalizeValue(item));
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    return Object.fromEntries(Object.keys(record).sort().map((key) => [key, normalizeValue(record[key])]));
  }
  return value;
}

function displayValue(value: unknown): string {
  if (Array.isArray(value)) return value.map((item) => displayValue(item)).join('，');
  if (value === null || value === undefined || value === '') return '无';
  if (typeof value === 'object') return JSON.stringify(normalizeValue(value), null, 2);
  return String(value);
}

function commonPrefixLength(left: string, right: string): number {
  let index = 0;
  while (index < left.length && index < right.length && left[index] === right[index]) {
    index += 1;
  }
  return index;
}

function commonSuffixLength(left: string, right: string, prefixLength: number): number {
  let length = 0;
  while (
    length + prefixLength < left.length
    && length + prefixLength < right.length
    && left[left.length - 1 - length] === right[right.length - 1 - length]
  ) {
    length += 1;
  }
  return length;
}

function stringSegments(originalText: string, modifiedText: string): DiffSegment[] {
  if (originalText === modifiedText) return [{ kind: 'equal', text: modifiedText }];
  const prefixLength = commonPrefixLength(originalText, modifiedText);
  const suffixLength = commonSuffixLength(originalText, modifiedText, prefixLength);
  const segments: DiffSegment[] = [];
  const prefix = modifiedText.slice(0, prefixLength);
  const removed = originalText.slice(prefixLength, originalText.length - suffixLength);
  const added = modifiedText.slice(prefixLength, modifiedText.length - suffixLength);
  const suffix = suffixLength > 0 ? modifiedText.slice(modifiedText.length - suffixLength) : '';
  if (prefix) segments.push({ kind: 'equal', text: prefix });
  if (removed && added) segments.push({ kind: 'changed', text: added });
  else if (added) segments.push({ kind: 'added', text: added });
  else if (removed) segments.push({ kind: 'removed', text: removed });
  if (suffix) segments.push({ kind: 'equal', text: suffix });
  return segments;
}

function statusForValues(originalValue: unknown, modifiedValue: unknown): ErrataFieldDiff['status'] {
  const originalEmpty = originalValue === undefined || originalValue === null || originalValue === '';
  const modifiedEmpty = modifiedValue === undefined || modifiedValue === null || modifiedValue === '';
  if (originalEmpty && !modifiedEmpty) return 'added';
  if (!originalEmpty && modifiedEmpty) return 'removed';
  return 'changed';
}

function sortedKeys(original: Record<string, unknown>, modified: Record<string, unknown>): string[] {
  const keys = new Set([...Object.keys(original), ...Object.keys(modified)]);
  return [...keys].sort((left, right) => {
    const leftIndex = preferredFieldOrder.indexOf(left);
    const rightIndex = preferredFieldOrder.indexOf(right);
    if (leftIndex !== -1 || rightIndex !== -1) {
      return (leftIndex === -1 ? 1000 : leftIndex) - (rightIndex === -1 ? 1000 : rightIndex);
    }
    return left.localeCompare(right);
  });
}

export function buildErrataDiff(
  original: Record<string, unknown> = {},
  modified: Record<string, unknown> = {},
): ErrataDiffSummary {
  const changedFields = sortedKeys(original, modified)
    .filter((key) => stableStringify(original[key]) !== stableStringify(modified[key]))
    .map<ErrataFieldDiff>((key) => {
      const originalText = displayValue(original[key]);
      const modifiedText = displayValue(modified[key]);
      return {
        key,
        label: fieldLabels[key] || key,
        originalText,
        modifiedText,
        status: statusForValues(original[key], modified[key]),
        segments: stringSegments(originalText === '无' ? '' : originalText, modifiedText === '无' ? '' : modifiedText),
      };
    });
  return {
    changedFields,
    changedFieldKeys: new Set(changedFields.map((item) => item.key)),
  };
}

function offsetToPosition(text: string, offset: number): { lineNumber: number; column: number } {
  const before = text.slice(0, offset);
  const lines = before.split('\n');
  return {
    lineNumber: lines.length,
    column: lines[lines.length - 1].length + 1,
  };
}

export function offsetRangeToMonacoRange(text: string, startOffset: number, endOffset: number) {
  return {
    ...offsetToPosition(text, startOffset),
    endLineNumber: offsetToPosition(text, endOffset).lineNumber,
    endColumn: offsetToPosition(text, endOffset).column,
  };
}

interface JsonStringValueRange {
  startOffset: number;
  endOffset: number;
  decodedText: string;
  decodedToRawOffsets: number[];
}

function readEscapedChar(json: string, offset: number): { text: string; endOffset: number } {
  const escaped = json[offset + 1];
  if (escaped === 'n') return { text: '\n', endOffset: offset + 2 };
  if (escaped === 'r') return { text: '\r', endOffset: offset + 2 };
  if (escaped === 't') return { text: '\t', endOffset: offset + 2 };
  if (escaped === 'b') return { text: '\b', endOffset: offset + 2 };
  if (escaped === 'f') return { text: '\f', endOffset: offset + 2 };
  if (escaped === 'u') {
    const hex = json.slice(offset + 2, offset + 6);
    return { text: String.fromCharCode(Number.parseInt(hex, 16)), endOffset: offset + 6 };
  }
  return { text: escaped || '', endOffset: offset + 2 };
}

function findJsonStringValueRange(json: string, key: string): JsonStringValueRange | null {
  const keyPattern = new RegExp(`"${key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"\\s*:\\s*"`, 'u');
  const match = keyPattern.exec(json);
  if (!match) return null;
  const startOffset = (match.index || 0) + match[0].length;
  let offset = startOffset;
  let decodedText = '';
  const decodedToRawOffsets: number[] = [];
  while (offset < json.length) {
    const char = json[offset];
    if (char === '\\') {
      const escapedChar = readEscapedChar(json, offset);
      decodedToRawOffsets.push(offset);
      decodedText += escapedChar.text;
      offset = escapedChar.endOffset;
      continue;
    }
    if (char === '"') {
      decodedToRawOffsets.push(offset);
      return { startOffset, endOffset: offset, decodedText, decodedToRawOffsets };
    }
    decodedToRawOffsets.push(offset);
    decodedText += char;
    offset += 1;
  }
  return null;
}

function rawRangeFromDecodedRange(valueRange: JsonStringValueRange, decodedStart: number, decodedEnd: number) {
  const startOffset = valueRange.decodedToRawOffsets[decodedStart] ?? valueRange.endOffset;
  const endOffset = valueRange.decodedToRawOffsets[decodedEnd] ?? valueRange.endOffset;
  return { startOffset, endOffset };
}

export function buildJsonStringDecorations(json: string, fields: ErrataFieldDiff[]): JsonStringDecoration[] {
  const decorations: JsonStringDecoration[] = [];
  for (const field of fields) {
    const valueRange = findJsonStringValueRange(json, field.key);
    if (!valueRange) continue;
    let decodedCursor = 0;
    for (const segment of field.segments) {
      if (segment.kind === 'removed') continue;
      const decodedStart = decodedCursor;
      const decodedEnd = decodedCursor + segment.text.length;
      const { startOffset, endOffset } = rawRangeFromDecodedRange(valueRange, decodedStart, decodedEnd);
      if (segment.kind !== 'equal' && endOffset > startOffset) {
        decorations.push({ key: field.key, kind: segment.kind, startOffset, endOffset });
      }
      decodedCursor = decodedEnd;
    }
  }
  return decorations;
}
