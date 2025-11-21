# ttsfm 服务封装指南

## 能力速览
- ttsfm 使用 `TTSClient`（同步）和 `AsyncTTSClient`（异步）向 OpenAI 兼容的 TTS 服务发请求，默认 `base_url` 为 `https://www.openai.fm`，亦可指向官方托管的 `https://ttsapi.site` 或自建服务。
- 支持多种音色 `Voice`（如 `ALLOY`、`ECHO`、`FABLE` 等）与多种格式 `AudioFormat`（MP3/WAV/OPUS/AAC/FLAC/PCM）；`TTSResponse.save_to_file()` 会按格式自动追加扩展名。
- `generate_speech` 处理短文本（默认最长 1000 字符，超长会抛 `ValidationException`）。
- `generate_speech_long_text`/`generate_speech_batch` 会在内部用 `max_length` 和 `preserve_words=True` 自动分片；`auto_combine=True` 会先按 WAV 汇总，再转换为目标格式。
- 客户端内置重试、指数退避与基础 headers 伪装，同时支持 `speed`（需要 ffmpeg）、提示词 `instructions`、`use_default_prompt` 等参数。

## 封装思路
目标：把“文本/文档 -> 语音文件”的流程收束成易用的服务层，隔离参数、重试和异常，外部只调用两个入口：文本合成与文件输出。

### 1. 定义配置对象
```python
from dataclasses import dataclass
from ttsfm import Voice, AudioFormat

@dataclass
class TTSConfig:
    base_url: str = "https://ttsapi.site"  # 或自建
    api_key: str | None = None
    voice: Voice = Voice.ALLOY
    response_format: AudioFormat = AudioFormat.MP3
    max_length: int = 1000
    preserve_words: bool = True
    auto_combine: bool = True
    speed: float = 1.0
    use_default_prompt: bool = False  # 需要更平滑语气时可打开
    timeout: float = 30.0
    max_retries: int = 3
```

### 2. 封装 TTS 服务类
```python
from pathlib import Path
from ttsfm import TTSClient

class TTSService:
    def __init__(self, cfg: TTSConfig):
        self.cfg = cfg
        self.client = TTSClient(
            base_url=cfg.base_url,
            api_key=cfg.api_key,
            timeout=cfg.timeout,
            max_retries=cfg.max_retries,
            preferred_format=cfg.response_format,
            use_default_prompt=cfg.use_default_prompt,
        )

    def synthesize(self, text: str, *, instructions: str | None = None):
        return self.client.generate_speech_long_text(
            text=text,
            voice=self.cfg.voice,
            response_format=self.cfg.response_format,
            instructions=instructions,
            max_length=self.cfg.max_length,
            preserve_words=self.cfg.preserve_words,
            auto_combine=self.cfg.auto_combine,
            speed=self.cfg.speed,
        )

    def text_to_file(self, text: str, out_path: str | Path, *, instructions: str | None = None) -> Path:
        resp = self.synthesize(text, instructions=instructions)
        out_path = Path(out_path)
        # save_to_file 会根据 format 自动加扩展名，提前补上更直观
        target = out_path.with_suffix(f".{self.cfg.response_format.value}")
        resp.save_to_file(str(target))
        return target

    def close(self):
        self.client.close()
```

### 3. 文档到语音的组合封装
在 `src/pdf2tts.py` 已有 `extract_text_from_pdf`，可以组合进服务类或单独的 use case：
```python
import pymupdf

def pdf_to_audio(pdf_path: str, out_path: str, service: TTSService, *, start_page: int | None = None, end_page: int | None = None):
    text = extract_text_from_pdf(pdf_path, start_page=start_page, end_page=end_page)
    if not text.strip():
        raise ValueError("PDF 未发现文本，可能需要 OCR")
    # 自行加长度保护，如本仓库示例的 50_000 字符上限
    return service.text_to_file(text, out_path)
```

### 4. 使用示例
```python
cfg = TTSConfig(
    base_url="https://ttsapi.site",
    voice=Voice.NOVA,
    response_format=AudioFormat.MP3,
    max_length=800,
    use_default_prompt=True,
)
svc = TTSService(cfg)
try:
    audio_path = pdf_to_audio("test.pdf", "test_output", svc)
    print("音频生成完成：", audio_path)
finally:
    svc.close()
```

### 5. 最佳实践与注意事项
- **分片控制**：对极长文本提前做长度校验或分页，避免超过服务端限制（参考本仓库示例的 50k 字符上限）。必要时调小 `max_length`。
- **格式与合并**：`auto_combine=True` 时内部会先按 WAV 合并再转回目标格式，若需保持无损可直接请求 `AudioFormat.WAV`。
- **速度与音质**：`speed` 依赖 ffmpeg；极速播放会牺牲清晰度，建议 0.8~1.25 区间。
- **稳定性**：`timeout`、`max_retries` 可依网络状况调整；遇到 400/401 等请求错误库会直接抛异常，不会重试。
- **提示词调优**：`use_default_prompt=True` 会自动注入友好播报提示；也可通过 `instructions` 传入场景化提示。

以上封装将参数、重试和文件落盘全部收口在 `TTSService`，上层只需提供文本或文档路径即可完成合成，便于后续扩展（如换后端、换格式或引入队列）。
