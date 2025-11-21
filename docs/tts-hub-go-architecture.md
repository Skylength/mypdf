# Go 版 TTS Hub 架构草案

## 目标与定位
- 作为 ttsfm 兼容的中间层：暴露 `/api/generate` 表单接口，返回音频流；分片、合并、落盘继续由 ttsfm 客户端处理。
- 聚合多路 TTS 提供方（例如 upstream OpenAI.fm/自建服务/第三方引擎），可按租户/音色/策略路由。
- 提供治理能力：鉴权、限流、熔断、观测、调度与配额。

## 协议兼容性
- HTTP POST `{base_url}/api/generate`，`Content-Type: application/x-www-form-urlencoded`。
- 表单字段：
  - `input`（必填）：待合成文本。
  - `voice`（必填）：音色标识（直接透传即可）。
  - `response_format`（必填）：`mp3`/`wav`/`opus` 等；可依据支持度决定直接返回或转码。
  - `generation`（必填/uuid）：可用于请求跟踪与幂等。
  - `prompt`（可选）：用于提示词增强。
- 响应：
  - 200：音频字节流，`Content-Type` 对应格式（`audio/mpeg`、`audio/wav` 等）。
  - 非 2xx：`{"error": {"message": "...", "type": "..."}}`；4xx 不建议客户端重试，5xx/429 可重试。

## 核心组件
1) **HTTP Ingress（net/http 或 chi）**：
   - 中间件：请求日志、跟踪 ID 注入（优先用 `generation`）、鉴权（API Key 或 JWT）、限流。
2) **路由器 Router**：
   - 策略：按租户、voice、可用性（健康度）选择 Provider；可加入权重与熔断。
3) **Provider 接口**（伪代码）：
   ```go
   type SynthRequest struct {
       Input          string
       Voice          string
       ResponseFormat string
       Prompt         string
       Generation     string
   }

   type SynthResponse struct {
       Audio       []byte
       ContentType string
   }

   type Provider interface {
       Name() string
       Healthy(ctx context.Context) bool
       Synth(ctx context.Context, req SynthRequest) (SynthResponse, error)
   }
   ```
4) **Provider 实现**：
   - OpenAI 兼容 Provider：直接转发表单到目标 `api/generate`，返回原始音频。
   - 其他厂商 Provider：若返回非期望格式，使用本地转码（ffmpeg）再返回。
5) **限流与熔断**：
   - token bucket/漏桶；按租户和全局；熔断可用 gobreaker。
6) **观测**：
   - 日志（结构化，含 generation/voice/provider/耗时）；
   - metrics（Prometheus：QPS、P99 延迟、错误率、转码耗时）；
   - tracing（OpenTelemetry，可将 generation 作为 trace/span id 关联客户端）。
7) **配置与注册**：
   - `config.yaml/json`：providers 列表（名称、base_url、鉴权 key、支持的 format/voice、权重）；router 策略；限流阈值。
   - 启动时加载并构建 Router；热更新可用 file watcher 或 admin API。
8) **缓存/存储（可选）**：
   - 针对相同 `generation+input` 的短暂缓存（如 Redis）；避免重复合成。
   - 大文件持久化交给客户端（ttsfm 自己落盘）。

## 请求处理流程
1. Ingress 校验鉴权/限流，提取 `generation` 作为 trace id。
2. Router 依据策略选 Provider；若主路由失败且允许重试，可降级到备用 Provider。
3. Provider.Synth：
   - 构造下游请求（通常仍为表单 POST）。
   - 支持超时控制（context with timeout）。
   - 收到 200 音频直接返回；必要时本地转码并设置正确 `Content-Type`。
4. 将音频字节和 `Content-Type` 直接写回客户端；错误按协议返回 JSON。

## 错误与重试
- Hub 内部对下游可做一次短重试（幂等要求：同一 generation 可视为幂等）。
- 语义错误（4xx）直接返回；系统错误（5xx/429）可带 `Retry-After` 供客户端参考。

## 部署建议
- 依赖：Go 1.22+，可选 ffmpeg（用于转码/变速）。
- 打包：单一二进制，配置文件挂载；容器化时暴露 8080/metrics 端口。
- 横向扩展：无状态，前置 LB；共享 Redis 用于限流计数/缓存。

## 最简代码骨架（示意）
```go
func main() {
    cfg := loadConfig()
    providers := buildProviders(cfg)
    router := newRouter(cfg.Router, providers)

    mux := chi.NewRouter()
    mux.Use(middleware.RequestID, logger, auth(cfg), rateLimit(cfg))
    mux.Post("/api/generate", func(w http.ResponseWriter, r *http.Request) {
        req := parseForm(r)
        ctx, cancel := context.WithTimeout(r.Context(), time.Second*cfg.Timeout)
        defer cancel()

        provider := router.Pick(req)
        resp, err := provider.Synth(ctx, req)
        if err != nil { writeError(w, err); return }

        w.Header().Set("Content-Type", resp.ContentType)
        w.WriteHeader(http.StatusOK)
        w.Write(resp.Audio)
    })

    http.ListenAndServe(cfg.Addr, mux)
}
```

## 下一步
- 细化 Provider 适配器（OpenAI 兼容、厂商 SDK、gRPC 等）。
- 落地观测（Prometheus + OTLP）与熔断策略。
- 验证与 ttsfm 端到端兼容：指向 hub 替换 base_url，跑长文本案例确保合并可用。
