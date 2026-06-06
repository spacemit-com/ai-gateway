// 模型元数据 —— 先用静态 fallback，App 启动后从后端拉取覆盖
// 静态 ID 已对齐后端真实值（sensevoice / matcha_zh / silero 等）

window.MODEL_CATALOG = {
  voice: [
    {
      id: 'sensevoice', name: 'SenseVoice', icon: 'mic', domain: 'asr',
      desc: '多语种语音理解模型，支持语音识别、情感识别等能力。',
      meta: [['模型类型', '语音识别'], ['语言支持', '多语种']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'qwen3-asr', name: 'Qwen3-ASR', icon: 'mic', domain: 'asr',
      desc: 'Qwen3 语音识别模型，支持多语种。',
      meta: [['模型类型', '语音识别'], ['特点', 'LLM-based']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'matcha_zh', name: 'Matcha-TTS 中文', icon: 'mic', domain: 'tts',
      desc: '中文语音合成模型，高效文本转语音。',
      meta: [['模型类型', '语音合成'], ['语种', '中文']],
      sample_rates: [22050, 16000],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'matcha_en', name: 'Matcha-TTS English', icon: 'mic', domain: 'tts',
      desc: '英语语音合成模型。',
      meta: [['模型类型', '语音合成'], ['语种', 'English']],
      sample_rates: [22050, 16000],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'matcha_zh_en', name: 'Matcha-TTS 中英', icon: 'mic', domain: 'tts',
      desc: '中英双语语音合成模型。',
      meta: [['模型类型', '语音合成'], ['语种', '中英双语']],
      sample_rates: [22050, 16000],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'kokoro', name: 'Kokoro-TTS', icon: 'mic', domain: 'tts',
      desc: '多语种高质量语音合成。',
      meta: [['模型类型', '语音合成'], ['特点', '多语种']],
      sample_rates: [24000],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'silero', name: 'Silero VAD', icon: 'activity', domain: 'vad',
      desc: '语音活动检测模型，用于判断音频中是否包含语音。',
      meta: [['模型类型', '语音检测'], ['采样率', '16kHz']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
  ],
  vlm: [
    {
      id: 'fastvlm-mm-0.5b-q4_1', name: 'FastVLM-MM 0.5B', icon: 'image', domain: 'vlm',
      capabilities: ['vlm'],
      desc: 'FastVLM 轻量视觉语言模型，支持图片理解与对话。',
      meta: [['类型', '视觉语言'], ['规模', '0.5B']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'Qwen3.5-0.8B', name: 'Qwen3.5-0.8B', icon: 'image', domain: 'vlm',
      capabilities: ['vlm'],
      desc: 'Qwen3.5 0.8B 视觉语言模型，适合嵌入式图片问答。',
      meta: [['类型', '视觉语言'], ['规模', '0.8B']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'Qwen3.5-2B', name: 'Qwen3.5-2B', icon: 'image', domain: 'vlm',
      capabilities: ['vlm'],
      desc: 'Qwen3.5 2B 视觉语言模型，支持图片理解与对话。',
      meta: [['类型', '视觉语言'], ['规模', '2B']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'Qwen3.5-4B', name: 'Qwen3.5-4B', icon: 'image', domain: 'vlm',
      capabilities: ['vlm'],
      desc: 'Qwen3.5 4B 视觉语言模型，支持更强的多模态理解。',
      meta: [['类型', '视觉语言'], ['规模', '4B']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'qwen30ba3b-mm-q4_1', name: 'Qwen3 30B-A3B MM', icon: 'image', domain: 'vlm',
      capabilities: ['vlm'],
      desc: 'Qwen3 MoE 视觉语言模型，适合高能力图片理解场景。',
      meta: [['类型', '视觉语言'], ['规模', '30B-A3B']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
  ],
  vision: [
    {
      id: 'yolov11n', name: 'YOLOv11n', icon: 'eye', domain: 'vision',
      capabilities: ['detect'],
      desc: 'YOLOv11 Nano 轻量目标检测。',
      meta: [['模型类型', '目标检测'], ['精度', 'INT8']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'yolov11s', name: 'YOLOv11s', icon: 'eye', domain: 'vision',
      capabilities: ['detect'],
      desc: 'YOLOv11 Small 目标检测。',
      meta: [['模型类型', '目标检测'], ['精度', 'INT8']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'yolov11m', name: 'YOLOv11m', icon: 'eye', domain: 'vision',
      capabilities: ['detect'],
      desc: 'YOLOv11 Medium 目标检测。',
      meta: [['模型类型', '目标检测'], ['精度', 'INT8']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'yolov8n', name: 'YOLOv8n', icon: 'eye', domain: 'vision',
      capabilities: ['detect'],
      desc: 'YOLOv8 Nano 目标检测，适合嵌入式部署。',
      meta: [['模型类型', '目标检测'], ['精度', 'INT8']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'yolov8s', name: 'YOLOv8s', icon: 'eye', domain: 'vision',
      capabilities: ['detect'],
      desc: 'YOLOv8 Small 目标检测。',
      meta: [['模型类型', '目标检测'], ['精度', 'INT8']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'yolov8m', name: 'YOLOv8m', icon: 'eye', domain: 'vision',
      capabilities: ['detect'],
      desc: 'YOLOv8 Medium 目标检测。',
      meta: [['模型类型', '目标检测'], ['精度', 'INT8']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'yolov5-face', name: 'YOLOv5-Face', icon: 'eye', domain: 'vision',
      capabilities: ['detect'],
      desc: 'YOLOv5 人脸检测。',
      meta: [['模型类型', '人脸检测'], ['精度', 'INT8']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'yolov5-gesture', name: 'YOLOv5-Gesture', icon: 'eye', domain: 'vision',
      capabilities: ['detect'],
      desc: '手势检测模型，识别常见手势动作。',
      meta: [['模型类型', '手势检测'], ['精度', 'INT8']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'yolov8n-pose', name: 'YOLOv8n-Pose', icon: 'eye', domain: 'vision',
      capabilities: ['detect', 'pose'],
      desc: '人体姿态估计，17 COCO 关键点 + 骨骼连线。',
      meta: [['模型类型', '姿态估计'], ['关键点', '17 COCO']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'yolov8s-pose', name: 'YOLOv8s-Pose', icon: 'eye', domain: 'vision',
      capabilities: ['detect', 'pose'],
      desc: 'YOLOv8 Small 姿态估计。',
      meta: [['模型类型', '姿态估计'], ['关键点', '17 COCO']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'yolov8m-pose', name: 'YOLOv8m-Pose', icon: 'eye', domain: 'vision',
      capabilities: ['detect', 'pose'],
      desc: 'YOLOv8 Medium 姿态估计。',
      meta: [['模型类型', '姿态估计'], ['关键点', '17 COCO']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'yolov8n-seg', name: 'YOLOv8n-Seg', icon: 'eye', domain: 'vision',
      capabilities: ['detect', 'segment'],
      desc: '实例分割模型，检测目标并输出分割掩码。',
      meta: [['模型类型', '实例分割'], ['精度', 'INT8']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'yolov8s-seg', name: 'YOLOv8s-Seg', icon: 'eye', domain: 'vision',
      capabilities: ['detect', 'segment'],
      desc: 'YOLOv8 Small 实例分割。',
      meta: [['模型类型', '实例分割'], ['精度', 'INT8']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'yolov8m-seg', name: 'YOLOv8m-Seg', icon: 'eye', domain: 'vision',
      capabilities: ['detect', 'segment'],
      desc: 'YOLOv8 Medium 实例分割。',
      meta: [['模型类型', '实例分割'], ['精度', 'INT8']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'resnet50', name: 'ResNet-50', icon: 'eye', domain: 'vision',
      capabilities: ['classify'],
      desc: '通用图像分类模型，ImageNet Top-5 输出。',
      meta: [['模型类型', '图像分类'], ['骨干网络', 'ResNet-50']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'emotion', name: 'Emotion', icon: 'eye', domain: 'vision',
      capabilities: ['classify', 'emotion'],
      desc: '人脸情绪识别，支持 7 种基础情绪分类。',
      meta: [['模型类型', '情绪识别'], ['类别数', '7']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'bytetrack', name: 'ByteTrack', icon: 'eye', domain: 'vision',
      capabilities: ['detect', 'track'],
      desc: '多目标跟踪，基于 YOLOv8 检测 + ByteTrack 关联。',
      meta: [['模型类型', '目标跟踪'], ['跟踪器', 'ByteTrack']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'ocsort', name: 'OC-SORT', icon: 'eye', domain: 'vision',
      capabilities: ['detect', 'track'],
      desc: '多目标跟踪，使用 OC-SORT 算法进行目标关联。',
      meta: [['模型类型', '目标跟踪'], ['跟踪器', 'OC-SORT']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'arcface', name: 'ArcFace', icon: 'eye', domain: 'vision',
      capabilities: ['embedding'],
      desc: '人脸识别模型，支持人脸特征提取与比对。',
      meta: [['模型类型', '人脸识别'], ['骨干网络', 'ResNet']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
  ],
  text: [
    {
      id: 'qwen3-0.6b', name: 'Qwen3-0.6B', icon: 'grid', domain: 'llm',
      desc: 'Qwen3 0.6B 轻量大语言模型，适合嵌入式推理。',
      meta: [['参数规模', '0.6B'], ['格式', 'GGUF']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'qwen3-1.7b', name: 'Qwen3-1.7B', icon: 'grid', domain: 'llm',
      desc: 'Qwen3 1.7B 大语言模型。',
      meta: [['参数规模', '1.7B'], ['格式', 'GGUF']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
    {
      id: 'hy-mt1.5-1.8b-q4_k_m', name: 'HY-MT 1.8B', icon: 'languages', domain: 'llm',
      task: 'translate',
      desc: '火山翻译模型 1.8B，支持中英双向翻译。',
      meta: [['参数规模', '1.8B'], ['格式', 'Q4_K_M'], ['任务', '翻译']],
      status: 'idle', calls: 0, latencyMs: 0,
    },
  ],
};

const VISION_MODEL_ALIASES = {
  yolov8: 'yolov8n',
  yolov11: 'yolov11n',
  yolov5_gesture: 'yolov5-gesture',
  'yolov8-pose': 'yolov8n-pose',
  'yolov8-seg': 'yolov8n-seg',
};

function visionCanonicalId(id) {
  const alias = VISION_MODEL_ALIASES[id] || id;
  return window.visionBackendModelId ? window.visionBackendModelId(alias) : alias;
}

function visionCatalogMeta(id) {
  const catalog = window.MODEL_CATALOG?.vision || [];
  const exact = catalog.find(m => m.id === id);
  if (exact) return exact;
  const canonical = visionCanonicalId(id);
  return catalog.find(m => m.id === canonical) || null;
}

const VLM_MODEL_META_ALIASES = {
  'qwen2.5-vl-3b': {
    id: 'qwen2.5-vl-3b', name: 'Qwen2.5-VL-3B', icon: 'image', domain: 'vlm',
    capabilities: ['vlm'],
    desc: 'Qwen2.5 3B 视觉语言模型，支持图像理解与对话。',
    meta: [['参数规模', '3B'], ['格式', 'GGUF']],
    status: 'idle', calls: 0, latencyMs: 0,
  },
};

function vlmCatalogMeta(id) {
  const catalog = window.MODEL_CATALOG?.vlm || [];
  return catalog.find(m => m.id === id) || VLM_MODEL_META_ALIASES[id] || null;
}

function dedupeCatalogModels(models) {
  const seen = new Set();
  return models.filter(m => {
    const key = m.domain + '-' + m.id;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// 从后端拉取真实模型列表，覆盖静态数据
window.initModelCatalog = async function() {
  const { asrApi, ttsApi, vadApi, visionApi, llmApi, vlmApi } = window;
  try {
    const [asrModels, ttsModels, vadModels, visionModelsRaw, llmModels, vlmModelsRaw] = await Promise.all([
      asrApi.listModels().catch(() => []),
      ttsApi.listModels().catch(() => []),
      vadApi.listModels().catch(() => []),
      visionApi.listModels().catch(() => []),
      llmApi.listModels().catch(() => []),
      vlmApi.listModels().catch(() => []),
    ]);

    const visionModels = Array.isArray(visionModelsRaw) ? visionModelsRaw : (visionModelsRaw.data || []);
    const vlmModels = Array.isArray(vlmModelsRaw) ? vlmModelsRaw : (vlmModelsRaw.data || []);

    // TTS: 按 id 分组，合并 sample_rates（去重）
    const ttsGrouped = {};
    for (const m of ttsModels) {
      if (!ttsGrouped[m.id]) {
        ttsGrouped[m.id] = { ...m, sample_rates: new Set() };
      }
      if (m.sample_rate) ttsGrouped[m.id].sample_rates.add(m.sample_rate);
      if (m.loaded) ttsGrouped[m.id].loaded = true;
    }

    const backendIds = new Set();
    const voice = [
      ...asrModels.map(m => {
        backendIds.add('asr-' + m.id);
        return {
          id: m.id, name: m.name || m.id, icon: 'mic', domain: 'asr',
          desc: 'ASR · ' + (m.languages || []).join('/'),
          meta: [['类型', '语音识别'], ['语言', (m.languages || []).join(', ') || '-']],
          status: m.loaded ? 'ready' : 'idle', calls: 0, latencyMs: 0,
        };
      }),
      ...Object.values(ttsGrouped).map(m => {
        backendIds.add('tts-' + m.id);
        const rates = [...m.sample_rates];
        return {
          id: m.id, name: m.name || m.id, icon: 'mic', domain: 'tts',
          desc: 'TTS · ' + rates.map(r => r + 'Hz').join(' / '),
          meta: [['类型', '语音合成'], ['采样率', rates.map(r => r + 'Hz').join(', ') || '-']],
          sample_rates: rates,
          status: m.loaded ? 'ready' : 'idle', calls: 0, latencyMs: 0,
        };
      }),
      ...vadModels.map(m => {
        backendIds.add('vad-' + m.id);
        return {
          id: m.id, name: m.name || m.id, icon: 'activity', domain: 'vad',
          desc: 'VAD 语音活动检测',
          meta: [['类型', '语音检测'], ['采样率', (m.sample_rate || 16000) + 'Hz']],
          status: m.loaded ? 'ready' : 'idle', calls: 0, latencyMs: 0,
        };
      }),
    ];
    const staticVoice = (window.MODEL_CATALOG.voice || []).filter(
      m => !backendIds.has(m.domain + '-' + m.id)
    );
    if (voice.length > 0) {
      window.MODEL_CATALOG = { ...window.MODEL_CATALOG, voice: [...voice, ...staticVoice] };
    }

    // Vision models
    const visionDescMap = {
      detect: '目标检测', pose: '姿态估计', segment: '实例分割',
      classify: '图像分类', emotion: '情绪识别', embedding: '特征提取',
      track: '目标跟踪', vlm: '视觉语言',
    };
    const buildVisionDesc = (caps) => caps.map(c => visionDescMap[c] || c).join(' + ') || 'Vision';
    const vlmStatusMap = {
      loaded: 'ready', loading: 'ready', ready: 'ready',
      downloaded: 'idle', available: 'idle', downloading: 'idle', unloaded: 'idle',
      error: 'offline', offline: 'offline',
    };
    const vlmDisplayStatus = (status) => vlmStatusMap[status] || 'idle';

    const mappedVisionModels = visionModels.map(m => {
      const rawModelId = m.model_id || m.id;
      if (!rawModelId) return null;
      const modelId = visionCanonicalId(rawModelId);
      const meta = visionCatalogMeta(modelId) || visionCatalogMeta(rawModelId);
      const caps = (meta?.capabilities?.length ? meta.capabilities : m.capabilities) || [];
      let domain = 'vision';
      if (meta?.domain) domain = meta.domain;
      else if (caps.includes('vlm') || modelId.toLowerCase().includes('vl')) domain = 'vlm';
      return {
        ...(meta || {}),
        id: modelId,
        name: meta?.name || modelId,
        icon: meta?.icon || (domain === 'vlm' ? 'image' : 'eye'),
        domain,
        capabilities: caps,
        desc: meta?.desc || (domain === 'vlm' ? '视觉语言模型' : buildVisionDesc(caps)),
        meta: [
          ...(meta?.meta || [['类型', domain === 'vlm' ? '视觉语言' : buildVisionDesc(caps)]]),
          ['后端', m.backend || '-'],
        ],
        status: domain === 'vlm' ? vlmDisplayStatus(m.status) : (m.status === 'ready' ? 'ready' : 'idle'),
        calls: 0, latencyMs: 0,
      };
    }).filter(Boolean);
    const visionList = dedupeCatalogModels(mappedVisionModels.filter(m => m.domain !== 'vlm'));
    const vlmFromVisionList = dedupeCatalogModels(mappedVisionModels.filter(m => m.domain === 'vlm'));

    const primaryVlmList = vlmModels.map(m => {
      const modelId = m.id || m.model || m.model_id;
      if (!modelId) return null;
      const meta = vlmCatalogMeta(modelId);
      const displayStatus = vlmDisplayStatus(m.status);
      const source = m.source_type === 'remote'
        ? (m.api_base_url || 'Remote API')
        : (m.url || m.local_path || 'Local VLM');
      return {
        ...(meta || {}),
        id: modelId, name: meta?.name || modelId, icon: meta?.icon || 'image', domain: 'vlm',
        source_type: m.source_type,
        url: m.url,
        local_path: m.local_path,
        api_base_url: m.api_base_url,
        is_preset: m.is_preset,
        capabilities: ['vlm'],
        desc: meta?.desc || ((m.source_type === 'remote' ? 'Remote · ' : 'VLM · ') + source),
        meta: [['类型', '视觉语言'], ['来源', m.source_type || '-'], ['状态', displayStatus]],
        status: displayStatus, calls: 0, latencyMs: 0,
      };
    }).filter(Boolean);

    if (visionList.length > 0) {
      const liveIds = new Set(visionList.map(m => m.domain + '-' + m.id));
      const staticVision = (window.MODEL_CATALOG.vision || []).filter(
        m => !liveIds.has(m.domain + '-' + m.id)
      );
      window.MODEL_CATALOG = { ...window.MODEL_CATALOG, vision: [...visionList, ...staticVision] };
    }

    if (primaryVlmList.length > 0 || vlmFromVisionList.length > 0) {
      // Prefer the dedicated VLM endpoint when both APIs report the same model.
      const liveVlm = dedupeCatalogModels([...primaryVlmList, ...vlmFromVisionList]);
      const liveIds = new Set(liveVlm.map(m => m.domain + '-' + m.id));
      const staticVlm = (window.MODEL_CATALOG.vlm || []).filter(
        m => !liveIds.has(m.domain + '-' + m.id)
      );
      window.MODEL_CATALOG = { ...window.MODEL_CATALOG, vlm: [...liveVlm, ...staticVlm] };
    }

    // LLM models
    const llmList = Array.isArray(llmModels) ? llmModels : [];
    const llmBackendIds = new Set();
    const TRANSLATE_MODELS = ['hy-mt'];
    const isTranslateModel = (id) => TRANSLATE_MODELS.some(p => id.toLowerCase().includes(p));
    const text = llmList.map(m => {
      llmBackendIds.add('llm-' + m.id);
      const statusMap = { loaded: 'ready', loading: 'ready', available: 'idle',
                          downloaded: 'idle', downloading: 'idle', error: 'offline' };
      const isTrans = isTranslateModel(m.id);
      return {
        id: m.id, name: m.id, icon: isTrans ? 'languages' : 'grid', domain: 'llm',
        ...(isTrans ? { task: 'translate' } : {}),
        desc: isTrans ? '火山翻译模型，支持中英双向翻译' : (m.source_type === 'remote' ? 'Remote · ' : 'Local · ') + (m.url || m.local_path || 'GGUF'),
        meta: [['来源', m.source_type || '-'], ['状态', m.status || '-']],
        status: statusMap[m.status] || 'idle', calls: 0, latencyMs: 0,
      };
    });
    const staticText = (window.MODEL_CATALOG.text || []).filter(
      m => !llmBackendIds.has(m.domain + '-' + m.id)
    );
    if (text.length > 0) {
      window.MODEL_CATALOG = { ...window.MODEL_CATALOG, text: [...text, ...staticText] };
    }

    window.dispatchEvent(new CustomEvent('model-catalog-updated'));
  } catch (e) {
    console.warn('[initModelCatalog] fallback to static data:', e.message);
  }
};

// 客户端历史记录（localStorage 持久化，audioUrl 仅当前会话有效）
window.historyStore = {
  _key: 'spacemit_ai_gateway_history',
  _max: 200,
  _audioCache: {},
  getAll() {
    try {
      const arr = JSON.parse(localStorage.getItem(this._key)) || [];
      for (const r of arr) {
        if (this._audioCache[r.id]) r.audioUrl = this._audioCache[r.id];
      }
      return arr;
    } catch { return []; }
  },
  push(record) {
    const arr = this.getAll();
    const id = 'h-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6);
    if (record.audioUrl) {
      this._audioCache[id] = record.audioUrl;
    }
    const toStore = { ...record };
    delete toStore.audioUrl;
    arr.unshift({
      id,
      time: new Date().toLocaleString('zh-CN'),
      ...toStore,
    });
    if (arr.length > this._max) arr.length = this._max;
    localStorage.setItem(this._key, JSON.stringify(arr));
    window.dispatchEvent(new CustomEvent('history-updated'));
  },
  clear() {
    this._audioCache = {};
    localStorage.removeItem(this._key);
    window.dispatchEvent(new CustomEvent('history-updated'));
  },
};

// Page state persistence (localStorage)
window.pageStateStore = {
  _k: (domain, modelId) => `spacemit_ai_gateway_page_${domain}_${modelId}`,
  load(domain, modelId) {
    try { return JSON.parse(localStorage.getItem(this._k(domain, modelId))) || null; }
    catch { return null; }
  },
  save(domain, modelId, state) {
    try { localStorage.setItem(this._k(domain, modelId), JSON.stringify(state)); }
    catch { /* quota exceeded */ }
  },
  clear(domain, modelId) { localStorage.removeItem(this._k(domain, modelId)); },
};

// Mock system stats (used when backend is offline)
window.mockSystemStats = () => {
  const cpu_per_core = Array.from({ length: 16 }, () => Math.random() * 50 + 5);
  return {
  timestamp: Date.now() / 1000,
  cpu_percent: cpu_per_core.reduce((a, b) => a + b, 0) / cpu_per_core.length,
  cpu_per_core,
  memory: { used_bytes: 2.1e9 + Math.random() * 5e8, total_bytes: 8e9, percent: 26 + Math.random() * 6 },
  disk: { used_bytes: 3.2e10, total_bytes: 6.4e10, percent: 50 },
  network: { bytes_sent: (window._mockNetSent = (window._mockNetSent || 1e8) + Math.random() * 5e4), bytes_recv: (window._mockNetRecv = (window._mockNetRecv || 5e8) + Math.random() * 2e5) },
  disk_io: { read_bytes: (window._mockDiskR = (window._mockDiskR || 2e9) + Math.random() * 1e5), write_bytes: (window._mockDiskW = (window._mockDiskW || 1e9) + Math.random() * 8e4) },
}; };
