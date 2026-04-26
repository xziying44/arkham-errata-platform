import type { ReactNode } from 'react';
import { Card, Col, Empty, Image, Row, Typography } from 'antd';

const { Text } = Typography;

export interface ImageSlot {
  key: string;
  title: string;
  url: string | null;
  error?: string | null;
  footer?: ReactNode;
  horizontal?: boolean;
  rotateCounterClockwise?: boolean;
}

interface Props {
  images: ImageSlot[];
}

/** 六图卡牌对比视图：英文/中文参考只读，本地渲染展示预发布结果 */
export default function CardComparison({ images }: Props) {
  const safeImages = images ?? [];
  return (
    <Image.PreviewGroup>
      <Row gutter={[12, 12]}>
        {safeImages.map((item) => (
          <Col span={8} key={item.key}>
            <Card size="small" bodyStyle={{ padding: 8, textAlign: 'center' }}>
              <Text strong>{item.title}</Text>
              <div
                style={{
                  marginTop: 8,
                  minHeight: item.horizontal ? 340 : 260,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  overflow: 'hidden',
                }}
              >
                {item.url ? (
                  <Image
                    src={item.url}
                    style={{
                      width: item.horizontal ? '82%' : '50%',
                      minWidth: item.horizontal ? 260 : 160,
                      maxWidth: item.horizontal ? 440 : 260,
                      transform: item.rotateCounterClockwise ? 'rotate(-90deg)' : undefined,
                    }}
                  />
                ) : (
                  <Empty description={item.error || '暂无图片'} />
                )}
              </div>
              {item.footer ? <div style={{ marginTop: 8 }}>{item.footer}</div> : null}
            </Card>
          </Col>
        ))}
      </Row>
    </Image.PreviewGroup>
  );
}
