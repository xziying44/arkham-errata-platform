import { Card, Image, List, Space, Tag, Typography } from 'antd';
import type { PublishArtifact } from '../../types';

interface SheetPreviewPanelProps {
  artifacts: PublishArtifact[];
}

function artifactImageUrl(artifact: PublishArtifact) {
  if (!artifact.public_url) return undefined;
  const version = artifact.checksum || artifact.updated_at || artifact.id;
  return `${artifact.public_url}?v=${encodeURIComponent(String(version))}`;
}

export default function SheetPreviewPanel({ artifacts }: SheetPreviewPanelProps) {
  const sheets = artifacts.filter(
    (artifact) =>
      (artifact.kind === 'sheet_front' || artifact.kind === 'sheet_back') &&
      (artifact.status === 'active' || artifact.status === 'confirmed'),
  );
  if (sheets.length === 0) return <Typography.Text type="secondary">还没有生成精灵图</Typography.Text>;

  return (
    <List
      grid={{ gutter: 12, column: 2 }}
      dataSource={sheets}
      renderItem={(artifact) => (
        <List.Item>
          <Card
            size="small"
            title={String(artifact.metadata.sheet_name || artifact.kind)}
            extra={<Tag color={artifact.status === 'confirmed' ? 'success' : 'processing'}>{artifact.status}</Tag>}
          >
            <Space direction="vertical" style={{ width: '100%' }}>
              {artifact.public_url && <Image src={artifactImageUrl(artifact)} style={{ maxHeight: 240, objectFit: 'contain' }} />}
              <Typography.Text type="secondary">卡牌：{Array.isArray(artifact.metadata.card_ids) ? artifact.metadata.card_ids.join(', ') : '-'}</Typography.Text>
              <Typography.Text copyable>{artifact.checksum || ''}</Typography.Text>
            </Space>
          </Card>
        </List.Item>
      )}
    />
  );
}
