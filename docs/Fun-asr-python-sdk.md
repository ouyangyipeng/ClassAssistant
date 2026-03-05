本文介绍Fun-ASR实时语音识别Python SDK的参数和接口细节。

**用户指南：**关于模型介绍和选型建议请参见[实时语音识别-Fun-ASR/Gummy/Paraformer](https://help.aliyun.com/zh/model-studio/real-time-speech-recognition)。

## **前提条件**

-   已开通服务并[获取API Key](https://help.aliyun.com/zh/model-studio/get-api-key)。请[配置API Key到环境变量](https://help.aliyun.com/zh/model-studio/configure-api-key-through-environment-variables)，而非硬编码在代码中，防范因代码泄露导致的安全风险。
    
-   [安装最新版DashScope SDK](https://help.aliyun.com/zh/model-studio/install-sdk)。
    

## **模型列表**

### 中国内地

在[中国内地部署模式](https://help.aliyun.com/zh/model-studio/regions/#080da663a75xh)下，接入点与数据存储均位于**北京地域**，模型推理计算资源仅限于中国内地。

| **模型名称** | **版本** | **单价** | **免费额度**[**（注）**](https://help.aliyun.com/zh/model-studio/new-free-quota#591f3dfedfyzj) |
| --- | --- | --- | --- |
| fun-asr-realtime > 当前等同fun-asr-realtime-2025-11-07 | 稳定版 | 0.00033元/秒 | 36,000秒（10小时） 有效期：阿里云百炼开通后90天 |
| fun-asr-realtime-2025-11-07 | 快照版 |
| fun-asr-realtime-2025-09-15 |
| fun-asr-flash-8k-realtime > 当前等同fun-asr-flash-8k-realtime-2026-01-28 | 稳定版 | 0.00022元/秒 |
| fun-asr-flash-8k-realtime-2026-01-28 | 快照版 |

-   **支持的语种**：
    
    -   fun-asr-realtime、fun-asr-realtime-2025-11-07：中文（普通话、粤语、吴语、闽南语、客家话、赣语、湘语、晋语；并支持中原、西南、冀鲁、江淮、兰银、胶辽、东北、北京、港台等，包括河南、陕西、湖北、四川、重庆、云南、贵州、广东、广西、河北、天津、山东、安徽、南京、江苏、杭州、甘肃、宁夏等地区官话口音）、英文、日语
        
    -   fun-asr-realtime-2025-09-15：中文（普通话、粤语）、英文、日语、韩语、越南语、印尼语、泰语
        
-   **支持的采样率**：
    
    -   fun-asr-flash-8k-realtime、fun-asr-flash-8k-realtime-2026-01-28：8kHz
        
    -   其他模型：16kHz
        
-   **支持的音频格式**：pcm、wav、mp3、opus、speex、aac、amr
    

### **国际**

在[国际部署模式](https://help.aliyun.com/zh/model-studio/regions/#080da663a75xh)下，接入点与数据存储均位于**新加坡地域**，模型推理计算资源在全球范围内动态调度（不含中国内地）。

| **模型名称** | **版本** | **单价** | **免费额度**[**（注）**](https://help.aliyun.com/zh/model-studio/new-free-quota#591f3dfedfyzj) |
| --- | --- | --- | --- |
| fun-asr-realtime > 当前等同fun-asr-realtime-2025-11-07 | 稳定版 | 0.00066元/秒 | 无免费额度 |
| fun-asr-realtime-2025-11-07 | 快照版 |

-   **支持的语种**：中文（普通话、粤语、吴语、闽南语、客家话、赣语、湘语、晋语；并支持中原、西南、冀鲁、江淮、兰银、胶辽、东北、北京、港台等，包括河南、陕西、湖北、四川、重庆、云南、贵州、广东、广西、河北、天津、山东、安徽、南京、江苏、杭州、甘肃、宁夏等地区官话口音）、英文、日语
    
-   **支持的采样率**：16kHz
    
-   **支持的音频格式**：pcm、wav、mp3、opus、speex、aac、amr
    

## **快速开始**

[Recognition类](#44f87473bfp2m)提供了非流式调用和双向流式调用等接口。请根据实际需求选择合适的调用方式：

-   非流式调用：针对本地文件进行识别，并一次性返回完整的处理结果。适合处理录制好的音频。
    
-   双向流式调用：可直接对音频流进行识别，并实时输出结果。音频流可以来自外部设备（如麦克风）或从本地文件读取。适合需要即时反馈的场景。
    

### **非流式调用**

提交单个语音实时转写任务，通过传入本地文件的方式同步阻塞地拿到转写结果。

实例化[Recognition类](#44f87473bfp2m)绑定[请求参数](https://help.aliyun.com/zh/model-studio/paraformer-real-time-speech-recognition-python-sdk#555007db2033f)，调用`call`进行识别/翻译并最终获取[识别结果（RecognitionResult）](https://help.aliyun.com/zh/model-studio/paraformer-real-time-speech-recognition-python-sdk#bc3e1a43d6hhy)。

点击查看完整示例

示例中用到的音频为：[asr\_example.wav](https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20250210/iwaouc/asr_example.wav)。

```
from http import HTTPStatus
import dashscope
from dashscope.audio.asr import Recognition
import os

# 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
# 若没有配置环境变量，请用百炼API Key将下行替换为：dashscope.api_key = "sk-xxx"
dashscope.api_key = os.environ.get('DASHSCOPE_API_KEY')

# 以下为北京地域url，若使用新加坡地域的模型，需将url替换为：wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference
dashscope.base_websocket_api_url='wss://dashscope.aliyuncs.com/api-ws/v1/inference'

recognition = Recognition(model='fun-asr-realtime',
                          format='wav',
                          sample_rate=16000,
                          callback=None)
result = recognition.call('asr_example.wav')
if result.status_code == HTTPStatus.OK:
    print('识别结果：')
    print(result.get_sentence())
else:
    print('Error: ', result.message)
    
print(
    '[Metric] requestId: {}, first package delay ms: {}, last package delay ms: {}'
    .format(
        recognition.get_last_request_id(),
        recognition.get_first_package_delay(),
        recognition.get_last_package_delay(),
    ))
```

### **双向流式调用**

提交单个语音实时转写任务，通过实现回调接口的方式流式输出实时识别结果。

1.  启动流式语音识别
    
    实例化[Recognition类](#44f87473bfp2m)绑定[请求参数](https://help.aliyun.com/zh/model-studio/paraformer-real-time-speech-recognition-python-sdk#555007db2033f)和[回调接口（RecognitionCallback）](#cec6e96138swr)，调用`start`方法启动流式语音识别。
    
2.  流式传输
    
    循环调用[Recognition类](#44f87473bfp2m)的`send_audio_frame`方法，将从本地文件或设备（如麦克风）读取的二进制音频流分段发送至服务端。
    
    在发送音频数据的过程中，服务端会通过[回调接口（RecognitionCallback）](#cec6e96138swr)的`on_event`方法，将识别结果实时返回给客户端。
    
    建议每次发送的音频时长约为100毫秒，数据大小保持在1KB至16KB之间。
    
3.  结束处理
    
    调用[Recognition类](#44f87473bfp2m)的`stop`方法结束语音识别。
    
    该方法会阻塞当前线程，直到[回调接口（RecognitionCallback）](#cec6e96138swr)的`on_complete`或者`on_error`回调触发后才会释放线程阻塞。
    

点击查看完整示例

## 识别传入麦克风的语音

```
import os
import signal  # for keyboard events handling (press "Ctrl+C" to terminate recording)
import sys

import dashscope
import pyaudio
from dashscope.audio.asr import *

mic = None
stream = None

# Set recording parameters
sample_rate = 16000  # sampling rate (Hz)
channels = 1  # mono channel
dtype = 'int16'  # data type
format_pcm = 'pcm'  # the format of the audio data
block_size = 3200  # number of frames per buffer


# Real-time speech recognition callback
class Callback(RecognitionCallback):
    def on_open(self) -> None:
        global mic
        global stream
        print('RecognitionCallback open.')
        mic = pyaudio.PyAudio()
        stream = mic.open(format=pyaudio.paInt16,
                          channels=1,
                          rate=16000,
                          input=True)

    def on_close(self) -> None:
        global mic
        global stream
        print('RecognitionCallback close.')
        stream.stop_stream()
        stream.close()
        mic.terminate()
        stream = None
        mic = None

    def on_complete(self) -> None:
        print('RecognitionCallback completed.')  # recognition completed

    def on_error(self, message) -> None:
        print('RecognitionCallback task_id: ', message.request_id)
        print('RecognitionCallback error: ', message.message)
        # Stop and close the audio stream if it is running
        if 'stream' in globals() and stream.active:
            stream.stop()
            stream.close()
        # Forcefully exit the program
        sys.exit(1)

    def on_event(self, result: RecognitionResult) -> None:
        sentence = result.get_sentence()
        if 'text' in sentence:
            print('RecognitionCallback text: ', sentence['text'])
            if RecognitionResult.is_sentence_end(sentence):
                print(
                    'RecognitionCallback sentence end, request_id:%s, usage:%s'
                    % (result.get_request_id(), result.get_usage(sentence)))


def signal_handler(sig, frame):
    print('Ctrl+C pressed, stop recognition ...')
    # Stop recognition
    recognition.stop()
    print('Recognition stopped.')
    print(
        '[Metric] requestId: {}, first package delay ms: {}, last package delay ms: {}'
        .format(
            recognition.get_last_request_id(),
            recognition.get_first_package_delay(),
            recognition.get_last_package_delay(),
        ))
    # Forcefully exit the program
    sys.exit(0)


# main function
if __name__ == '__main__':
    # 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    # 若没有配置环境变量，请用百炼API Key将下行替换为：dashscope.api_key = "sk-xxx"
    dashscope.api_key = os.environ.get('DASHSCOPE_API_KEY')

    # 以下为北京地域url，若使用新加坡地域的模型，需将url替换为：wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference
    dashscope.base_websocket_api_url='wss://dashscope.aliyuncs.com/api-ws/v1/inference'

    # Create the recognition callback
    callback = Callback()

    # Call recognition service by async mode, you can customize the recognition parameters, like model, format,
    # sample_rate
    recognition = Recognition(
        model='fun-asr-realtime',
        format=format_pcm,
        # 'pcm'、'wav'、'opus'、'speex'、'aac'、'amr', you can check the supported formats in the document
        sample_rate=sample_rate,
        # support 8000, 16000
        semantic_punctuation_enabled=False,
        callback=callback)

    # Start recognition
    recognition.start()

    signal.signal(signal.SIGINT, signal_handler)
    print("Press 'Ctrl+C' to stop recording and recognition...")
    # Create a keyboard listener until "Ctrl+C" is pressed

    while True:
        if stream:
            data = stream.read(3200, exception_on_overflow=False)
            recognition.send_audio_frame(data)
        else:
            break

    recognition.stop()
```

## 识别本地语音文件

示例中用到的音频为：[asr\_example.wav](https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20250210/acoict/asr_example.wav)。

```
import os
import time
import dashscope
from dashscope.audio.asr import *

# 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
# 若没有配置环境变量，请用百炼API Key将下行替换为：dashscope.api_key = "sk-xxx"
dashscope.api_key = os.environ.get('DASHSCOPE_API_KEY')

# 以下为北京地域url，若使用新加坡地域的模型，需将url替换为：wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference
dashscope.base_websocket_api_url = 'wss://dashscope.aliyuncs.com/api-ws/v1/inference'

from datetime import datetime


def get_timestamp():
    now = datetime.now()
    formatted_timestamp = now.strftime("[%Y-%m-%d %H:%M:%S.%f]")
    return formatted_timestamp


class Callback(RecognitionCallback):
    def on_complete(self) -> None:
        print(get_timestamp() + ' Recognition completed')  # recognition complete

    def on_error(self, result: RecognitionResult) -> None:
        print('Recognition task_id: ', result.request_id)
        print('Recognition error: ', result.message)
        exit(0)

    def on_event(self, result: RecognitionResult) -> None:
        sentence = result.get_sentence()
        if 'text' in sentence:
            print(get_timestamp() + ' RecognitionCallback text: ', sentence['text'])
        if RecognitionResult.is_sentence_end(sentence):
            print(get_timestamp() +
                  'RecognitionCallback sentence end, request_id:%s, usage:%s'
                  % (result.get_request_id(), result.get_usage(sentence)))


callback = Callback()

recognition = Recognition(model='fun-asr-realtime',
                          format='wav',
                          sample_rate=16000,
                          callback=callback)

try:
    audio_data: bytes = None
    f = open("asr_example.wav", 'rb')
    if os.path.getsize("asr_example.wav"):
        # 一次性将文件数据全部读入buffer
        file_buffer = f.read()
        f.close()
        print("Start Recognition")
        recognition.start()

        # 从buffer中间隔3200字节发送一次
        buffer_size = len(file_buffer)
        offset = 0
        chunk_size = 3200

        while offset < buffer_size:
            # 计算本次要发送的数据块大小
            remaining_bytes = buffer_size - offset
            current_chunk_size = min(chunk_size, remaining_bytes)

            # 从buffer中提取当前数据块
            audio_data = file_buffer[offset:offset + current_chunk_size]

            # 发送音频数据帧
            recognition.send_audio_frame(audio_data)
            # 更新偏移量
            offset += current_chunk_size

            # 添加延迟模拟实时传输
            time.sleep(0.1)

        recognition.stop()
    else:
        raise Exception(
            'The supplied file was empty (zero bytes long)')
except Exception as e:
    raise e

print(
    '[Metric] requestId: {}, first package delay ms: {}, last package delay ms: {}'
    .format(
        recognition.get_last_request_id(),
        recognition.get_first_package_delay(),
        recognition.get_last_package_delay(),
    ))
```

## **请求参数**

请求参数通过[Recognition类](#44f87473bfp2m)的构造方法（\_init\_）进行设置。

| **参数** | **类型** | **默认值** | **是否必须** | **说明** |
| --- | --- | --- | --- | --- |
| model | str | \\- | 是   | 用于实时语音识别的模型 |
| sample\\_rate | int | \\- | 是   | 设置待识别音频采样率（单位Hz）。 fun-asr-realtime支持16000Hz采样。 |
| format | str | \\- | 是   | 设置待识别音频格式。 支持的音频格式：pcm、wav、mp3、opus、speex、aac、amr。 **重要** opus/speex：必须使用Ogg封装； wav：必须为PCM编码； amr：仅支持AMR-NB类型。 |
| vocabulary\\_id | str | \\- | 否   | 热词ID。使用方法参见[定制热词](https://help.aliyun.com/zh/model-studio/custom-hot-words)。 默认不设置。 |
| semantic\\_punctuation\\_enabled | bool | False | 否   | 设置是否开启语义断句，默认关闭。 - true：开启语义断句，关闭VAD（Voice Activity Detection，语音活动检测）断句。 - false（默认）：开启VAD（Voice Activity Detection，语音活动检测）断句，关闭语义断句。 语义断句准确性更高，适合会议转写场景；VAD（Voice Activity Detection，语音活动检测）断句延迟较低，适合交互场景。 通过调整`semantic_punctuation_enabled`参数，可以灵活切换语音识别的断句方式以适应不同场景需求。 |
| max\\_sentence\\_silence | int | 1300 | 否   | 设置VAD（Voice Activity Detection，语音活动检测）断句的静音时长阈值（单位为ms）。 当一段语音后的静音时长超过该阈值时，系统会判定该句子已结束。 参数范围为200ms至6000ms，默认值为1300ms。 该参数仅在`semantic_punctuation_enabled`参数为false（VAD断句）时生效。 |
| multi\\_threshold\\_mode\\_enabled | bool | False | 否   | 该开关打开时（true）可以防止VAD断句切割过长。默认关闭。 该参数仅在`semantic_punctuation_enabled`参数为false（VAD断句）时生效。 |
| punctuation\\_prediction\\_enabled | bool | True | 否   | 设置是否在识别结果中自动添加标点： - true（默认）：是，不支持修改。 |
| heartbeat | bool | False | 否   | 当需要与服务端保持长连接时，可通过该开关进行控制： - true：在持续发送静音音频的情况下，可保持与服务端的连接不中断。 - false（默认）：即使持续发送静音音频，连接也将在60秒后因超时而断开。 静音音频指的是在音频文件或数据流中没有声音信号的内容。静音音频可以通过多种方法生成，例如使用音频编辑软件如Audacity或Adobe Audition，或者通过命令行工具如FFmpeg。 使用该字段时，SDK版本不能低于1.23.1。 |
| language\\_hints | list\\[str\\] | \\["zh", "en"\\] | 否   | 设置待识别语言代码。如果无法提前确定语种，可不设置，模型会自动识别语种。 不同模型支持的语言代码如下： - fun-asr-realtime、fun-asr-realtime-2025-11-07： - zh: 中文 - en: 英文 - ja: 日语 - fun-asr-realtime-2025-09-15： - zh: 中文 - en: 英文 |
| speech\\_noise\\_threshold | float | \\- | 否   | 控制语音与噪音的判定阈值，用于调整语音活动检测（VAD）的灵敏度。 取值范围：\\[-1.0, 1.0\\]。 取值说明： - 取值越接近 -1：降低噪音判定阈值，噪音被识别为语音的概率增大，可能导致更多噪音被转写 - 取值越接近 +1：提高噪音判定阈值，语音被误判为噪音的概率增大，可能导致部分语音被过滤 **重要** 此参数为高级配置参数，调整可能显著影响识别效果，建议： - 调整前充分测试验证效果 - 根据实际音频环境小幅度调整（建议步长 0.1） |
| callback | RecognitionCallback | \\- | 否   | [回调接口（RecognitionCallback）](#cec6e96138swr)。 |

## **关键接口**

### `Recognition`类

`Recognition`通过“`from dashscope.audio.asr import *`”方式引入。

| **成员方法** | **方法签名** | **说明** |
| --- | --- | --- |
| call | ``` def call(self, file: str, phrase_id: str = None, **kwargs) -> RecognitionResult ``` | 基于本地文件的非流式调用，该方法会阻塞当前线程直到全部音频读完，该方法要求所识别文件具有可读权限。 识别结果以`RecognitionResult`类型数据返回。 |
| start | ``` def start(self, phrase_id: str = None, **kwargs) ``` | 开始语音识别。 基于回调形式的流式实时识别，该方法不会阻塞当前线程。需要配合`send_audio_frame`和`stop`使用。 |
| send\\_audio\\_frame | ``` def send_audio_frame(self, buffer: bytes) ``` | 推送音频。每次推送的音频流不宜过大或过小，建议每包音频时长为100ms左右，大小在1KB~16KB之间。 识别结果通过[回调接口（RecognitionCallback）](#cec6e96138swr)的on\\_event方法获取。 |
| stop | ``` def stop(self) ``` | 停止语音识别，阻塞到服务将收到的音频都识别后结束任务。 |
| get\\_last\\_request\\_id | ``` def get_last_request_id(self) ``` | 获取request\\_id，在构造函数调用（创建对象）后可以使用。 |
| get\\_first\\_package\\_delay | ``` def get_first_package_delay(self) ``` | 获取首包延迟，从发送第一包音频到收到首包识别结果延迟，在任务完成后使用。 |
| get\\_last\\_package\\_delay | ``` def get_last_package_delay(self) ``` | 获得尾包延迟，发送`stop`指令到最后一包识别结果下发耗时，在任务完成后使用。 |
| get\\_response | ``` def get_response(self) ``` | 获取最后一次报文，可以用于获取task-failed报错。 |

### **回调接口（**`RecognitionCallback`）

[双向流式调用](#7b019225eeqet)时，服务端会通过回调的方式，将关键流程信息和数据返回给客户端。您需要实现回调方法，处理服务端返回的信息或者数据。

点击查看示例

```
class Callback(RecognitionCallback):
    def on_open(self) -> None:
        print('连接成功')

    def on_event(self, result: RecognitionResult) -> None:
        # 实现接收识别结果的逻辑

    def on_complete(self) -> None:
        print('任务完成')

    def on_error(self, result: RecognitionResult) -> None:
        print('出现异常：', result)

    def on_close(self) -> None:
        print('连接关闭')


callback = Callback()
```

| **方法** | **参数** | **返回值** | **描述** |
| --- | --- | --- | --- |
| ``` def on_open(self) -> None ``` | 无   | 无   | 当和服务端建立连接完成后，该方法立刻被回调。 |
| ``` def on_event(self, result: RecognitionResult) -> None ``` | `result`：[识别结果（RecognitionResult）](https://help.aliyun.com/zh/model-studio/paraformer-real-time-speech-recognition-python-sdk#bc3e1a43d6hhy) | 无   | 当服务有回复时会被回调。 |
| ``` def on_complete(self) -> None ``` | 无   | 无   | 当所有识别结果全部返回后进行回调。 |
| ``` def on_error(self, result: RecognitionResult) -> None ``` | `result`：[识别结果（RecognitionResult）](https://help.aliyun.com/zh/model-studio/paraformer-real-time-speech-recognition-python-sdk#bc3e1a43d6hhy) | 无   | 发生异常时该方法被回调。 |
| ``` def on_close(self) -> None ``` | 无   | 无   | 当服务已经关闭连接后进行回调。 |

## **响应结果**

### **识别结果（**`**RecognitionResult**`**）**

`RecognitionResult`代表[双向流式调用](https://help.aliyun.com/zh/model-studio/paraformer-real-time-speech-recognition-python-sdk#9d1e5f6852jr8)中一次实时识别或[非流式调用](https://help.aliyun.com/zh/model-studio/paraformer-real-time-speech-recognition-python-sdk#8341058094tc3)的识别结果。

| **成员方法** | **方法签名** | **说明** |
| --- | --- | --- |
| get\\_sentence | ``` def get_sentence(self) -> Union[Dict[str, Any], List[Any]] ``` | 获取当前识别的句子及时间戳信息。回调中返回的是单句信息，所以此方法返回类型为Dict\\[str, Any\\]。 详情请参见[单句信息（Sentence）](https://help.aliyun.com/zh/model-studio/paraformer-real-time-speech-recognition-python-sdk#f28f50b035qtn)。 |
| get\\_request\\_id | ``` def get_request_id(self) -> str ``` | 获取请求的request\\_id。 |
| is\\_sentence\\_end | ``` @staticmethod def is_sentence_end(sentence: Dict[str, Any]) -> bool ``` | 判断给定句子是否已经结束。 |

### 单句信息（`Sentence`）

Sentence类成员如下：

| **参数** | **类型** | **说明** |
| --- | --- | --- |
| begin\\_time | int | 句子开始时间，单位为ms。 |
| end\\_time | int | 句子结束时间，单位为ms。 |
| text | str | 识别文本。 |
| words | [字时间戳信息（Word）](#b55a7391caxxe)的list集合 | 字时间戳信息。 |

### **字时间戳信息（**`**Word**`**）**

Word类成员如下：

| **参数** | **类型** | **说明** |
| --- | --- | --- |
| begin\\_time | int | 字开始时间，单位为ms。 |
| end\\_time | int | 字结束时间，单位为ms。 |
| text | str | 字。  |
| punctuation | str | 标点。 |

## **错误码**

如遇报错问题，请参见[错误信息](https://help.aliyun.com/zh/model-studio/error-code)进行排查。

若问题仍未解决，请加入[开发者群](https://github.com/aliyun/alibabacloud-bailian-speech-demo)反馈遇到的问题，并提供Request ID，以便进一步排查问题。

## **常见问题**

### **功能特性**

#### **Q：在长时间静默的情况下，如何保持与服务端长连接？**

将请求参数`heartbeat`设置为true，并持续向服务端发送静音音频。

静音音频指的是在音频文件或数据流中没有声音信号的内容。静音音频可以通过多种方法生成，例如使用音频编辑软件如Audacity或Adobe Audition，或者通过命令行工具如FFmpeg。

#### **Q：如何将音频格式转换为满足要求的格式？**

可使用[FFmpeg工具](https://ffmpeg.en.lo4d.com/download)，更多用法请参见FFmpeg官网。

```
# 基础转换命令（万能模板）
# -i，作用：输入文件路径，常用值示例：audio.wav
# -c:a，作用：音频编码器，常用值示例：aac, libmp3lame, pcm_s16le
# -b:a，作用：比特率（音质控制），常用值示例：192k, 320k
# -ar，作用：采样率，常用值示例：44100 (CD), 48000, 16000
# -ac，作用：声道数，常用值示例：1(单声道), 2(立体声)
# -y，作用：覆盖已存在文件(无需值)
ffmpeg -i input_audio.ext -c:a 编码器名 -b:a 比特率 -ar 采样率 -ac 声道数 output.ext

# 例如：WAV → MP3（保持原始质量）
ffmpeg -i input.wav -c:a libmp3lame -q:a 0 output.mp3
# 例如：MP3 → WAV（16bit PCM标准格式）
ffmpeg -i input.mp3 -c:a pcm_s16le -ar 44100 -ac 2 output.wav
# 例如：M4A → AAC（提取/转换苹果音频）
ffmpeg -i input.m4a -c:a copy output.aac  # 直接提取不重编码
ffmpeg -i input.m4a -c:a aac -b:a 256k output.aac  # 重编码提高质量
# 例如：FLAC无损 → Opus（高压缩）
ffmpeg -i input.flac -c:a libopus -b:a 128k -vbr on output.opus
```

#### **Q：如何识别本地文件（录音文件）？**

识别本地文件有两种方式：

-   直接传入本地文件路径：此种方式在最终识别结束后获取完整识别结果，不适合即时反馈的场景。
    
    参见[非流式调用](#881157aa56lll)，在[Recognition类](#44f87473bfp2m)的`call`方法中传入文件路径对录音文件直接进行识别。
    
-   将本地文件转成二进制流进行识别：此种方式一边识别文件一边流式获取识别结果，适合即时反馈的场景。
    
    参见[双向流式调用](#7b019225eeqet)，通过[Recognition类](#44f87473bfp2m)的`send_audio_frame`方法向服务端发送二进制流对其进行识别。
    

### **故障排查**

#### **Q：无法识别语音（无识别结果）是什么原因？**

1.  请检查请求参数中的音频格式（`format`）和采样率（`sampleRate`/`sample_rate`）设置是否正确且符合参数约束。以下为常见错误示例：
    
    -   音频文件扩展名为 .wav，但实际为 MP3 格式，而请求参数 `format` 设置为 mp3（参数设置错误）。
        
    -   音频采样率为 3600Hz，但请求参数 `sampleRate`/`sample_rate` 设置为 48000（参数设置错误）。
        
    
    可以使用[ffprobe](https://ffmpeg.org/ffprobe.html)工具获取音频的容器、编码、采样率、声道等信息：
    
    ```
    ffprobe -v error -show_entries format=format_name -show_entries stream=codec_name,sample_rate,channels -of default=noprint_wrappers=1 input.xxx
    ```
    
2.  若以上检查均无问题，可通过定制热词提升对特定词语的识别效果。