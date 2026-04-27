import { Card, Empty, Space, Tag, Typography } from 'antd';
import type { ErrataFieldDiff } from './errataDiff';

const { Text } = Typography;

interface ErrataDiffPanelProps {
  fields: ErrataFieldDiff[];
}

function statusTag(status: ErrataFieldDiff['status']) {
  if (status === 'added') return <Tag color="success">新增</Tag>;
  if (status === 'removed') return <Tag color="error">删除</Tag>;
  return <Tag color="warning">修改</Tag>;
}

function rowColor(status: ErrataFieldDiff['status']) {
  if (status === 'added') return { background: '#f0fdf4', border: '#bbf7d0' };
  if (status === 'removed') return { background: '#fef2f2', border: '#fecaca' };
  return { background: '#fffbeb', border: '#fde68a' };
}

function renderSegments(field: ErrataFieldDiff) {
  if (field.status === 'removed') return <Text delete type="danger">{field.originalText}</Text>;
  return field.segments.map((segment, index) => {
    if (!segment.text) return null;
    if (segment.kind === 'added') {
      return <mark key={index} style={{ background: '#bbf7d0', color: '#166534', padding: '0 2px' }}>{segment.text}</mark>;
    }
    if (segment.kind === 'changed') {
      return <mark key={index} style={{ background: '#fde68a', color: '#92400e', padding: '0 2px' }}>{segment.text}</mark>;
    }
    return <span key={index}>{segment.text}</span>;
  });
}

export default function ErrataDiffPanel({ fields }: ErrataDiffPanelProps) {
  const visibleFields = fields.filter((field) => field.status !== 'changed' || field.originalText !== field.modifiedText);
  return (
    <Card
      size="small"
      title={
        <Space>
          <span>勘误差异（当前面）</span>
          <Tag color={visibleFields.length ? 'warning' : 'default'}>{visibleFields.length} 处变更</Tag>
        </Space>
      }
      style={{ marginBottom: 12, background: '#fffdf2', borderColor: '#fde68a' }}
    >
      {visibleFields.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前面暂未修改" />
      ) : (
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Text type="secondary">只显示和原始 .card 不一致的字段；JSON 编辑器会精确高亮新增或修改的字符串片段。</Text>
          {visibleFields.map((field) => {
            const colors = rowColor(field.status);
            return (
              <div
                key={field.key}
                style={{
                  border: `1px solid ${colors.border}`,
                  background: colors.background,
                  borderRadius: 10,
                  padding: '8px 10px',
                }}
              >
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <Space>
                    <Text strong>{field.label}</Text>
                    <Text type="secondary">{field.key}</Text>
                    {statusTag(field.status)}
                  </Space>
                  <Text type="secondary">原始：{field.originalText}</Text>
                  <Text>当前：{renderSegments(field)}</Text>
                </Space>
              </div>
            );
          })}
        </Space>
      )}
    </Card>
  );
}
