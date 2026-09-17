# OpenAI 论文配图生成

本目录使用 Codex 自带的 OpenAI 图片生成 CLI，底层调用 OpenAI Image API。默认模型为 `gpt-image-2`，生成结果写入项目的 `output/imagegen/railway-paper/`。

## 为什么不让模型直接写中文架构标签

图片模型适合生成场景图、概念图和无文字的信息图底图，但正式论文中的中文模块名、箭头关系、指标数字和图号必须准确。推荐流程：

1. OpenAI 生成无文字的场景图或架构视觉底图。
2. 使用 LaTeX/TikZ 在底图上叠加中文标签、箭头、图例和编号。
3. ER 图、业务流程图、数据流图继续使用 TikZ 或 Mermaid，不交给图片模型生成文字。

## 已准备的图片

| 文件名 | 用途 | 适合放置章节 |
|---|---|---|
| `01-cover-railway-inspection.png` | 东南亚铁路无人机巡检主视觉 | 封面、执行摘要 |
| `02-multisource-data-collection.png` | 多源巡检数据采集生态 | 项目背景、总体方案 |
| `03-multimodal-system-architecture.png` | 六阶段系统架构无文字底图 | 总体解决方案 |
| `04-edge-cloud-deployment.png` | 现场边缘与中心平台部署 | 落地实施 |
| `05-bilingual-collaboration.png` | 中外运维人员双语协同 | 创新点、应用案例 |
| `06-value-closed-loop.png` | 采集、识别、复核、处置价值闭环 | 应用价值与成效 |

上述 6 张图片已于 2026 年 7 月 21 日完成生成并通过视觉检查，输出目录为 `output/imagegen/railway-paper/`。其中第 6 张将六阶段压缩成了五个主环节，正式使用时应按五阶段闭环标注，或单独重生成最终版。

## 调用前准备

在 OpenAI Platform 创建 API Key，然后只在当前 shell 或服务器密钥管理中设置。不要把 Key 写进仓库、`.env.example`、前端代码或论文。

```bash
export OPENAI_API_KEY="你的本地密钥"
```

## 先检查请求

dry-run 不联网、不计费、不需要 API Key：

```bash
python /home/xuelin/.codex/skills/.system/imagegen/scripts/image_gen.py generate-batch \
  --input games/imagegen/prompts.jsonl \
  --out-dir output/imagegen/railway-paper \
  --concurrency 3 \
  --dry-run
```

## 正式生成

```bash
python /home/xuelin/.codex/skills/.system/imagegen/scripts/image_gen.py generate-batch \
  --input games/imagegen/prompts.jsonl \
  --out-dir output/imagegen/railway-paper \
  --concurrency 3
```

当前 Linux 服务器无法直接连接 `api.openai.com`，但 Codex 已配置 OpenAI 兼容网关。需要在该服务器复现时，可仅在命令进程中复用 Codex 凭据，不把密钥写入仓库：

```bash
codex_key=$(jq -r '.OPENAI_API_KEY' ~/.codex/auth.json)
OPENAI_API_KEY="$codex_key" \
OPENAI_BASE_URL="http://codex.wlbclub.com" \
python /home/xuelin/.codex/skills/.system/imagegen/scripts/image_gen.py generate-batch \
  --input games/imagegen/prompts.jsonl \
  --out-dir output/imagegen/railway-paper \
  --concurrency 1
unset codex_key
```

采用单并发是因为高分辨率图片通常需要 1-4 分钟，且网关对并发图片请求更敏感。

提示词默认使用 `2048x1152`、`medium`，适合先挑选构图。选定图片后，将对应 JSONL 行的 `quality` 改成 `high` 并使用新的输出文件名重生成最终版本。

## 接入当前系统时的边界

当前 FastAPI/Vue 代码没有 OpenAI 集成。若要在前端增加“生成方案配图”按钮，必须由 FastAPI 后端读取 `OPENAI_API_KEY` 并调用 Image API，前端只提交提示词和查询任务状态。禁止从 Vue 环境变量或浏览器请求中暴露 API Key。
