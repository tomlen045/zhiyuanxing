#!/bin/bash
# 志愿星平台 + Cloudflare 固定隧道 自启脚本
export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH

# 1. MySQL容器(docker restart unless-stopped策略已兜底, 保险起见ensure)
docker start gaokao-mysql >/dev/null 2>&1

# 2. 应用服务(如未监听则启动)
if ! lsof -nP -iTCP:8504 -sTCP:LISTEN >/dev/null 2>&1; then
  cd "/Users/len/CodeBuddy/dx/志愿星"
  nohup /usr/bin/python3 app.py >> /tmp/zhiyuanxing_app.log 2>&1 &
fi

# 3. 固定隧道(如未运行则启动)
if ! pgrep -f "cloudflared tunnel run zhiyuanxing" >/dev/null 2>&1; then
  nohup /opt/homebrew/bin/cloudflared tunnel run zhiyuanxing >> /tmp/zhiyuanxing_tunnel.log 2>&1 &
fi
