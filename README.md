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

`sd_2.5_special_v1` 支持文字、多模态参考、首尾帧，以及 seed、generate_audio、
omni_reference_task_type、return_last_frame、tools。两端提供本地文件选择及折叠的生成参数设置。
按官方场景限制采用 9 张参考图、3 个视频（mp4/mov，单个最多 50 MB）、3 段音频（wav/mp3，单段最多 15 MB）；
视频/音频单段 2–15 秒，各自总时长不超过 15 秒，视频 24–60 fps。首尾帧与参考素材不可混用，音频不可单独输入。
所有素材使用 `model=sd_2.5` 提交素材库并等待 ACTIVE 后才提交任务；返回的尾帧地址在任务详情提供入口。
参数来源：https://docs.globalaiopc.com/api-reference/model-center/video-gen/sd_2.5_special_v1

MEAICC 新增 `sd-2.5-d1`、`sd-2.5-d2`、`sd-2.5-d3`，均复用 `MEAICC_API_KEY` 和 `/v1/videos` 流程。
三者支持 5–30 秒、最多 30 张参考图及最多 10 个参考音频；D2/D3 另外支持最多 10 个参考视频。
D1/D3 输出 720p，D2 输出 480p，支持 16:9、9:16、1:1；D1 提示词上限为 15000 字符。
附加素材选择本地文件，默认收起，按 `input.media` 的图片、音频、视频、首尾帧类型提交。

`sd-2.5-c1` 仅支持 30 秒视频，使用 MEAICC 渠道（默认 `https://api.meaicc.com`），复用 `MEAICC_API_KEY` 和现有 `/v1/videos` 提交、轮询与并发排队流程。

客易云模型中心新增：
- `videos_2.5_30_10_10_c5`：5–30 秒，720p，支持 8 种画幅比例。
- `videos_30_10_10_c3`：4–30 秒，480p/720p，支持 16:9、9:16、1:1，支持可选首尾帧图片上传。

两个模型复用 `LUXVID_BASE_URL` 和 `LUXVID_API_KEY`，允许纯文本生成或最多 30 张参考图。上传图片复用 ImgBB 图床；参考视频、音频和首尾帧区域默认收起，点击展开后选择本地文件，视频和音频各最多 10 个，首尾帧各 1 张。视频单个最多 128 MB、音频 32 MB、首尾帧图片 20 MB；浏览器限制文件总计 510 MB，为 512 MB 的服务端请求限制留出表单开销。附加文件保存到任务目录，服务端通过 `PUBLIC_WEB_BASE_URL` 生成渠道可读取的资源地址，前端无需填写链接。重新提交会复制参考文件，复用配置会还原文件。任务通过 `/v2/model-center/tasks` 提交和查询，完成后自动下载保存视频。

离线验证（不调用付费生成接口）：`python -m unittest discover -s backend/tests -v`。

- LuxVid_video
- seedance2.5
- grok-imagine-video-1.5-preview
- veo3.1-components
- veo3.1-fast-components
- videos_stable_fast
- veo_3_1_pro_stable
- veo_3_1_fast
