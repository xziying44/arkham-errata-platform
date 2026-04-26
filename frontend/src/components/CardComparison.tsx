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
              <div style={{ marginTop: 8, minHeight: 320, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                {item.url ? (
                  <div
                    style={{
                      width: 360,
                      height: 260,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      overflow: 'hidden',
                    }}
                  >
                    <Image
                      src={item.url}
                      preview={{ src: item.url }}
                      style={{
                        width: item.rotateCounterClockwise ? 260 : 360,
                        height: item.rotateCounterClockwise ? 360 : 260,
                        maxWidth: 'none',
                        objectFit: 'contain',
                        transform: item.rotateCounterClockwise ? 'rotate(-90deg)' : undefined,
                      }}
                    />
                  </div>
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
