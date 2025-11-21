#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
from pathlib import Path
from typing import Optional
from datetime import datetime

import pymupdf
from ttsfm import TTSClient, Voice, AudioFormat

# 默认使用官方托管的 https://ttsapi.site/ 作为后端
# （如果你以后自己用 Docker 起服务，可以看文档把客户端指向 localhost）
client = TTSClient()

def extract_text_from_pdf(
    pdf_path: str,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
) -> str:
    """按页提取 PDF 文本，简单拼起来。"""
    doc = pymupdf.open(pdf_path)
    texts = []

    total_pages = doc.page_count
    sp = start_page - 1 if start_page else 0
    ep = end_page if end_page else total_pages

    if sp < 0 or sp >= total_pages or ep < 1 or ep > total_pages or sp >= ep:
        doc.close()
        raise ValueError(f"页码范围无效（共有 {total_pages} 页），请检查 start_page/end_page 参数")

    for i in range(sp, ep):
        page = doc[i]
        texts.append(page.get_text("text"))

    doc.close()
    return "\n\n".join(texts)


def pdf_to_mp3_with_ttsfm(
    pdf_path: str,
    mp3_path: str,
    voice: str = "alloy",
    speed: float = 1.0,
    max_length: int = 1000,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
):
    """
    用 ttsfm 把整本 PDF 变成一个 MP3：
    - ttsfm 会自动按 max_length 拆分长文本、调用多次 TTS，并合并音频。
    """
    start_time = datetime.now()
    print(f"[{start_time.strftime('%H:%M:%S')}] 读取 PDF: {pdf_path}")
    full_text = extract_text_from_pdf(pdf_path, start_page=start_page, end_page=end_page)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] PDF 读取完成，耗时: {(datetime.now() - start_time).total_seconds():.2f}秒")

    if not full_text.strip():
        raise ValueError("PDF 中没有提取到文本（可能是纯图片 PDF，需要 OCR）")

    text_length = len(full_text)
    if text_length > 50000:
        raise ValueError(
            f"提取的文本超过 TTSFM 的 50000 字符限制（当前 {text_length} 个字符），"
            "请使用 -start / -end 或 -start-page / -end-page 限定页码，或拆分 PDF 后重试。"
        )

    tts_start = datetime.now()
    print(f"[{tts_start.strftime('%H:%M:%S')}] 调用 TTSFM 生成语音（自动长文本拆分 + 合并）...")

    # 这里直接把整本书丢给 ttsfm，它会：
    # 1）按句子 + max_length 自动拆分  2）多次请求 openai.fm  3）合并音频
    # 这些参数来自官方文档：max_length / auto_combine / preserve_words 等。
    resp = client.generate_speech_long_text(
        text=full_text,
        voice=Voice[voice.upper()],
        response_format=AudioFormat.MP3,
        speed=speed,
        max_length=max_length,
        preserve_words=True,
        auto_combine=True,
    )
    print(f"[{datetime.now().strftime('%H:%M:%S')}] TTS 生成完成，耗时: {(datetime.now() - tts_start).total_seconds():.2f}秒")

    out_path = Path(mp3_path)
    resp.save_to_file(str(out_path))        # 官方示例就是这么用的
    total_time = (datetime.now() - start_time).total_seconds()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 完成！输出文件：{out_path}，总耗时: {total_time:.2f}秒")


def main():
    parser = argparse.ArgumentParser(description="用 TTSFM 把 PDF 转成 MP3 有声书")
    parser.add_argument("pdf", help="输入 PDF 文件路径")
    parser.add_argument("-out", "-o", help="输出 MP3 文件路径（默认同名）")
    parser.add_argument("-voice", default="alloy", help="声音：alloy/echo/fable/onyx/nova/shimmer")
    parser.add_argument("-speed", type=float, default=1.0, help="播放速度 0.25 ~ 4.0，1.0=正常")  # full 版本才支持变速
    parser.add_argument("-max-length", type=int, default=1000, help="内部拆分时每段最大字符数")
    parser.add_argument(
        "-start-page",
        "--start-page",
        "-start",
        "--start",
        type=int,
        dest="start_page",
        help="起始页（从 1 开始）",
    )
    parser.add_argument(
        "-end-page",
        "--end-page",
        "-end",
        "--end",
        type=int,
        dest="end_page",
        help="结束页（包含）",
    )

    args = parser.parse_args()

    pdf_path = args.pdf
    out_path = args.out or str(Path(pdf_path).with_suffix(".mp3"))

    pdf_to_mp3_with_ttsfm(
        pdf_path=pdf_path,
        mp3_path=out_path,
        voice=args.voice,
        speed=args.speed,
        max_length=args.max_length,
        start_page=args.start_page,
        end_page=args.end_page,
    )


if __name__ == "__main__":
    main()
