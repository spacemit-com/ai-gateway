## POST /props 说明

`POST /v1/llm/props` 用于修改当前已加载的本地模型（llama-server）的运行时全局属性。

### 前提条件

llama-server 必须以 `--props` 标志启动，否则返回 501：

```json
{"error": {"code": 501, "message": "This server does not support changing global properties. Start it with `--props`"}}
```

在 spacemit-ai-gateway 中，通过 load 时传 `extra_args` 启用：

```json
POST /v1/llm/models/load
{"model": "qwen3-0.6b-q4_0", "extra_args": ["--props"]}
```

### 当前实现状态

经源码确认（`llama.cpp` commit `2afcdb9`，`tools/server/server-context.cpp:3350`），`POST /props` 是**未完成的占位实现**：

```cpp
this->post_props = [this](const server_http_req &) {
    // ...
    // update any props here   ← 空注释，无实际逻辑

    res->ok({{ "success", true }});
    return res;
};
```

即使带 `--props` 启动，POST 也只返回 `{"success": true}`，不会修改任何属性。GET /props 读回的值不会变化。

### GET /props 返回结构

```
default_generation_settings.params  采样参数（temperature、top_k、top_p 等）
total_slots                          并发 slot 数
model_alias / model_path             模型信息
endpoint_props / endpoint_metrics    功能开关
chat_template                        聊天模板
```
