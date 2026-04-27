import { useEffect, useRef } from 'react';
import Editor from '@monaco-editor/react';

export interface JsonEditorDecoration {
  startLineNumber: number;
  startColumn: number;
  endLineNumber: number;
  endColumn: number;
  className: string;
  hoverMessage?: string;
}

interface Props {
  value: string;
  onChange: (value: string) => void;
  height?: string;
  decorations?: JsonEditorDecoration[];
}

/** 基于 Monaco Editor 的 JSON 编辑器 */
export default function JsonEditor({ value, onChange, height = '600px', decorations = [] }: Props) {
  const editorRef = useRef<any>(null);
  const monacoRef = useRef<any>(null);
  const decorationCollectionRef = useRef<any>(null);
  const safeJson = typeof value === 'string' ? value : JSON.stringify(value, null, 2);

  useEffect(() => {
    if (!editorRef.current || !monacoRef.current) return;
    const nextDecorations = decorations.map((item) => ({
      range: new monacoRef.current.Range(
        item.startLineNumber,
        item.startColumn,
        item.endLineNumber,
        item.endColumn,
      ),
      options: {
        inlineClassName: item.className,
        hoverMessage: item.hoverMessage ? { value: item.hoverMessage } : undefined,
      },
    }));
    if (!decorationCollectionRef.current) {
      decorationCollectionRef.current = editorRef.current.createDecorationsCollection(nextDecorations);
    } else {
      decorationCollectionRef.current.set(nextDecorations);
    }
  }, [decorations, safeJson]);

  return (
    <Editor
      height={height}
      language="json"
      theme="vs-light"
      value={safeJson}
      onChange={(v) => onChange(v || '')}
      onMount={(editor, monaco) => {
        editorRef.current = editor;
        monacoRef.current = monaco;
        decorationCollectionRef.current = editor.createDecorationsCollection([]);
      }}
      options={{
        minimap: { enabled: false },
        fontSize: 13,
        lineNumbers: 'on',
        scrollBeyondLastLine: false,
        wordWrap: 'on',
      }}
    />
  );
}
