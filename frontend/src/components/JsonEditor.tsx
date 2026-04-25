import Editor from '@monaco-editor/react';

interface Props {
  value: string;
  onChange: (value: string) => void;
  height?: string;
}

/** 基于 Monaco Editor 的 JSON 编辑器 */
export default function JsonEditor({ value, onChange, height = '600px' }: Props) {
  const safeJson = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  return (
    <Editor
      height={height}
      language="json"
      theme="vs-light"
      value={safeJson}
      onChange={(v) => onChange(v || '')}
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
