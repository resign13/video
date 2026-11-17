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

## 生成用量记录

网页顶部“用量记录”默认显示客易云，可按渠道、脱敏 Key 前后缀和上海时区日期筛选。
记录包含任务、使用 Key、设定视频秒数、渠道实际秒数，以及上游返回的 amount/cost/fee。
无费用返回时保存为空并显示“未返回”；零费用与未返回区分，币种或积分单位分别汇总。
模型中心的 amount 按渠道文档标为积分，未声明单位的旧接口保留“渠道原始单位”，不换算人民币。

记录保存在原 SQLite 的 generation_usage 表，与任务保存使用同一事务，以任务 ID 去重。
生成完成的响应在下载前记账，下载失败不影响用量记录；视频与普通任务的 5 小时清理不会删除该表。
保留期限为提交日起 3 个自然月，按上海时区计算月末，过期记录在定时清理时删除，查询立即排除过期记录。
完整 Key 仅在权限 0600 的服务器数据库保留原始快照，API 与网页仅返回脱敏值；重启恢复沿用已记录的任务 Key。
上线时仍在运行的旧任务会纳入记录，但旧代码未持久化 Key 的标为“旧任务 Key 未留存”，不使用当前配置推测。
本次无需新依赖；原视频生成、上传和下载接口继续使用原流程。验证：`python -m unittest discover -s backend/tests -v`。

## 当前保留模型

`sd_2.5_special_v1` 支持文字、多模态参考、首尾帧，以及 seed、generate_audio、
omni_reference_task_type、return_last_frame、tools。两端提供本地文件选择及折叠的生成参数设置。
按官方场景限制采用 9 张参考图、3 个视频（mp4/mov，单个最多 50 MB）、3 段音频（wav/mp3，单段最多 15 MB）；
视频/音频单段 2–15 秒，各自总时长不超过 15 秒，视频 24–60 fps。首尾帧与参考素材不可混用，音频不可单独输入。
所有素材使用 `model=sd_2.5` 提交素材库并等待 ACTIVE 后才提交任务；返回的尾帧地址在任务详情提供入口。
参数来源：https://docs.globalaiopc.com/api-reference/model-center/video-gen/sd_2.5_special_v1

MEAICC 新增 `mx-h3`、`sd-2.5-d1-720`，网页与桌面端共用现有 MEAICC Key 和 `/v1/videos` 流程：
- `mx-h3`：4–15 秒、768p、9:16；最多 9 张参考图片和 3 段音频，不提供参考视频和首尾帧输入。
- `sd-2.5-d1-720`：4–30 秒、720p；最多 30 张参考图片、10 个参考视频和 10 段音频，支持首尾帧；比例为 16:9、9:16、1:1、4:3、3:4、21:9。

两端新增独立的“渠道可用性”模块，读取 MEAICC 模型广场与客易云全部模型页面的公开数据，每 5 分钟刷新，可手动刷新和搜索。
`GET /api/channel-availability` 返回两家来源各自的更新时间和状态，`?refresh=1` 立即获取。
客易云只展示 `video_gen` 分组中的视频规格，保留有无参考视频、分辨率等区别，使用官方页面默认的公开价格档位；可用状态沿用官方接口的 available 或配置/启用标记。
成功率仅展示真实返回值，不采用客易云页面缺省的 100%；未提供的成功率、耗时显示“未提供”。
MEAICC 展示官方目录、24 小时成功率、样本数、平均耗时和最近结果；“官方在列”不代表每次生成都成功。
单个来源获取失败时标明未知或上次数据，其他来源继续显示。状态查询无需 Key，也不调用付费生成接口。
数据来源：https://api.meaicc.com/pricing 、https://www.globalaiopc.com/zh/default/allModels

网页与软件采用统一浅色工作台。网页左侧独立导航包含视频创作、用量记录和渠道可用性；
生成表单按模型参数、画面描述和参考素材分组，模型按渠道归类，素材空位默认只显示 3 个。
日志与高级参数按需展开，任务历史支持状态筛选；窄屏改为单列，生成输入在页面切换时保留。
软件右侧使用任务历史/详情页签，保存位置设置收起，视频、音频、首尾帧与高级参数继续使用原有本地文件流程。

软件端提供“软件更新”入口，发布版本由 `desktop_update.py` 的 `APP_VERSION` 标识。
重新打包 EXE 后执行 `python scripts/package_desktop_release.py`，生成 `dist.zip` 和 `output/desktop-release` 发布目录。
将其中的版本 ZIP 先上传到网页静态目录 `desktop/releases/`，最后更新 `desktop/latest.json`。
更新通过同一 HTTPS 站点下载，验证长度、ZIP 完整性和程序格式；只提取已知程序及说明文件。
辅助进程等待当前程序退出后在原目录替换、保留前一版并重启；替换/启动失败恢复原文件。
生成任务运行中不执行更新，保存的 Key 和下载路径沿用 Windows 本地设置。初次需手动使用带更新入口的新版。

MEAICC 原有 `sd-2.5-d1`、`sd-2.5-d2`、`sd-2.5-d3`，均复用 `MEAICC_API_KEY` 和 `/v1/videos` 流程。
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
