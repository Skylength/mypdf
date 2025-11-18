from ttsfm import TTSClient, AudioFormat, Voice,AsyncTTSClient
import asyncio

client = TTSClient()

# 基础用法
response = client.generate_speech(
    text="来自 TTSFM 的问候！",
    voice=Voice.ALLOY,
    response_format=AudioFormat.MP3,
)
response.save_to_file("hello")  # -> hello.mp3

# 使用语速调节（需要 ffmpeg）
response = client.generate_speech(
    text="这段语音会更快！",
    voice=Voice.NOVA,
    response_format=AudioFormat.MP3,
    speed=1.5,  # 1.5 倍速（范围：0.25 - 4.0）
)
response.save_to_file("fast")  # -> fast.mp3




async def main():
    client = AsyncTTSClient()
    response = await client.generate_speech(
        text="Hello, async world!",
        voice=Voice.ALLOY,
        response_format=AudioFormat.MP3
    )
    response.save_to_file("async_output.mp3")

asyncio.run(main())



## curl 请求
base_url = "http://siyandiu.online:8003"

