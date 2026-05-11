# 云厂商 AI 接口列表（ASR / TTS / 语音端点 / Vision）

本文档按厂商整理**对外 API 操作名或 HTTP 路径**（不含鉴权、区域 endpoint、配额；以各云**当前官方文档**为准）。自建网关接口见同目录 [`ai-gateway.md`](ai-gateway.md)。

**说明**

- **列全的含义**：下列表格尽量与**官方 API 参考 / Discovery / OpenAPI（见各节链接）在编辑时一致**；厂商新增或下线接口时，以官网为准，本文不保证实时同步。
- **接口形态（文中用语）**：
  - **HTTP · REST**：以 **URL 路径 + HTTP 方法** 表达资源与操作（如 `GET/POST …/v1/...`、OpenAI `/v1/audio/...`）。
  - **HTTP(S) · RPC**：传输层为 **HTTPS**，业务上通过 **`Action` / `x-amz-target` / 单一路径 + 过程名** 调用「远程过程」，**不是**典型 REST 资源路径风格（如腾讯云 API 3.0、阿里云 POP、AWS JSON 协议）。
  - **WebSocket**：**`ws://` / `wss://` 长连接**，帧内传业务数据（与「单次 HTTP 请求—响应」不同）。
  - 同一产品可能同时提供 **HTTP（REST 或 RPC）** 与 **WebSocket**（如实时语音识别）；以各小节 **「接口类型」** 为准。
  - **各云是否用 WebSocket**：**多数接口是 HTTPS**；**实时语音（流式 ASR）**、部分 **Speech 合成/对话** 会提供 **WebSocket**（或 **HTTP/2** 流）。**视觉**类多为 **HTTPS**。**Google Speech 流式**为 **gRPC**，**不是** WebSocket。**WebSocket / 流式入口**按厂商分列：**§1.4**（AWS）、**§2.4**（Google gRPC）、**§3.4**（Azure）、**§4.4**（阿里云）、**§5.2**（腾讯云）、**§6.2**（OpenAI Realtime）。
- **VAD**：公有云极少提供独立「仅端点检测」REST；多并入**流式 ASR** 或 SDK。下表「语音端点」列仅列文档中明确与端点/语音活动相关的项。
- 同一产品在不同版本（v1/v2）下路径可能并存，以厂商文档为准。

---

## 1. Amazon Web Services（AWS）

本节中：**批量/控制面**若使用 **`x-amz-target` + 单一路径 `POST /`**，在本文中记为 **HTTPS · RPC**（AWS JSON 协议）；**Polly** 等为 **HTTPS · REST**（路径含 `/v1/...`）。**Transcribe / Polly 的 WebSocket 与流式 URL** 见 **§1.4**；流式操作名另见 **§1.1** 表格。

### 1.1 Amazon Transcribe（ASR）

**接口类型**：下表 **Transcribe Service（批量等）** 为 **HTTPS · RPC**（`x-amz-target` + `POST /`）。**Transcribe Streaming** 为 **流式 endpoint**（官方支持 **HTTP/2 与/或 WebSocket**，以 [流式文档](https://docs.aws.amazon.com/transcribe/latest/dg/streaming.html) 为准；**非** 与批量表相同的 URL 形态）。

**调用形态**：区域 endpoint + AWS JSON 协议（`x-amz-target: com.amazonaws.transcribe.Transcribe.<Operation>`），非单一「REST 风格路径」。

**路径（批量 Service）**：`POST https://transcribe.{region}.amazonaws.com/`；Header `x-amz-target: com.amazonaws.transcribe.Transcribe.<方法>`（与下列「方法」列同名）。

**Transcribe Service（批量等）— 全部操作**（与 [官方 Actions 列表](https://docs.aws.amazon.com/transcribe/latest/APIReference/API_Operations_Amazon_Transcribe_Service.html) 对齐）：

| 方法 | 路径 | 说明 |
|------|------|------|
| `CreateCallAnalyticsCategory` | `POST /` | 创建通话分析分类 |
| `CreateLanguageModel` | `POST /` | 创建自定义语言模型 |
| `CreateMedicalVocabulary` | `POST /` | 创建医疗专用词表 |
| `CreateVocabulary` | `POST /` | 创建自定义词表 |
| `CreateVocabularyFilter` | `POST /` | 创建词汇过滤表 |
| `DeleteCallAnalyticsCategory` | `POST /` | 删除通话分析分类 |
| `DeleteCallAnalyticsJob` | `POST /` | 删除通话分析任务 |
| `DeleteLanguageModel` | `POST /` | 删除语言模型 |
| `DeleteMedicalScribeJob` | `POST /` | 删除医疗听写任务 |
| `DeleteMedicalTranscriptionJob` | `POST /` | 删除医疗转写任务 |
| `DeleteMedicalVocabulary` | `POST /` | 删除医疗词表 |
| `DeleteTranscriptionJob` | `POST /` | 删除标准转写任务 |
| `DeleteVocabulary` | `POST /` | 删除词表 |
| `DeleteVocabularyFilter` | `POST /` | 删除词汇过滤表 |
| `DescribeLanguageModel` | `POST /` | 查询语言模型详情 |
| `GetCallAnalyticsCategory` | `POST /` | 获取通话分析分类 |
| `GetCallAnalyticsJob` | `POST /` | 获取通话分析任务 |
| `GetMedicalScribeJob` | `POST /` | 获取医疗听写任务 |
| `GetMedicalTranscriptionJob` | `POST /` | 获取医疗转写任务 |
| `GetMedicalVocabulary` | `POST /` | 获取医疗词表 |
| `GetTranscriptionJob` | `POST /` | 获取标准转写任务 |
| `GetVocabulary` | `POST /` | 获取词表 |
| `GetVocabularyFilter` | `POST /` | 获取词汇过滤表 |
| `ListCallAnalyticsCategories` | `POST /` | 列举通话分析分类 |
| `ListCallAnalyticsJobs` | `POST /` | 列举通话分析任务 |
| `ListLanguageModels` | `POST /` | 列举语言模型 |
| `ListMedicalScribeJobs` | `POST /` | 列举医疗听写任务 |
| `ListMedicalTranscriptionJobs` | `POST /` | 列举医疗转写任务 |
| `ListMedicalVocabularies` | `POST /` | 列举医疗词表 |
| `ListTagsForResource` | `POST /` | 列举资源标签 |
| `ListTranscriptionJobs` | `POST /` | 列举标准转写任务 |
| `ListVocabularies` | `POST /` | 列举词表 |
| `ListVocabularyFilters` | `POST /` | 列举词汇过滤表 |
| `StartCallAnalyticsJob` | `POST /` | 启动通话分析转写任务 |
| `StartMedicalScribeJob` | `POST /` | 启动医疗听写任务 |
| `StartMedicalTranscriptionJob` | `POST /` | 启动医疗转写任务 |
| `StartTranscriptionJob` | `POST /` | 启动标准转写任务 |
| `TagResource` | `POST /` | 为资源添加标签 |
| `UntagResource` | `POST /` | 移除资源标签 |
| `UpdateCallAnalyticsCategory` | `POST /` | 更新通话分析分类 |
| `UpdateMedicalVocabulary` | `POST /` | 更新医疗词表 |
| `UpdateVocabulary` | `POST /` | 更新词表 |
| `UpdateVocabularyFilter` | `POST /` | 更新词汇过滤表 |

**路径（流式 Streaming）**：使用独立流式 endpoint（**HTTP/2** 或 **WebSocket**，见官方「流式转写」文档）；`x-amz-target` 指向流式 API 对应操作。**WebSocket / HTTP/2 握手 URL 形态**见 **§1.4**。

**Transcribe Streaming Service — 全部操作**（与 [官方 Streaming Actions](https://docs.aws.amazon.com/transcribe/latest/APIReference/API_Operations_Amazon_Transcribe_Streaming_Service.html) 对齐）：

| 方法 | 路径 | 说明 |
|------|------|------|
| `GetMedicalScribeStream` | 流式接入端点（HTTP/2 或 WebSocket） | 获取医疗听写流式结果 |
| `StartCallAnalyticsStreamTranscription` | 同上 | 启动通话分析流式转写 |
| `StartMedicalScribeStream` | 同上 | 启动医疗听写流式 |
| `StartMedicalStreamTranscription` | 同上 | 启动医疗流式转写 |
| `StartStreamTranscription` | 同上 | 启动标准流式转写 |
| `UpdateVocabularyFilter` | 同上 | 更新词汇过滤表（流式侧） |

**文档**：[Transcribe · Actions 总览](https://docs.aws.amazon.com/transcribe/latest/APIReference/API_Operations.html)

### 1.2 Amazon Polly（TTS）

**接口类型**：下表 **HTTPS · REST**（路径如 `/v1/speech`、`/v1/voices` 等）。`StartSpeechSynthesisStream` 为 **流式 endpoint**（见官方流式合成说明；**非** 下表路径枚举的同一套 URL）。

**调用形态**：区域 endpoint；路径相对于服务根（以下为常见 REST 形态，与 [Polly API](https://docs.aws.amazon.com/polly/latest/dg/API_Operations.html) 对齐）。

**全部操作**：

| 方法 | 路径 | 说明 |
|------|------|------|
| `SynthesizeSpeech` | `POST /v1/speech` | 同步语音合成 |
| `StartSpeechSynthesisTask` | `POST /v1/synthesisTasks` | 创建异步长文本合成任务 |
| `GetSpeechSynthesisTask` | `GET /v1/synthesisTasks/{TaskId}` | 查询异步合成任务 |
| `ListSpeechSynthesisTasks` | `GET /v1/synthesisTasks` | 列举异步合成任务 |
| `StartSpeechSynthesisStream` | 流式接入端点（见官方流式合成文档） | 流式合成 |
| `DescribeVoices` | `GET /v1/voices` | 列举/筛选音色 |
| `PutLexicon` | `PUT /v1/lexicons/{LexiconName}` | 上传自定义词典 |
| `GetLexicon` | `GET /v1/lexicons/{LexiconName}` | 获取词典内容 |
| `DeleteLexicon` | `DELETE /v1/lexicons/{LexiconName}` | 删除词典 |
| `ListLexicons` | `GET /v1/lexicons` | 列举词典 |

**文档**：[SynthesizeSpeech](https://docs.aws.amazon.com/polly/latest/dg/API_SynthesizeSpeech.html)

### 1.3 Amazon Rekognition（视觉）

**接口类型**：**HTTPS · RPC**（AWS JSON 协议：`Content-Type: application/x-amz-json-1.1`；**操作**由 Header **`x-amz-target: com.amazonaws.rekognition.Rekognition.<Operation>`** 与 **JSON Body** 共同指定）。**非 WebSocket**；**非** Polly 那种 `/v1/...` **REST 资源路径**。

**为何「路径」列全是 `POST /`（不是表没补全）**：服务只暴露**固定服务根** `POST https://rekognition.{region}.amazonaws.com/`，路径即为 **`/`**；**所有** API 共用这一 URL，**不按 REST 资源拆不同 path**，故表中「路径」列统一为 `POST /` 是**刻意与官方一致**，**区分操作靠「方法」列 + `x-amz-target`**。

**路径（统一）**：`POST https://rekognition.{region}.amazonaws.com/`；Header `x-amz-target: com.amazonaws.rekognition.Rekognition.<方法>`（与下列「方法」列同名）。

**全部操作**（与 [Rekognition Actions](https://docs.aws.amazon.com/rekognition/latest/APIReference/API_Operations_Amazon_Rekognition.html) 对齐）：

| 方法 | 路径 | 说明 |
|------|------|------|
| `AssociateFaces` | `POST /` | 将人脸关联到用户 |
| `CompareFaces` | `POST /` | 比对人脸相似度 |
| `CopyProjectVersion` | `POST /` | 复制自定义模型版本 |
| `CreateCollection` | `POST /` | 创建资源 |
| `CreateDataset` | `POST /` | 创建资源 |
| `CreateFaceLivenessSession` | `POST /` | 创建资源 |
| `CreateProject` | `POST /` | 创建资源 |
| `CreateProjectVersion` | `POST /` | 创建资源 |
| `CreateStreamProcessor` | `POST /` | 创建资源 |
| `CreateUser` | `POST /` | 创建资源 |
| `DeleteCollection` | `POST /` | 删除资源 |
| `DeleteDataset` | `POST /` | 删除资源 |
| `DeleteFaces` | `POST /` | 删除资源 |
| `DeleteProject` | `POST /` | 删除资源 |
| `DeleteProjectPolicy` | `POST /` | 删除资源 |
| `DeleteProjectVersion` | `POST /` | 删除资源 |
| `DeleteStreamProcessor` | `POST /` | 删除资源 |
| `DeleteUser` | `POST /` | 删除资源 |
| `DescribeCollection` | `POST /` | 查询资源元数据 |
| `DescribeDataset` | `POST /` | 查询资源元数据 |
| `DescribeProjects` | `POST /` | 查询资源元数据 |
| `DescribeProjectVersions` | `POST /` | 查询资源元数据 |
| `DescribeStreamProcessor` | `POST /` | 查询资源元数据 |
| `DetectCustomLabels` | `POST /` | 同步图像检测 |
| `DetectFaces` | `POST /` | 同步图像检测 |
| `DetectLabels` | `POST /` | 同步图像检测 |
| `DetectModerationLabels` | `POST /` | 同步图像检测 |
| `DetectProtectiveEquipment` | `POST /` | 同步图像检测 |
| `DetectText` | `POST /` | 同步图像检测 |
| `DisassociateFaces` | `POST /` | 解除人脸与用户关联 |
| `DistributeDatasetEntries` | `POST /` | 分发数据集条目 |
| `GetCelebrityInfo` | `POST /` | 按 Id 查询名人信息 |
| `GetCelebrityRecognition` | `POST /` | 查询名人识别异步结果 |
| `GetContentModeration` | `POST /` | 查询视频异步分析结果 |
| `GetFaceDetection` | `POST /` | 查询视频异步分析结果 |
| `GetFaceLivenessSessionResults` | `POST /` | 获取人脸活体检测结果 |
| `GetFaceSearch` | `POST /` | 查询视频异步分析结果 |
| `GetLabelDetection` | `POST /` | 查询视频异步分析结果 |
| `GetMediaAnalysisJob` | `POST /` | 查询媒体分析异步任务 |
| `GetPersonTracking` | `POST /` | 查询视频异步分析结果 |
| `GetSegmentDetection` | `POST /` | 查询视频异步分析结果 |
| `GetTextDetection` | `POST /` | 查询视频异步分析结果 |
| `IndexFaces` | `POST /` | 向集合索引人脸 |
| `ListCollections` | `POST /` | 列举资源 |
| `ListDatasetEntries` | `POST /` | 列举资源 |
| `ListDatasetLabels` | `POST /` | 列举资源 |
| `ListFaces` | `POST /` | 列举资源 |
| `ListMediaAnalysisJobs` | `POST /` | 列举资源 |
| `ListProjectPolicies` | `POST /` | 列举资源 |
| `ListStreamProcessors` | `POST /` | 列举资源 |
| `ListTagsForResource` | `POST /` | 列举资源 |
| `ListUsers` | `POST /` | 列举资源 |
| `PutProjectPolicy` | `POST /` | 设置项目策略 |
| `RecognizeCelebrities` | `POST /` | 同步识别名人 |
| `SearchFaces` | `POST /` | 以图或 Id 搜索人脸或用户 |
| `SearchFacesByImage` | `POST /` | 以图或 Id 搜索人脸或用户 |
| `SearchUsers` | `POST /` | 以图或 Id 搜索人脸或用户 |
| `SearchUsersByImage` | `POST /` | 以图或 Id 搜索人脸或用户 |
| `StartCelebrityRecognition` | `POST /` | 启动视频异步分析 |
| `StartContentModeration` | `POST /` | 启动视频异步分析 |
| `StartFaceDetection` | `POST /` | 启动视频异步分析 |
| `StartFaceSearch` | `POST /` | 启动视频异步分析 |
| `StartLabelDetection` | `POST /` | 启动视频异步分析 |
| `StartMediaAnalysisJob` | `POST /` | 启动视频异步分析 |
| `StartPersonTracking` | `POST /` | 启动视频异步分析 |
| `StartProjectVersion` | `POST /` | 启动视频异步分析 |
| `StartSegmentDetection` | `POST /` | 启动视频异步分析 |
| `StartStreamProcessor` | `POST /` | 启动视频异步分析 |
| `StartTextDetection` | `POST /` | 启动视频异步分析 |
| `StopProjectVersion` | `POST /` | 停止自定义模型或流处理器 |
| `StopStreamProcessor` | `POST /` | 停止自定义模型或流处理器 |
| `TagResource` | `POST /` | 管理资源标签 |
| `UntagResource` | `POST /` | 管理资源标签 |
| `UpdateDatasetEntries` | `POST /` | 更新资源 |
| `UpdateStreamProcessor` | `POST /` | 更新资源 |

**文档**：[Rekognition · Actions](https://docs.aws.amazon.com/rekognition/latest/APIReference/API_Operations.html)

### 1.4 WebSocket / 流式长连接（Transcribe · Polly）

**说明**：以下为 AWS 文档中**与流式语音**相关的 **WebSocket** 或 **HTTP/2** 接入摘要；完整 Query、签名、帧格式以官方为准。

#### Amazon Transcribe Streaming

| 传输 | 入口 / 形态（摘要） | 文档 |
|------|---------------------|------|
| **WebSocket** | `wss://transcribestreaming.{region}.amazonaws.com:8443/stream-transcription-websocket`（预签名 URL 中常含 `Action=transcribe:StartStreamTranscriptionWebSocket` 等） | [Streaming](https://docs.aws.amazon.com/transcribe/latest/dg/streaming.html) · [WebSocket 设置](https://docs.aws.amazon.com/transcribe/latest/dg/streaming-setting-up.html) |
| **HTTP/2** | `POST /stream-transcription`（与 WebSocket **二选一**接入方式） | 同上 |

流式侧 **API 操作名**见 §1.1「Transcribe Streaming Service」表（如 `StartStreamTranscription`、`StartMedicalStreamTranscription` 等）。

#### Amazon Polly

**`StartSpeechSynthesisStream`** 为**流式合成**能力，接入形态以 [Polly 产品/操作文档](https://docs.aws.amazon.com/polly/latest/dg/API_Operations.html) 为准；与 **`POST /v1/speech`** 等 **HTTPS REST** 并列，**未必**等同于浏览器标准 WebSocket 场景。

**视觉（Rekognition）**：对外为 **HTTPS · RPC**（§1.3），**无**与 ASR 同级的统一 WebSocket 能力表。

---

## 2. Google Cloud

**接口类型**：**HTTPS · REST**（Google API Discovery：资源路径 + `GET`/`POST` 等；如 `…/v1/speech:recognize`）。**不是** AWS `x-amz-target` 式 RPC、**不是**腾讯云 `Action` 表（语义上同为 HTTP，但路径风格不同）。**连续流式语音识别**见 **§2.4**（**gRPC**，非 WebSocket）。

以下 REST 方法来自 **Discovery**（[Speech v1](https://speech.googleapis.com/$discovery/rest?version=v1)、[Speech v2](https://speech.googleapis.com/$discovery/rest?version=v2)、[TTS v1](https://texttospeech.googleapis.com/$discovery/rest?version=v1)、[Vision v1](https://vision.googleapis.com/$discovery/rest?version=v1)）。

### 2.1 Cloud Speech-to-Text（ASR）

**Host**：`https://speech.googleapis.com/`（下表路径与其拼接；`…` 表示 host + 版本前缀）。

**v1**

| 方法 | 路径 | 说明 |
|------|------|------|
| `speech.recognize` | `POST …/v1/speech:recognize` | 同步短音频识别 |
| `speech.longrunningrecognize` | `POST …/v1/speech:longrunningrecognize` | 提交长音频异步识别 |
| `projects.locations.phraseSets.*` | `GET/POST/PATCH/DELETE …/v1/{+parent}/phraseSets` 等 | 词组集增删改查 |
| `projects.locations.customClasses.*` | `GET/POST/PATCH/DELETE …/v1/{+parent}/customClasses` 等 | 自定义类增删改查 |
| `operations.get` · `operations.list` | `GET …/v1/operations/{+name}`、`…/v1/operations` | 查询长运行操作状态 |

**v2**

| 方法 | 路径 | 说明 |
|------|------|------|
| `projects.locations.recognizers.recognize` | `POST …/v2/{+recognizer}:recognize` | 同步识别 |
| `projects.locations.recognizers.batchRecognize` | `POST …/v2/{+recognizer}:batchRecognize` | 批量识别 |
| `projects.locations.recognizers.*` | `GET/POST/PATCH/DELETE …/v2/{+parent}/recognizers` 等 | 识别器增删改查与软删除恢复 |
| `projects.locations.phraseSets.*` · `customClasses.*` | `v2/...` 对应资源 | 词组集与自定义类 |
| `projects.locations.config.get` · `config.update` | `GET/PATCH …/v2/{+name}` | 配置读写 |
| `projects.locations.get` · `projects.locations.list` | `GET …/v2/{+name}`、`…/locations` | 项目与位置 |
| `projects.locations.operations.get` · `operations.list` | `GET …/v2/{+name}/operations` 等 | 操作状态 |

**语音端点 / 活动（流式）**：v2 流式识别与**语音活动事件**见产品文档（非独立 VAD 产品名）。

**文档**：[Speech-to-Text · REST](https://cloud.google.com/speech-to-text/docs/reference/rest)

### 2.2 Cloud Text-to-Speech（TTS）

**接口类型**：**HTTPS · REST**（与 §2 一致）。

**Host**：`https://texttospeech.googleapis.com/`

| 方法 | 路径 | 说明 |
|------|------|------|
| `text.synthesize` | `POST …/v1/text:synthesize` | 同步合成语音 |
| `voices.list` | `GET …/v1/voices` | 列举音色 |
| `projects.locations.synthesizeLongAudio` | `POST …/v1/{+parent}:synthesizeLongAudio` | 长音频异步合成 |
| `projects.locations.operations.get` · `operations.list` | `GET …/v1/{+name}`、`…/operations` | 长音频任务状态 |
| `operations.cancel` · `operations.delete` | `POST/DELETE …/v1/{+name}`、`…:cancel` | 取消或删除操作资源 |

**文档**：[Text-to-Speech · REST](https://cloud.google.com/text-to-speech/docs/reference/rest)

### 2.3 Cloud Vision API（视觉）

**接口类型**：**HTTPS · REST**（与 §2 一致；`:annotate`、`:asyncBatchAnnotate` 等为 **RPC 风格方法后缀**，但仍通过 **URL 路径** 区分，与 AWS 单路径 `POST /` 不同）。

**Host**：`https://vision.googleapis.com/`。下表为 Discovery 中路径模板与典型方法（**路径模板共 18 种**；同一 path 可对应多种 HTTP 方法，以 Discovery 为准）。

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `v1/files:annotate` | 对文件执行标注（批量特征） |
| `POST` | `v1/files:asyncBatchAnnotate` | 文件异步批量标注 |
| `POST` | `v1/images:annotate` | 对图像执行标注（常用入口） |
| `POST` | `v1/images:asyncBatchAnnotate` | 图像异步批量标注 |
| GET/PATCH/DELETE 等 | `v1/{+name}` | 资源与长时间运行操作元数据（依子路径与方法而定） |
| `GET` | `v1/{+name}/products` | 列出商品集下商品 |
| `POST` | `v1/{+name}:addProduct` / `:removeProduct` | 商品集增删商品 |
| `POST` | `v1/{+name}:cancel` | 取消长时间运行操作 |
| `POST` 等 | `v1/{+parent}/files:annotate` 等 | 项目作用域下文件/图像标注 |
| GET/POST/PATCH/DELETE | `v1/{+parent}/productSets` 等 | 商品集增删改查与导入 |
| GET/POST 等 | `v1/{+parent}/products` / `:purge` | 商品增删改查与清空 |
| GET/POST/DELETE | `v1/{+parent}/referenceImages` | 参考图管理 |

**文档**：[Vision · REST](https://cloud.google.com/vision/docs/reference/rest)

### 2.4 Cloud Speech 流式识别（gRPC，非 WebSocket）

**接口类型**：**gRPC 双向流**（**不是** `wss://`）。公开文档以 **`Speech.StreamingRecognize`**（v1/v2 见对应 proto）为主；浏览器侧 **无**与 REST 表同级的 **`wss` 流式**说明路径。

**文档**：[Streaming speech recognition](https://cloud.google.com/speech-to-text/docs/streaming-recognize)

---

## 3. Microsoft Azure（AI Speech 等）

**接口类型**：下列 OpenAPI 表为 **HTTPS · REST**（相对路径 + **`api-version` query**）。**实时/连续识别**与 **流式合成** 的 **WebSocket** 见 **§3.4**（**非** 本表路径形态）。

**调用形态**：认知服务 **endpoint + `api-version`**；下列路径来自 **OpenAPI**（相对路径，不含 host）。

### 3.1 语音转文本（Speech to text）

**路径前缀**：认知服务 **endpoint** + 下列**相对路径**；需带 `api-version`（见 [speechtotext.json `preview/2024-05-15-preview`](https://github.com/Azure/azure-rest-api-specs/blob/main/specification/cognitiveservices/data-plane/Speech/SpeechToText/preview/2024-05-15-preview/speechtotext.json)）。**说明**列为中文摘要（与 OpenAPI `summary` 对应）。

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/datasets` | 获取当前订阅下的数据集列表 |
| `POST` | `/datasets` | 从指定 URL 拉取数据或等待分块上传，创建新数据集 |
| `GET` | `/datasets/locales` | 获取数据集支持的语言区域列表 |
| `DELETE` | `/datasets/{id}` | 删除指定数据集 |
| `GET` | `/datasets/{id}` | 按 ID 获取数据集 |
| `PATCH` | `/datasets/{id}` | 按 ID 更新数据集的可变字段 |
| `GET` | `/datasets/{id}/blocks` | 获取该数据集已上传分块列表 |
| `PUT` | `/datasets/{id}/blocks` | 上传数据集的一个数据块（单块最大 8MiB） |
| `POST` | `/datasets/{id}/blocks:commit` | 提交分块列表以完成数据集上传 |
| `GET` | `/datasets/{id}/files` | 获取该数据集的文件列表 |
| `GET` | `/datasets/{id}/files/{fileId}` | 按 fileId 获取数据集中的单个文件 |
| `GET` | `/endpoints` | 获取当前订阅下的终结点列表 |
| `POST` | `/endpoints` | 创建新终结点 |
| `DELETE` | `/endpoints/base/{locale}/files/logs` | 删除使用默认基础模型时存储的指定语种音频与转写日志 |
| `GET` | `/endpoints/base/{locale}/files/logs` | 列出使用默认基础模型时存储的指定语种音频与转写日志 |
| `DELETE` | `/endpoints/base/{locale}/files/logs/{logId}` | 删除上述日志中的一条 |
| `GET` | `/endpoints/base/{locale}/files/logs/{logId}` | 获取上述日志中的一条 |
| `GET` | `/endpoints/locales` | 获取创建终结点时可用的语言区域列表 |
| `DELETE` | `/endpoints/{id}` | 按 ID 删除终结点 |
| `GET` | `/endpoints/{id}` | 按 ID 获取终结点 |
| `PATCH` | `/endpoints/{id}` | 按 ID 更新终结点元数据 |
| `DELETE` | `/endpoints/{id}/files/logs` | 删除该终结点下存储的全部音频与转写日志 |
| `GET` | `/endpoints/{id}/files/logs` | 列出该终结点下存储的音频与转写日志 |
| `DELETE` | `/endpoints/{id}/files/logs/{logId}` | 删除该终结点下存储的一条日志 |
| `GET` | `/endpoints/{id}/files/logs/{logId}` | 获取该终结点下存储的一条日志 |
| `GET` | `/evaluations` | 获取当前订阅下的评估任务列表 |
| `POST` | `/evaluations` | 创建新评估任务 |
| `GET` | `/evaluations/locales` | 获取评估支持的语言区域列表 |
| `DELETE` | `/evaluations/{id}` | 按 ID 删除评估 |
| `GET` | `/evaluations/{id}` | 按 ID 获取评估 |
| `PATCH` | `/evaluations/{id}` | 按 ID 更新评估的可变字段 |
| `GET` | `/evaluations/{id}/files` | 获取该评估的文件列表 |
| `GET` | `/evaluations/{id}/files/{fileId}` | 按 fileId 获取评估中的单个文件 |
| `GET` | `/models` | 获取当前订阅下的自定义模型列表 |
| `POST` | `/models` | 创建新模型 |
| `GET` | `/models/base` | 获取当前订阅下的基础模型列表 |
| `GET` | `/models/base/{id}` | 按 ID 获取基础模型 |
| `GET` | `/models/base/{id}/manifest` | 返回该基础模型的清单（可用于本地容器部署） |
| `GET` | `/models/locales` | 获取模型适配支持的语言区域列表 |
| `DELETE` | `/models/{id}` | 按 ID 删除模型 |
| `GET` | `/models/{id}` | 按 ID 获取模型 |
| `PATCH` | `/models/{id}` | 按 ID 更新模型元数据 |
| `GET` | `/models/{id}/files` | 获取该模型的文件列表 |
| `GET` | `/models/{id}/files/{fileId}` | 按 fileId 获取模型中的单个文件 |
| `GET` | `/models/{id}/manifest` | 返回该模型的清单（可用于本地容器部署） |
| `POST` | `/models/{id}:copy` | 将模型复制到另一订阅 |
| `POST` | `/models:authorizecopy` | 授权另一语音资源（源）将模型复制到本资源（目标） |
| `GET` | `/operations/models/copy/{id}` | 按 ID 获取复制操作状态 |
| `GET` | `/projects` | 获取当前订阅下的项目列表 |
| `POST` | `/projects` | 创建新项目 |
| `GET` | `/projects/locales` | 获取支持的语言区域列表 |
| `DELETE` | `/projects/{id}` | 按 ID 删除项目 |
| `GET` | `/projects/{id}` | 按 ID 获取项目 |
| `PATCH` | `/projects/{id}` | 按 ID 更新项目 |
| `GET` | `/projects/{id}/datasets` | 获取该项目下的数据集列表 |
| `GET` | `/projects/{id}/endpoints` | 获取该项目下的终结点列表 |
| `GET` | `/projects/{id}/evaluations` | 获取该项目下的评估列表 |
| `GET` | `/projects/{id}/models` | 获取该项目下的模型列表 |
| `GET` | `/projects/{id}/transcriptions` | 获取该项目下的转写任务列表 |
| `GET` | `/transcriptions` | 获取当前订阅下的转写任务列表 |
| `GET` | `/transcriptions/locales` | 获取离线转写支持的语言区域列表 |
| `DELETE` | `/transcriptions/{id}` | 删除指定转写任务 |
| `GET` | `/transcriptions/{id}` | 按 ID 获取转写任务 |
| `PATCH` | `/transcriptions/{id}` | 按 ID 更新转写任务的可变字段 |
| `GET` | `/transcriptions/{id}/files` | 获取该转写任务的文件列表 |
| `GET` | `/transcriptions/{id}/files/{fileId}` | 按 fileId 获取转写任务中的单个文件 |
| `POST` | `/transcriptions:submit` | 提交新的转写任务 |
| `POST` | `/transcriptions:transcribe` | 转写提供的音频流 |
| `GET` | `/webhooks` | 获取当前订阅下的 Webhook 列表 |
| `POST` | `/webhooks` | 创建新 Webhook |
| `DELETE` | `/webhooks/{id}` | 按 ID 删除 Webhook |
| `GET` | `/webhooks/{id}` | 按 ID 获取 Webhook |
| `PATCH` | `/webhooks/{id}` | 按 ID 更新 Webhook |
| `POST` | `/webhooks/{id}:ping` | 向注册 URL 发送 ping 事件 |
| `POST` | `/webhooks/{id}:test` | 对每种已注册事件类型向注册 URL 发送测试请求 |

**文档**：[Speech to text REST 概览](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-speech-to-text) · [REST API 参考](https://learn.microsoft.com/en-us/rest/api/speechtotext/)

### 3.2 文本转语音（TTS）

**接口类型**：**下表**（Batch/自定义等）为 **HTTPS · REST**；**在线合成**一句见同节 **「在线合成（区域 endpoint）」**（同为 HTTPS；与 SDK/WebSocket 流式合成区分见官方文档）。

**Batch / 自定义等相关 REST**（[texttospeech.json `preview/2024-02-01-preview`](https://github.com/Azure/azure-rest-api-specs/blob/main/specification/cognitiveservices/data-plane/Speech/TextToSpeech/preview/2024-02-01-preview/texttospeech.json)）。**说明**列为中文摘要（与 OpenAPI `summary` 对应）。

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/basemodels` | 获取基础模型列表 |
| `GET` | `/consents` | 获取当前 Speech 资源下的发音人授权同意列表 |
| `DELETE` | `/consents/{id}` | 按 ID 删除授权同意 |
| `GET` | `/consents/{id}` | 按 ID 获取授权同意 |
| `POST` | `/consents/{id}` | 使用上传的音频文件创建新的发音人授权同意 |
| `PUT` | `/consents/{id}` | 使用音频 URL 创建新的发音人授权同意 |
| `GET` | `/endpoints` | 获取当前 Speech 资源下的终结点列表 |
| `DELETE` | `/endpoints/{id}` | 按 ID 删除终结点 |
| `GET` | `/endpoints/{id}` | 按 ID 获取终结点 |
| `PUT` | `/endpoints/{id}` | 创建新终结点 |
| `POST` | `/endpoints/{id}:resume` | 恢复指定 ID 的终结点 |
| `POST` | `/endpoints/{id}:suspend` | 暂停指定 ID 的终结点 |
| `GET` | `/modelrecipes` | 获取模型构建可用的配方列表（不同配方能力不同） |
| `GET` | `/models` | 获取当前 Speech 资源下的模型列表 |
| `DELETE` | `/models/{id}` | 按 ID 删除模型 |
| `GET` | `/models/{id}` | 按 ID 获取模型 |
| `PUT` | `/models/{id}` | 创建新语音模型 |
| `GET` | `/operations/{id}` | 获取操作信息 |
| `GET` | `/personalvoices` | 获取当前 Speech 资源下的个人音色列表 |
| `DELETE` | `/personalvoices/{id}` | 按 ID 删除个人音色 |
| `GET` | `/personalvoices/{id}` | 按 ID 获取个人音色 |
| `POST` | `/personalvoices/{id}` | 使用客户端音频文件创建个人音色 |
| `PUT` | `/personalvoices/{id}` | 使用 Azure Blob 中的音频创建个人音色 |
| `GET` | `/projects` | 获取当前 Speech 资源下的项目列表 |
| `DELETE` | `/projects/{id}` | 按 ID 删除项目（项目内同意书、训练集等数据一并删除） |
| `GET` | `/projects/{id}` | 按 ID 获取项目 |
| `PUT` | `/projects/{id}` | 创建新项目 |
| `GET` | `/trainingsets` | 获取当前 Speech 资源下的训练集列表 |
| `DELETE` | `/trainingsets/{id}` | 按 ID 删除训练集 |
| `GET` | `/trainingsets/{id}` | 按 ID 获取训练集 |
| `PUT` | `/trainingsets/{id}` | 创建新训练集 |
| `POST` | `/trainingsets/{id}:upload` | 向指定训练集上传数据 |

**在线合成（区域 endpoint）**：文档中的 **Text to speech REST** URL 模板（非上表路径）；音色列表例如 `GET https://{region}.tts.speech.microsoft.com/cognitiveservices/voices/list`。

**文档**：[Text to speech REST](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech)

### 3.3 视觉

**接口类型**：各子产品多为 **HTTPS · REST**（具体路径以对应 API 参考为准）。

产品拆分为多条产品线（图像分析、人脸、文档智能等），**无单一 `images:annotate` 式总表**；按 [Azure AI Vision](https://learn.microsoft.com/en-us/azure/ai-services/computer-vision/) 子文档查阅各 REST。

### 3.4 Speech Service — WebSocket（实时识别 / 流式合成）

**说明**：与 §3.1、§3.2 中 **OpenAPI 相对路径** 的 **HTTPS REST** 不同；下列为 **区域化 `wss://`** 语音接入（完整 Query、Header、消息帧以官方为准）。

| 场景 | 传输 | 入口 URL（摘要） | 文档 |
|------|------|------------------|------|
| 连续 / 实时 **语音识别** | **WebSocket** | `wss://{region}.stt.speech.microsoft.com/speech/recognition/{mode}/cognitiveservices/v1`（`{mode}` 如 `conversation`、`dictation` 等，以文档为准） | [使用 WebSocket](https://learn.microsoft.com/azure/ai-services/speech-service/how-to-use-websocket) · [识别语音](https://learn.microsoft.com/azure/ai-services/speech-service/how-to-recognize-speech) |
| **语音合成**（流式，常见需经 **语音 SDK**） | **WebSocket** | `wss://{region}.tts.speech.microsoft.com/...`（路径与区域以官方为准；与 §3.2 **REST** 在线合成不同） | [Text to speech](https://learn.microsoft.com/azure/ai-services/speech-service/rest-text-to-speech) |

---

## 4. 阿里云（智能语音交互 / 视觉智能开放平台）

### 4.1 智能语音交互 — 公共说明

**鉴权**：各接口需在 **Header** `X-NLS-Token` 和/或 **Query/Body** 中携带 **服务鉴权 Token**，并与项目 **`appkey`** 配合使用（见 [获取 Token 概述](https://help.aliyun.com/zh/isi/developer-reference/overview-of-obtaining-an-access-token)）。

**地域占位**：下文 `{region}` 常见为 `cn-shanghai`、`cn-beijing`、`cn-shenzhen`。网关 Host 形如 `nls-gateway-{region}.aliyuncs.com`。

**官方文档索引**

| 能力 | 文档 |
|------|------|
| 一句话识别（REST） | [调用 RESTful API 实现一句话识别](https://help.aliyun.com/zh/isi/developer-reference/restful-api-2) |
| 语音合成（REST） | [使用 RESTful API 进行语音合成](https://help.aliyun.com/zh/isi/developer-reference/restful-api-3) |
| 录音文件识别（POP） | [录音文件识别接口调用指南](https://help.aliyun.com/zh/isi/developer-reference/api-reference-2) |
| 实时语音识别（WebSocket） | [实时语音识别接口的交互流程参数说明与服务状态码](https://help.aliyun.com/zh/isi/developer-reference/api-reference) |
| SSML | [SSML 概览](https://help.aliyun.com/zh/isi/developer-reference/ssml-overview) |

---

### 4.2 语音识别（ASR）

#### 4.2.1 一句话识别 — REST（`stream/v1/asr`）

**接口类型**：**HTTPS 或 HTTP · REST**（外网可用 HTTPS；ECS 内网仅 HTTP）。**POST** 上传整段音频（≤ 约 1 分钟），响应 **JSON**。**非 WebSocket**。

**路径**

| 访问类型 | 方法 | 完整 URL（示例地域） |
|----------|------|----------------------|
| 外网 | `POST` | `https://nls-gateway-{region}.aliyuncs.com/stream/v1/asr` |
| ECS 内网 | `POST` | `http://nls-gateway-{region}-internal.aliyuncs.com/stream/v1/asr` |

**Query 参数（上传二进制音频流时）**

| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `appkey` | String | 是 | 项目 Appkey |
| `format` | String | 否 | 音频格式：`pcm`、`wav`、`opus`、`speex`、`amr`、`mp3`、`aac` 等（与官方一致） |
| `sample_rate` | Integer | 否 | 采样率：`8000` 或 `16000`（Hz），默认 `16000` |
| `vocabulary_id` | String | 否 | 热词表 ID |
| `customization_id` | String | 否 | 自学习模型 ID |
| `enable_punctuation_prediction` | Boolean | 否 | 是否自动加标点，默认 `false` |
| `enable_inverse_text_normalization` | Boolean | 否 | 是否 ITN（中文数字转阿拉伯数字），默认 `false` |
| `enable_voice_detection` | Boolean | 否 | 是否语音检测（有效语音起止），默认 `false` |
| `disfluency` | Boolean | 否 | 是否过滤语气词（顺滑），默认 `false` |
| `audio_address` | String | 否 | 音频文件 **HTTPS 直链**（与 Body 二进制二选一）；传此参数时请求体可为空，Header 要求见官方「使用音频文件链接」 |

**Query 参数（使用音频 URL：`audio_address` 方式）**：在传 `audio_address` 时，除 `appkey` 等外，**无需** `Content-Type: application/octet-stream` 的二进制 Body；具体见 [一句话识别 · 使用音频文件链接](https://help.aliyun.com/zh/isi/developer-reference/restful-api-2)。

**请求头（上传二进制音频流）**

| 名称 | 必选 | 说明 |
|------|------|------|
| `X-NLS-Token` | 是 | 服务鉴权 Token |
| `Content-Type` | 是 | `application/octet-stream` |
| `Content-Length` | 是 | 请求体字节长度 |
| `Host` | 是 | 与 URL 中网关域名一致 |

**请求体**：二进制音频数据（单声道、16 bit；采样率与 `sample_rate`、控制台模型一致）。

**成功响应 JSON（示例字段）**

| 字段 | 说明 |
|------|------|
| `task_id` | 本次请求任务 ID（响应 Header 中亦可能带回） |
| `result` | 识别文本 |
| `status` | 状态码（如 `20000000` 表示成功） |
| `message` | 状态描述 |

#### 4.2.2 录音文件识别 — POP / RPC（`nls-filetrans`）

**接口类型**：**HTTPS · RPC**（`Action` + `Version`）。**非 WebSocket**。

**调用形态**：HTTPS 访问地域域名；公共参数含 `Action`、`Version`；业务参数在 Body（JSON）或 Query，以 [接口调用指南](https://help.aliyun.com/zh/isi/developer-reference/api-reference-2) 为准。

| 项目 | 值 |
|------|-----|
| **Endpoint（模式）** | `filetrans.{region}.aliyuncs.com` |
| **地域示例** | `cn-shanghai`、`cn-beijing`、`cn-shenzhen` |
| **API 版本** | `2018-08-17` |
| **Action** | `SubmitTask`、`GetTaskResult` 等 |

| 方法 | 路径 | 说明 |
|------|------|------|
| `SubmitTask` | `POST https://filetrans.{region}.aliyuncs.com/`（`Action=SubmitTask`，`Version=2018-08-17`） | 提交录音文件识别任务 |
| `GetTaskResult` | `GET https://filetrans.{region}.aliyuncs.com/`（`Action=GetTaskResult` 等） | 查询任务结果 |

**说明**：支持 **轮询** 与 **回调**；极速版、语音流异步识别等为独立文档，域名/参数可能不同。

**OpenAPI**：[nls-filetrans · SubmitTask](https://next.api.alibabacloud.com/document/nls-filetrans/2018-08-17/SubmitTask)

---

### 4.3 语音合成（TTS）

#### 4.3.1 REST（`stream/v1/tts`）

**接口类型**：**HTTPS 或 HTTP · REST**；支持 **`GET`** 与 **`POST`**。**非 WebSocket**（流式低延迟见官方「流式合成」与 SDK 示例）。

**路径**

| 访问类型 | 方法 | 完整 URL（示例） |
|----------|------|------------------|
| 外网 | `GET` / `POST` | `https://nls-gateway-{region}.aliyuncs.com/stream/v1/tts` |
| ECS 内网 | `GET` / `POST` | `http://nls-gateway-{region}-internal.aliyuncs.com/stream/v1/tts` |

**请求参数（GET 与 POST 一致；GET 用 Query，POST 可放 JSON Body）**

| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `appkey` | String | 是 | 项目 appkey |
| `text` | String | 是 | 待合成文本，UTF-8；**GET** 需再按 RFC 3986 做 urlencode；**POST JSON** 内 **不要** 对正文再做 urlencode |
| `token` | String | 否 | 若不传，则用 Header `X-NLS-Token` |
| `format` | String | 否 | 音频格式：`pcm`、`wav`、`mp3` 等，默认 `pcm` |
| `sample_rate` | Integer | 否 | `8000` 或 `16000`（Hz），默认 `16000` |
| `voice` | String | 否 | 发音人（见控制台音色列表） |
| `volume` | Integer | 否 | 音量 `0`～`100`，默认 `50` |
| `speech_rate` | Integer | 否 | 语速 `-500`～`500`，默认 `0` |
| `pitch_rate` | Integer | 否 | 语调 `-500`～`500`，默认 `0` |

**请求头**

| 名称 | 说明 |
|------|------|
| `X-NLS-Token` | 鉴权 Token（与参数 `token` 二选一方式配合） |
| `Content-Type` | **`POST` JSON 时必选** `application/json` |
| `Content-Length` | `POST` 时可选 |

**响应**

- **成功**：Header `Content-Type` 随 `format` 而定（如 `audio/mpeg`、`audio/pcm` 等）；**Body** 为合成音频二进制。Header 中常含 `X-NLS-RequestId`（对应任务标识）。
- **失败**：`Content-Type` 为 `application/json` 或缺省；Body 为 JSON，含 `task_id`、`status`、`message` 等（见官方 [响应结果](https://help.aliyun.com/zh/isi/developer-reference/restful-api-3)）。

**`POST` JSON 请求体示例（字段与上表一致）**

```json
{
  "appkey": "你的appkey",
  "text": "今天是周一，天气挺好的。",
  "token": "服务鉴权Token",
  "format": "wav",
  "sample_rate": 16000
}
```

**限制**：单次上传文本长度上限（如 **300 字符**，超长截断）以官方为准；长文本需客户端分句或多请求，参见 SDK 示例。

---

### 4.4 实时语音识别 — WebSocket

**接口类型**：**WebSocket**（`wss` / `ws`）。与 §4.2.1 **REST**、§4.2.2 **POP** 不同。

**就近地域智能接入（推荐）**

| 传输 | URL |
|------|-----|
| `WebSocket` | `wss://nls-gateway.aliyuncs.com/ws/v1`（按客户端地理位置解析到最近地域） |

**按地域固定接入**

| 访问类型 | URL |
|----------|-----|
| 外网 `wss` | `wss://nls-gateway-{region}.aliyuncs.com/ws/v1` |
| ECS 内网 `ws` | `ws://nls-gateway-{region}-internal.aliyuncs.com:80/ws/v1` |

**交互流程（概要）**

1. **鉴权**：建立 WebSocket 后按协议发送带 Token 的鉴权消息（详见 [接口说明](https://help.aliyun.com/zh/isi/developer-reference/api-reference)）。
2. **开始识别**：在首条控制消息中配置参数（与 SDK `SpeechTranscriber` 的 set 项对应），常见字段如下。

**开始识别 — 常用参数**

| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `appkey` | String | 是 | 项目 appkey |
| `format` | String | 否 | 音频格式，同一句话识别 |
| `sample_rate` | Integer | 否 | 默认 `16000`，须与控制台模型一致 |
| `enable_intermediate_result` | Boolean | 否 | 是否返回中间识别结果，默认 `false` |
| `enable_punctuation_prediction` | Boolean | 否 | 是否加标点，默认 `false` |
| `enable_inverse_text_normalization` | Boolean | 否 | 是否 ITN，默认 `false` |
| `customization_id` | String | 否 | 自学习模型 ID |
| `vocabulary_id` | String | 否 | 定制泛热词 ID |
| `max_sentence_silence` | Integer | 否 | 断句静音阈值（ms），约 `200`～`6000`，默认 `800` |
| `enable_words` | Boolean | 否 | 是否返回词级信息，默认 `false` |
| `disfluency` | Boolean | 否 | 是否过滤语气词，默认 `false` |
| `speech_noise_threshold` | Float | 否 | 噪音阈值，约 `[-1, 1]`，高级参数 |
| `enable_semantic_sentence_detection` | Boolean | 否 | 语义断句；需与 `enable_intermediate_result=true` 配合 |
| `special_word_filter` | JSON 字符串 | 否 | 敏感词过滤等 |

3. **发送音频**：连接保持，按协议向服务端发送二进制音频帧。
4. **接收结果**：服务端 JSON 消息，`header.namespace` 多为 `SpeechTranscriber`，`header.name` 常见事件如下。

**下行事件（`header.name` 摘选）**

| 事件名 | 含义 |
|--------|------|
| `SentenceBegin` | 检测到句子开始 |
| `TranscriptionResultChanged` | 句中结果变化（中间结果；需 `enable_intermediate_result=true`） |
| `SentenceEnd` | 句子结束及该句最终结果（可含词信息、情感等，依参数与模型） |

**消息 JSON 结构（概要）**：每条消息含 `header` 与 `payload`。`header` 含 `namespace`（多为 `SpeechTranscriber`）、`name`（事件名）、`status`、`message_id`、`task_id`、`status_text`；`payload` 含句子索引 `index`、时间 `time`、`result`、可选 `words` / `confidence` / `emo_tag` 等（见官方示例）。

5. **结束识别**：通知服务端语音数据发送完成，服务端在识别结束后通知客户端完毕（报文名与帧格式见 [接口说明](https://help.aliyun.com/zh/isi/developer-reference/api-reference) 与 SDK）；**Task_id** 等在响应 Header 或消息体中返回，便于排障。

**服务状态码与完整事件、鉴权报文格式**：见 [实时语音识别 · 接口说明](https://help.aliyun.com/zh/isi/developer-reference/api-reference)。

---

### 4.5 视觉智能开放平台（viapi）

**接口类型**：下表各类目均为 **HTTPS · RPC**（对 Endpoint 发 **HTTPS**，请求体为 **RPC 形态**：含 **Action**、业务参数等；**不是** REST 风格资源路径为主的那类）。**不提供** 面向这些能力的 **WebSocket** 表（与 §4.4 **WebSocket** 实时语音区分）。

**调用形态**：按类目使用不同 **Endpoint**；具体 **Action**（如 `RecognizeFace`、各类 OCR）见各能力文档。

**华东 2（上海）— 外网 Endpoint 全集**（与 [访问域名](https://help.aliyun.com/zh/viapi/getting-started/access-to-the-domain-name) 对照表一致；**内网** 为对应 `*-vpc.cn-shanghai.aliyuncs.com`）：

| 接口类型 | 路径（HTTPS Endpoint） | 说明 |
|----------|------------------------|------|
| HTTPS · RPC | `facebody.cn-shanghai.aliyuncs.com` | 人脸人体 |
| HTTPS · RPC | `ocr.cn-shanghai.aliyuncs.com`（部分能力亦支持 `ocr.cn-shenzhen.aliyuncs.com`） | 文字识别 |
| HTTPS · RPC | `goodstech.cn-shanghai.aliyuncs.com` | 商品理解 |
| HTTPS · RPC | `imageaudit.cn-shanghai.aliyuncs.com` | 内容审核 |
| HTTPS · RPC | `imagerecog.cn-shanghai.aliyuncs.com` | 图像识别 |
| HTTPS · RPC | `imageenhan.cn-shanghai.aliyuncs.com` | 图像生产 |
| HTTPS · RPC | `imageseg.cn-shanghai.aliyuncs.com` | 分割抠图 |
| HTTPS · RPC | `imgsearch.cn-shanghai.aliyuncs.com` | 视觉搜索 |
| HTTPS · RPC | `imageprocess.cn-shanghai.aliyuncs.com` | 图像分析处理 |
| HTTPS · RPC | `objectdet.cn-shanghai.aliyuncs.com` | 目标检测 |
| HTTPS · RPC | `videorecog.cn-shanghai.aliyuncs.com` | 视频理解 |
| HTTPS · RPC | `videoenhan.cn-shanghai.aliyuncs.com` | 视频生产 |
| HTTPS · RPC | `videoseg.cn-shanghai.aliyuncs.com` | 视频分割 |
| HTTPS · RPC | `viapi.cn-shanghai.aliyuncs.com` | 异步任务管理 |

**文档**：[视觉智能开放平台](https://help.aliyun.com/zh/viapi/) · [访问域名](https://help.aliyun.com/zh/viapi/getting-started/access-to-the-domain-name) · [各能力 API 说明](https://help.aliyun.com/zh/viapi/developer-reference/)

---

## 5. 腾讯云

**调用形态**：`POST https://<product>.tencentcloudapi.com`；公共参数 `Action`、`Version`、`Region`；业务参数 JSON body。

**接口类型小结**：§5.1、§5.3 为 **HTTPS · RPC**（**非 WebSocket**）；**实时语音识别**见 §5.2（**WebSocket** 等长连接）。

### 5.1 语音识别（ASR）— API 3.0 Action 全集

**接口类型**：**HTTPS POST · RPC**（`Action` 区分操作）。与 §5.2 **WebSocket** 实时识别不是同一套接入。

下列 **Action** 与 [腾讯云 Python SDK `asr/v20190614`](https://github.com/TencentCloud/tencentcloud-sdk-python/tree/master/tencentcloud/asr/v20190614) 客户端方法一一对应（与控制台文档中的英文 Action 名一致）。

| 方法 | 路径 | 说明 |
|------|------|------|
| `CloseAsyncRecognitionTask` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 关闭语音流异步识别任务 |
| `CreateAsrKeyWordLib` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 创建热词表 |
| `CreateAsrVocab` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 创建自学习语料表 |
| `CreateAsyncRecognitionTask` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 创建语音流异步识别任务 |
| `CreateCustomization` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 创建自学习模型 |
| `CreateRecTask` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 创建录音文件识别任务 |
| `DeleteAsrKeyWordLib` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 删除热词表 |
| `DeleteAsrVocab` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 删除语料表 |
| `DeleteCustomization` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 删除自学习模型 |
| `DescribeAsyncRecognitionTasks` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 查询语音流异步识别任务列表 |
| `DescribeTaskStatus` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 查询录音文件识别任务状态 |
| `DownloadAsrVocab` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 下载语料表 |
| `DownloadCustomization` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 下载自学习模型语料 |
| `GetAsrKeyWordLibList` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 列举热词表 |
| `GetAsrVocab` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 获取语料表 |
| `GetAsrVocabList` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 列举语料表 |
| `GetCustomizationList` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 列举自学习模型 |
| `GetModelInfo` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 获取自学习模型信息 |
| `GetUsageByDate` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 按日查询用量 |
| `ModifyCustomization` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 更新自学习模型 |
| `ModifyCustomizationState` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 修改自学习模型状态 |
| `SentenceRecognition` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 一句话识别 |
| `SetVocabState` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 设置热词表状态 |
| `UpdateAsrKeyWordLib` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 更新热词表 |
| `UpdateAsrVocab` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 更新语料表 |
| `VoicePrintCompare` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 声纹比对 |
| `VoicePrintCount` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 声纹注册数量统计 |
| `VoicePrintDelete` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 声纹删除 |
| `VoicePrintEnroll` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 声纹注册 |
| `VoicePrintGroupVerify` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 声纹组验证 |
| `VoicePrintUpdate` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 声纹更新 |
| `VoicePrintVerify` | `POST https://asr.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 声纹验证 |

**文档**：[语音识别 API 概览](https://cloud.tencent.com/document/product/1093/101674) · [API 中心](https://cloud.tencent.com/document/api/1093/35646)

### 5.2 实时语音识别

**接口类型**：**WebSocket**（或文档约定的 **长连接**；**非** §5.1 的 HTTP RPC）。产品与录音文件识别可能不同 `product`/`endpoint`；协议与参数见 [实时语音识别（WebSocket）](https://cloud.tencent.com/document/product/1093/48982)。

| 传输 | 入口 URL（摘要） | 说明 |
|------|------------------|------|
| `WebSocket` | `wss://asr.cloud.tencent.com/asr/v2/<appid>?{请求参数}` | 握手地址；`<appid>` 为应用 ID，问号后为鉴权与引擎等查询参数（见官方示例） |

**文档**：[实时语音识别 API](https://www.tencentcloud.com/zh/document/api/1118/53937) · [WebSocket 接入说明](https://cloud.tencent.com/document/product/1093/48982)

### 5.3 语音合成（TTS）— API 3.0 Action

**接口类型**：**HTTPS POST · RPC**（与 §5.1 相同形态）。

与 [腾讯云 Python SDK `tts/v20190823`](https://github.com/TencentCloud/tencentcloud-sdk-python/tree/master/tencentcloud/tts/v20190823) 对齐：

| 方法 | 路径 | 说明 |
|------|------|------|
| `CreateTtsTask` | `POST https://tts.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 创建异步语音合成任务 |
| `DescribeTtsTaskStatus` | `POST https://tts.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 查询异步合成任务状态 |
| `TextToVoice` | `POST https://tts.tencentcloudapi.com/`（`Action` 与「方法」列同名） | 基础语音合成（文本转语音） |

**文档**：[语音技术](https://cloud.tencent.com/document/product/1073)

### 5.4 视觉

图像分析、OCR、人脸等分散在多条产品线，见 [人工智能](https://cloud.tencent.com/document/product/865) 下各 API 文档。

---

## 6. OpenAI API（平台型）

**Base**：`https://api.openai.com/v1`（或企业部署等价地址）。

**接口类型**：**HTTPS · REST**（下表 **Audio**）；**Realtime** 为 **WebSocket**（**§6.2**）。**非** 腾讯云式 RPC `Action` 表。

### 6.1 Audio（HTTPS · REST）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v1/audio/transcriptions` | 语音转写为文本 |
| `POST` | `/v1/audio/translations` | 语音译为英文文本 |
| `POST` | `/v1/audio/speech` | 文本转语音 |

**文档**：[Audio · API Reference](https://platform.openai.com/docs/api-reference/audio)

### 6.2 Realtime API（WebSocket）

**接口类型**：**WebSocket**（低延迟语音/多模态对话等；与 **§6.1** 单次 HTTP **Audio** 不同）。

| 传输 | 入口 URL（摘要） | 说明 |
|------|------------------|------|
| `WebSocket` | `wss://api.openai.com/v1/realtime?model=...` | 鉴权与模型等查询参数以 [官方指南](https://platform.openai.com/docs/guides/realtime-websocket) 为准 |

**文档**：[Realtime API · WebSocket](https://platform.openai.com/docs/guides/realtime-websocket)

---

## 7. 与自建网关对照

| 能力域 | 本文档（云厂商） | 自建（`ai-gateway.md`） |
|--------|------------------|-------------------------|
| ASR | 多形态：同步、异步任务、流式、词表/定制 | `POST /asr/recognize` + `WebSocket /asr/stream`（§3.3）+ `languages` / `config` / `info` |
| TTS | 合成 + 音色枚举 + 常含 SSML/长音频 | `POST /tts/synthesize` + `WebSocket /tts/stream`（§4.4，可选）+ `backends` / `speakers` / `config` |
| VAD | 多并入流式 ASR | `POST /vad/detect`、`/vad/scan` 等（显式 REST） |
| Vision | 单端点多 Feature（Google）或多 API（AWS） | `POST /v1/infer/*`、`tracking`、`sequence` + `GET /openapi.json` |

---

*表格为便于对照的整理；上线前请以各云官方 API 参考 / Discovery / OpenAPI 为准。*
