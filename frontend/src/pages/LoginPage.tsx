import { useState } from 'react';
import { Button, Card, Form, Input, Typography } from 'antd';

type LoginPageProps = {
  loading: boolean;
  errorMessage?: string;
  onSubmit: (username: string, password: string) => Promise<void> | void;
};

export function LoginPage({ loading, errorMessage, onSubmit }: LoginPageProps) {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');

  const handleSubmit = async () => {
    await onSubmit(username.trim(), password);
  };

  return (
    <div className="login-page">
      <Card className="panel-card login-card">
        <div className="login-card__badge">/login</div>
        <Typography.Title level={2} className="login-card__title">
          系统登录
        </Typography.Title>
        <Typography.Paragraph className="login-card__desc">
          首次进入需先完成身份校验，登录成功后可访问预案生成、图谱溯源、模板查看和格式优化页面。
        </Typography.Paragraph>
        <Form layout="vertical" onFinish={handleSubmit}>
          <Form.Item label="用户名" required>
            <Input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="请输入用户名" />
          </Form.Item>
          <Form.Item label="密码" required>
            <Input.Password
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="请输入密码"
              onPressEnter={handleSubmit}
            />
          </Form.Item>
          {errorMessage ? (
            <Typography.Text type="danger" className="login-card__error">
              {errorMessage}
            </Typography.Text>
          ) : null}
          <Button type="primary" htmlType="submit" loading={loading} block>
            登录
          </Button>
        </Form>
      </Card>
    </div>
  );
}
