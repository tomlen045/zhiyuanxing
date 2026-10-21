#!/bin/bash
# 高考志愿平台 · MySQL 8 专用容器引导脚本（独立DB，独立数据卷）
set -x
PW="${MYSQL_PASSWORD:?请先 export MYSQL_PASSWORD=你的MySQL密码}"

docker pull docker.m.daocloud.io/library/mysql:8.0 || exit 1
docker tag docker.m.daocloud.io/library/mysql:8.0 gaokao-mysql:8.0

docker rm -f gaokao-mysql 2>/dev/null

docker run -d \
  --name gaokao-mysql \
  --restart unless-stopped \
  -p 127.0.0.1:3306:3306 \
  -v gaokao-mysql-data:/var/lib/mysql \
  -e MYSQL_ROOT_PASSWORD="$PW" \
  gaokao-mysql:8.0 \
  --character-set-server=utf8mb4 \
  --collation-server=utf8mb4_unicode_ci || exit 1

echo '--- waiting for mysql healthy ---'
ok=0
for i in $(seq 1 60); do
  # 注意: mysqladmin ping 在初始化临时服务器阶段即使密码未生效也返回0, 会假阳性
  # 必须用带密码的真实 SELECT 1 判定就绪
  if docker exec gaokao-mysql mysql -uroot -p"$PW" -e 'SELECT 1' >/dev/null 2>&1; then
    ok=1; break
  fi
  sleep 5
done
[ "$ok" = 1 ] || { echo 'MYSQL FAILED TO BECOME HEALTHY'; exit 1; }

echo '--- loading 001_init.sql ---'
docker exec -i gaokao-mysql mysql -uroot -p"$PW" < "/Users/len/CodeBuddy/dx/志愿星/001_init.sql"

echo '--- tables ---'
docker exec gaokao-mysql mysql -uroot -p"$PW" -e "SHOW TABLES; SELECT COUNT(*) AS provinces FROM gaokao_platform.province;" 2>/dev/null

echo 'BOOTSTRAP_DONE'
