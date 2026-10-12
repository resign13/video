# AI Video Studio Web

Vue3 + Flask 视频生成网页端。

## 目录

```text
web/
  backend/    Flask API 后端
  frontend/   Vue3 + Vite 前端
  deploy/     Linux 服务器部署配置模板
  scripts/    本地/服务器部署脚本
```

## 本地开发

后端：

```powershell
cd web/backend
python -m pip install -r requirements.txt
copy .env.example .env
python app.py
```

前端：

```powershell
cd web/frontend
npm install
npm run dev
```

默认地址：
- 前端开发服务：http://127.0.0.1:5173
- 后端接口：http://127.0.0.1:5000

## 生产部署

生产环境建议：Nginx 静态托管前端 `dist`，反向代理 `/api/` 到 Flask/Gunicorn。

```bash
cd /opt/video
bash scripts/server_deploy.sh
```

部署脚本会：
1. 创建 Python venv 并安装后端依赖
2. 构建 Vue 前端
3. 安装/重启 systemd 服务 `video-web.service`
4. 写入 Nginx 站点配置并重载 Nginx

## 当前保留模型

客易云模型中心新增：
- `videos_2.5_30_10_10_c5`：5–30 秒，720p，支持 8 种画幅比例。
- `videos_30_10_10_c3`：4–30 秒，480p/720p，支持 16:9、9:16、1:1，支持可选首尾帧图片链接。

两个模型复用 `LUXVID_BASE_URL` 和 `LUXVID_API_KEY`，允许纯文本生成或最多 30 张参考图。上传图片复用 ImgBB 图床；可在网页展开可选输入，填写参考视频和音频的公开链接（各最多 10 个）。任务通过 `/v2/model-center/tasks` 提交和查询，完成后自动下载保存视频。

离线验证（不调用付费生成接口）：`python -m unittest discover -s backend/tests -v`。

- LuxVid_video
- seedance2.5
- grok-imagine-video-1.5-preview
- veo3.1-components
- veo3.1-fast-components
- videos_stable_fast
- veo_3_1_pro_stable
- veo_3_1_fast
