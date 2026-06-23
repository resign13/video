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

- LuxVid_video
- seedance2渠道2（网页表单手动填 Key）
- grok-imagine-video-1.5-preview
- veo3.1-components
- veo3.1-fast-components
