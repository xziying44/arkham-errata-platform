import { useEffect, useMemo } from 'react';
import { Alert, Form, Input, Space, Typography } from 'antd';

const { Text } = Typography;

interface CardTextFieldsEditorProps {
  selectedFace: string;
  jsonByFace: Record<string, string>;
  onFaceJsonChange: (face: string, value: string) => void;
}

type CardTextFormValues = {
  name?: string;
  subtitle?: string;
  traits?: string;
  body?: string;
  flavor?: string;
};

function parseJson(value?: string): Record<string, unknown> | null {
  if (!value) return {};
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function textValue(value: unknown): string {
  if (Array.isArray(value)) return value.join('，');
  if (value === null || value === undefined) return '';
  return String(value);
}

function traitsToJsonValue(value?: string): string[] | undefined {
  const items = (value || '')
    .split(/[，,、\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
  return items.length ? items : undefined;
}

function setOptionalText(target: Record<string, unknown>, key: string, value?: string) {
  const normalized = (value || '').trim();
  if (normalized) target[key] = normalized;
  else delete target[key];
}

function updateFaceJson(
  face: string,
  jsonByFace: Record<string, string>,
  updates: Partial<CardTextFormValues>,
  onFaceJsonChange: (face: string, value: string) => void,
) {
  const current = parseJson(jsonByFace[face]);
  if (!current) return;
  const next = { ...current };
  if ('name' in updates) setOptionalText(next, 'name', updates.name);
  if ('subtitle' in updates) setOptionalText(next, 'subtitle', updates.subtitle);
  if ('body' in updates) setOptionalText(next, 'body', updates.body);
  if ('flavor' in updates) setOptionalText(next, 'flavor', updates.flavor);
  if ('traits' in updates) {
    const traits = traitsToJsonValue(updates.traits);
    if (traits) next.traits = traits;
    else delete next.traits;
  }
  onFaceJsonChange(face, JSON.stringify(next, null, 2));
}

export default function CardTextFieldsEditor({ selectedFace, jsonByFace, onFaceJsonChange }: CardTextFieldsEditorProps) {
  const [form] = Form.useForm<CardTextFormValues>();
  const selectedContent = useMemo(() => parseJson(jsonByFace[selectedFace]), [jsonByFace, selectedFace]);
  const hasInvalidJson = selectedContent === null;

  useEffect(() => {
    if (!selectedContent) return;
    form.setFieldsValue({
      name: textValue(selectedContent.name),
      subtitle: textValue(selectedContent.subtitle),
      traits: textValue(selectedContent.traits),
      body: textValue(selectedContent.body),
      flavor: textValue(selectedContent.flavor),
    });
  }, [form, selectedContent]);

  const handleValuesChange = (changed: Partial<CardTextFormValues>, values: CardTextFormValues) => {
    const selectedUpdates: Partial<CardTextFormValues> = {};
    for (const key of ['name', 'subtitle', 'traits', 'body', 'flavor'] as const) {
      if (key in changed) selectedUpdates[key] = values[key];
    }
    if (Object.keys(selectedUpdates).length > 0) {
      updateFaceJson(selectedFace, jsonByFace, selectedUpdates, onFaceJsonChange);
    }
  };

  return (
    <Space direction="vertical" size={8} style={{ width: '100%', marginBottom: 12 }}>
      <Text type="secondary">常用文本字段会和下方 JSON 实时同步；复杂字段仍可直接编辑 JSON。</Text>
      {hasInvalidJson && <Alert type="warning" showIcon message="当前 JSON 格式有误，修正后表单会自动恢复同步。" />}
      <Form
        form={form}
        layout="vertical"
        disabled={hasInvalidJson}
        onValuesChange={handleValuesChange}
      >
        <Form.Item label="名称" name="name" style={{ marginBottom: 10 }}>
          <Input placeholder="name" />
        </Form.Item>
        <Form.Item label="副名称" name="subtitle" style={{ marginBottom: 10 }}>
          <Input placeholder="subtitle" />
        </Form.Item>
        <Form.Item label="特性" name="traits" style={{ marginBottom: 10 }}>
          <Input placeholder="多个特性可用逗号、顿号或换行分隔" />
        </Form.Item>
        <Form.Item label="正文" name="body" style={{ marginBottom: 10 }}>
          <Input.TextArea autoSize={{ minRows: 3, maxRows: 8 }} placeholder="body" />
        </Form.Item>
        <Form.Item label="风味文本" name="flavor" style={{ marginBottom: 10 }}>
          <Input.TextArea autoSize={{ minRows: 2, maxRows: 6 }} placeholder="flavor" />
        </Form.Item>
      </Form>
    </Space>
  );
}
