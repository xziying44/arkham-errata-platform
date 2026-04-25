import { Row, Col, Image, Empty, Typography } from 'antd';

const { Text } = Typography;

interface Props {
  englishImageUrl: string | null;
  chineseImageUrl: string | null;
  previewImageUrl: string | null;
}

/** 三栏卡牌对比视图：英文 TTS 卡图 | 中文 TTS 卡图（当前）| 修改后预览 */
export default function CardComparison({ englishImageUrl, chineseImageUrl, previewImageUrl }: Props) {
  return (
    <Row gutter={16}>
      <Col span={8}>
        <div style={{ textAlign: 'center' }}>
          <Text strong>英文 TTS 卡图</Text>
          {englishImageUrl ? (
            <Image
              src={englishImageUrl}
              style={{ width: '100%' }}
              fallback="data:image/png;base64,iVBORw0KGgo="
            />
          ) : (
            <Empty description="暂无英文卡图" />
          )}
        </div>
      </Col>
      <Col span={8}>
        <div style={{ textAlign: 'center' }}>
          <Text strong>中文 TTS 卡图（当前）</Text>
          {chineseImageUrl ? (
            <Image src={chineseImageUrl} style={{ width: '100%' }} />
          ) : (
            <Empty description="暂无中文卡图" />
          )}
        </div>
      </Col>
      <Col span={8}>
        <div style={{ textAlign: 'center' }}>
          <Text strong>修改后预览</Text>
          {previewImageUrl ? (
            <Image src={previewImageUrl} style={{ width: '100%' }} />
          ) : (
            <Empty description="点击预览按钮生成" />
          )}
        </div>
      </Col>
    </Row>
  );
}
