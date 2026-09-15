# Product Video Remake - Codex Skill

> 这是一个可安装到 OpenAI Codex 的 Skill，不是独立的视频生成应用。

`product-video-remake` 是一个用于快速复刻爆款或高表现商品视频脚本的离线编译 Skill。它分析用户有权使用的参考视频，提取分镜顺序、节奏、动作、运镜、声音节点以及人物、商品和场景变化，再结合目标商品图片，生成可直接用于视频模型的复刻脚本提示词、请求包和验收清单。

它适合电商运营、短视频创作者和 AIGC 视频团队快速研究成熟视频结构，并把原本依赖人工逐帧观察的工作整理成可验证的镜头时间线。该项目不会上传素材、调用视频生成 API、轮询任务或下载生成结果；参考视频只用于本地分析，模型请求只应包含独立成片提示词和目标商品图片。

## 安装到 Codex

最简单的安装方式是在 Codex 中发送：

```text
请从 https://github.com/ckc1360623/product-video-remake 安装 product-video-remake Skill
```

也可以在 Windows PowerShell 中手动克隆到 Codex Skills 目录：

```powershell
git clone https://github.com/ckc1360623/product-video-remake.git "$env:USERPROFILE\.codex\skills\product-video-remake"
```

安装后，在新的 Codex 对话中通过 `$product-video-remake` 调用，例如：

```text
使用 $product-video-remake 分析这个参考视频和商品图，生成高保真复刻脚本提示词及请求包。
```

## 主要能力

- 将爆款或高表现商品视频拆解为完整的视频脚本提示词，而不是只概括故事大意。
- 使用 FFmpeg/ffprobe 提取媒体信息、密集帧、切镜证据、总览图和分析音频。
- 保留镜头顺序、动作、节奏、人物和场景状态变化。
- 编译标准单次请求或高镜头密度的分段请求包。
- 在提交前验证请求不包含参考视频、分析音频、本地路径和内部时间线编号。
- 对用户回传的视频检查时长、画幅和主要切点，并生成语义验收清单。

## 环境要求

- Python 3.10 或更高版本
- FFmpeg 和 ffprobe，可通过命令行直接调用，或通过脚本参数指定路径
- Skill 本身没有第三方 Python 运行时依赖

## 快速检查

在项目根目录运行：

```powershell
python -X utf8 -m unittest discover -s tests -v
python -X utf8 scripts/check_release_safety.py
```

准备本地视频分析包：

```powershell
python -X utf8 scripts/prepare_analysis_pack.py `
  --input "C:\path\to\reference.mp4" `
  --output-dir "C:\path\outside-this-repository\analysis-pack"
```

编译已经准备好的商品画像和 Video DNA：

```powershell
python -X utf8 scripts/run_pipeline.py `
  --product-profile "C:\path\to\product-profile.json" `
  --video-dna "C:\path\to\source-video-dna.json" `
  --output-dir "C:\path\outside-this-repository\outputs" `
  --generation-mode auto
```

完整工作流和数据结构分别见 [`references/workflow.md`](references/workflow.md) 与 [`references/data-contracts.md`](references/data-contracts.md)。Codex Skill 的入口说明位于 [`SKILL.md`](SKILL.md)。

## 隐私与数据边界

分析清单和编译产物可能包含本地绝对路径、商品文件名以及用户素材的派生信息。分析缓存还会保存参考视频抽帧、切镜画面和音频，因此它们可能暴露人物、声音、住所、平台水印、商品包装或客户商业信息。

- 始终把运行输出写到仓库外部，或写入已经被 `.gitignore` 排除的 `outputs/`、`analysis-pack/` 等目录。
- 提交前运行 `scripts/check_release_safety.py`，并使用 `git status --short` 人工检查待提交文件。
- 不要提交参考视频、商品原图、抽帧、音频、联系表、生成结果、API 凭证或真实客户数据。
- 不要从包含历史客户素材的旧仓库直接公开 Git 历史。建议使用这份清理后的源码创建全新仓库。
- 如果敏感文件曾经进入 Git 历史，仅删除当前文件并不足够，需要清理历史并轮换已经暴露的凭证。

测试夹具中的品牌、产品、人物、场景和效果描述均为虚构，仅用于验证镜头状态变化和编译规则，不代表真实产品或效果承诺。

## 使用责任

使用者应确保对参考视频、商品图片、人物肖像、声音、音乐、字体和品牌素材拥有必要权利。该项目不提供广告法、功效宣称、肖像权、版权或平台发布合规判断，也不保证外部视频模型能够逐镜头复现输入内容。

Seedance、火山引擎及其他产品名称属于其各自权利人。本项目是独立工具，与相关服务商不存在官方隶属或背书关系。外部模型能力和 API 参数可能变化，实际使用前应核对最新官方文档。

## 许可证

本项目采用 [Apache License 2.0](LICENSE)。你可以使用、修改和分发本项目，也可以将其用于商业或闭源产品，但必须遵守许可证中的版权、归属、修改说明和专利条款。

许可证只覆盖本仓库中由项目贡献者拥有版权的源码、文档、schema 和虚构测试夹具，不授予用户输入素材、生成结果、第三方视频、图片、音频、字体、人物肖像、商标或商品包装的任何权利。归属信息见 [`NOTICE`](NOTICE)。

## 安全问题

发现凭证、个人信息或客户素材泄露时，请不要在公开 Issue 中粘贴敏感内容，按 [`SECURITY.md`](SECURITY.md) 的方式私下报告。
