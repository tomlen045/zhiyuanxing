#!/bin/sh
# 志愿星 GitHub 发布（token 从钥匙串读，不回显）
set -e
cd "$(dirname "$0")"
GIT=/usr/bin/git

GH_TOKEN=$(security find-generic-password -s GH_TOKEN -w 2>/dev/null)
[ -n "$GH_TOKEN" ] || { echo "❌ 钥匙串没有 GH_TOKEN"; exit 1; }

# 1. 建仓（幂等）
echo "→ 创建 GitHub 仓库 tomlen045/zhiyuanxing ..."
HTTP=$(curl -s -o /tmp/gh_zx.json -w '%{http_code}' \
  -H "Authorization: token $GH_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/user/repos \
  -d '{"name":"zhiyuanxing","description":"志愿星 ZhiYuanXing - 高考志愿填报智能分析平台: 位次锚定冲稳保推荐/提分ROI规划/就业百科. 广东2022-2026全量真实数据(考试院官方). 纯前端可部署 zhiyuanxing.pages.dev","has_wiki":false,"private":false}')
if [ "$HTTP" = "201" ]; then echo "  ✅ 已创建"
elif [ "$HTTP" = "422" ]; then echo "  ℹ 已存在，跳过"
else echo "  ❌ HTTP $HTTP: $(head -c 200 /tmp/gh_zx.json)"; exit 1; fi

# 2. 推送（SSH 443 绕墙）
if ! "$GIT" remote get-url github >/dev/null 2>&1; then
  "$GIT" remote add github git@ssh.github.com:tomlen045/zhiyuanxing.git
fi
"$GIT" add -A
"$GIT" commit -m "志愿星: 位次锚定推荐 + 提分ROI + 就业百科 (广东2022-2026全量真实数据)" --allow-empty -q || true
echo "→ 推送 main ..."
GIT_SSH_COMMAND="ssh -p 443 -i $HOME/.ssh/id_ed25519_github -o StrictHostKeyChecking=accept-new" \
  "$GIT" push -u github main && echo "  ✅ 推送完成"

# 3. About 描述 + topics
curl -s -o /dev/null -X PATCH \
  -H "Authorization: token $GH_TOKEN" -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/tomlen045/zhiyuanxing \
  -d '{"description":"志愿星 - 高考志愿填报智能分析平台: 位次锚定冲稳保推荐/提分ROI规划/就业百科. 广东2022-2026全量真实数据. 在线: zhiyuanxing.pages.dev"}'
curl -s -o /dev/null -X PUT \
  -H "Authorization: token $GH_TOKEN" -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/tomlen045/zhiyuanxing/topics \
  -d '{"names":["gaokao","volunteer","education","mysql","cloudflare-pages","chinese","recommendation-engine"]}'
echo "  ✅ About/topics 已设置"
echo "🎉 https://github.com/tomlen045/zhiyuanxing"
