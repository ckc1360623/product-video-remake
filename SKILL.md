---
name: product-video-remake
description: 用于快速复刻爆款或高表现商品视频的脚本提示词。离线完整拆解用户有权使用的参考视频，保留分镜、节奏、音频、运镜及人物/物体/商品/场景变化，只适配目标商品，输出标准单次请求或高镜头密度下的高保真分段请求包，并可验收用户回传的成片。适用于商品视频复刻、爆款视频脚本拆解、换商品视频与 Seedance 请求编译；不上传素材、不调用生成 API。
---

# 商品视频复刻编译器

当前运行策略为 V1.4 执行保真版。核心用途是把爆款或高表现商品参考视频快速拆解为可执行的视频脚本提示词，而不是直接复制或上传原片。原视频只在本地用于提取 Video DNA；线上请求只包含能够独立描述目标成片或片段的提示词与商品图。

## 不可改变的交付合同

- 终点是提示词、商品图上传清单、API 请求包、生成前校验报告，以及用户提供成片时的生成后结构验收；不上传素材、不调用或轮询 Seedance、不下载结果。
- 每个 API 请求都必须恰好包含一个文本提示词和 1–9 个商品 `reference_image`，不得包含视频或音频项目。
- 原视频及其路径、URL、占位符、资产记录、角色或描述不得进入 `upload-manifest.json` 或 `seedance-request.json`。
- 最终提示词必须独立描述目标视频，不得出现 `视频1`、`参考视频`、`原视频`、`原商品`、`reference video`、`source video` 等依赖模型看到原片的措辞。
- 不进行广告法、功效宣称或发布合规判断，不因合规原因弱化原片中可见的人体、皮肤、物体、商品或场景变化。
- 除目标商品和物理上必需的商品交互适配外，原片的镜头顺序、时长、节奏、音频结构、运镜、构图、焦段感、人物、状态变化、场景、文字、特效、转场和情绪弧线均视为锁定。
- 每个重要细节必须标记为 `preserved`、`approximated`、`minimally_adapted` 或 `omitted_with_reason`，不得静默丢失。
- 支持 `standard_single_call` 与 `high_fidelity_segmented` 两种编译模式。标准模式输出一次 4–15 秒生成；高保真模式只离线输出 2–3 个合法请求和确定性拼接清单，外部提交与拼接仍需用户或调用方明确执行。
- `T001` 等时间线 ID 仅用于 JSON 映射与校验，最终提示词必须改写为“镜头1（开始秒-结束秒）”，不得出现 `执行于：Txxx` 或其他悬空引用。

## 输入

默认只要求：

- 一张或多张商品图。
- 一个本地原视频路径，或可供离线分析的既有视频资产地址。

商品名称、卖点、语言、目标时长、比例、分辨率和达人均为可选。先从商品图推断缺失信息并记录证据与置信度；只有仍存在会实质改变复刻方向的歧义时才询问用户。

## 高速无损工作流

1. 对本地视频运行 `scripts/probe_media.py`，再运行 `scripts/prepare_analysis_pack.py`。后者默认保留 6 FPS 原始分辨率证据、镜头切换证据和分析音频，在一次源视频解码中完成主要提取，并用素材指纹复用缓存。不同复刻任务需要共享缓存时，显式把 `--cache-dir` 指向同一个可写缓存目录。
2. 如果工具允许，将商品图理解与视频分析包准备并行执行。并行只改变等待时间，不改变分析内容。
3. 视频第一遍理解必须按时间顺序查看 `analysis-pack.json` 中的全部 `overview_sheets`，建立完整故事、镜头顺序、主体和状态变化时间线；不得只看开头、中间和结尾。
4. 第二遍只对每个镜头边界、快速动作、音频踩点、字幕变化、商品交互，以及人物体型/皮肤/表情、物体形态、商品形态或场景变化检查原始 `dense_frames` 和 `cut_candidate_frames`。需要精确时刻的完整分辨率画面时运行 `scripts/extract_evidence_frame.py`。
5. 若总览图与原始证据矛盾、镜头边界不确定、两张总览之间可能遗漏短镜头，或任何必须保留项置信度不足，立即回退检查该时间段的全部密集帧；仍不确定时提高该区间抽帧率。速度不得优先于证据完整性。
6. 构建 `product-profile.json` 与 `source-video-dna.json`。把分析包的 `cache_key`、`source_signature` 和 `analysis_strategy_version` 写入 `source_asset`，用于安全复用语义分析。只有商品证据歧义、跨品类或交互不匹配时读取 [商品适配规则](references/product-adaptation.md)；只有快切、强音频踩点、复杂转场或人物/物体/场景变化时读取 [原视频深度分析](references/source-video-analysis.md) 和 [视频类型路由](references/video-type-routing.md)。
7. 判断商品距离并建立 `remake-plan.json`。计划必须包含 `editing_contract`：预期镜头数、硬切数、切点、允许漂移和禁止合并的相邻镜头。每个镜头必须记录 `must_be_distinct`、切入/切出要求、与前一镜头的可见差异、必要动作、服装/状态和场景。
8. 根据镜头密度选择模式。12秒内超过8个镜头，或平均镜头短于1.2秒时，默认推荐 `high_fidelity_segmented`；用户明确要求单次调用时保留标准模式并提示相邻镜头被合并的风险。长片压缩时读取 [单次调用压缩规则](references/single-call-compression.md)。
9. 标准模式运行 `scripts/compile_seedance_request.py`；高保真模式运行 `scripts/compile_fidelity_package.py`。`scripts/run_pipeline.py --generation-mode auto` 会按上述规则选择。只有 API 字段、模型能力或参数范围需要更新时读取 [Seedance 2.0 编译规则](references/seedance-2.0-compiler.md)。
10. 必须运行 `scripts/validate_bundle.py`。生成前校验还要确认提示词明确声明镜头数、硬切数和禁止合并要求，且不存在内部 `Txxx` 编号。校验失败时读取 [保真校验规则](references/fidelity-validation.md) 并修复。
11. 用户提供生成成片时，运行 `scripts/validate_generated_video.py`，检查时长、画幅、主要切点和切点漂移并生成语义验收清单。结构通过不等于语义通过；必须人工或视觉模型确认每个镜头的动作、服装、场景和状态差异后才能声称复刻成功。

数据结构不明确时读取 [数据合同](references/data-contracts.md)。需要理解完整操作顺序或排障时读取 [端到端工作流](references/workflow.md)。只有用户要求基准测试或证明质量时读取 [评测规则](references/evaluation.md)。不要在普通运行中加载所有参考文档。

## 缓存复用规则

- `prepare_analysis_pack.py` 只有在源文件的绝对路径、大小、修改时间、分析器版本和抽帧参数全部一致时才命中缓存；可用 `--force` 强制重建。
- 相同原视频更换商品时，可复用已验证的分析包和 `source-video-dna.json`，只重做商品理解、适配、编译和校验。
- 相同商品更换视频时，可复用有来源签名且证据未变化的 `product-profile.json`。
- 只修改时长、比例、分辨率或模型参数时，复用商品画像和视频 DNA，只重新生成计划、提示词、请求与校验报告。
- 不得仅因文件名相同而复用语义缓存；缓存证据不完整、版本变化或用户替换了文件时必须失效。

## 隐私与发布安全

- 分析包和缓存会保存本地绝对路径、参考视频抽帧、切镜画面及音频，只能放在用户指定的私有输出目录或被 `.gitignore` 排除的目录中。
- 不得把真实参考视频、商品图、分析音频、联系表、生成成片、客户名称、账号标识或凭证复制进 Skill 源码目录。
- 准备分发或公开仓库前，运行 `python -X utf8 scripts/check_release_safety.py`；发现项必须人工确认并清除后才能打包。
- 发布包只包含 Skill 源码、文档、schema 和虚构测试夹具；不得包含 `.product-video-remake-cache`、运行输出、`__pycache__`、`.pyc` 或 `.env` 文件。

## 标准模式必交付文件

- `product-profile.json`
- `source-video-dna.json`
- `remake-plan.json`
- `seedance-prompt.txt`
- `upload-manifest.json`
- `seedance-request.json`
- `preflight-validation-report.json`

外部程序只读取 `upload-manifest.json` 上传本地商品图，把 URL 占位符替换进 `seedance-request.json`，然后提交一次。分析缓存、总览图、密集帧、原视频和分析音频都不得加入请求。

高保真模式额外交付 `high-fidelity-package/fidelity-package.json`、`assembly-plan.json`，以及每个 `segment-XXX` 目录中的独立计划、提示词、上传清单、请求和预检报告。用户回传成片后额外交付 `postflight-validation-report.json` 和联系表。

## 完成条件

只有在 `preflight-validation-report.json` 显示 `ready: true`、错误数为零、所有必须保留镜头和元素都有目标指令，并确认每个请求只有一个提示词、商品参考图且没有视频/音频项目时才能交付。高保真模式还要求所有片段预检通过且拼接时间无空隙或重叠。成片只能在后验收结构通过并完成语义清单后标记为复刻成功。警告只能表达保真或模型可控性不确定性，不得表达合规判断。
