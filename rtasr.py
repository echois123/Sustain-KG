import hashlib
import hmac
import base64
import time
from urllib.parse import urlencode, quote
import websocket
import json
try:
    import thread
except ImportError:
    import _thread as thread

import pyaudio
import global_var

dicTxt = ''

def create_url(appid='1cb84079', apikey='cac2d31aa2c54a98eae25685e1036b44'):
    base_url = 'ws://rtasr.xfyun.cn/v1/ws?'

    ts = str(int(time.time()))

    baseString = appid + ts
    m = hashlib.md5()
    m.update(baseString.encode())
    baseString_md5 = m.hexdigest()
    signa = base64.b64encode(hmac.new(apikey.encode(), baseString_md5.encode(), hashlib.sha1).digest()).decode()

    params = {
        'appid': appid,
        'ts': ts,
        'signa': signa,
    }
    return base_url + urlencode(params)

def on_message(ws, message):
    global dicTxt
    result_dict = json.loads(message)
    if result_dict["action"] == "started":
        print('握手成功')
    if result_dict["action"] == "result":
        result_1 = result_dict
        type = json.loads(result_1["data"])["cn"]["st"]["type"]
        # print(type)
        if(type == "0"):
            result_2 = json.loads(result_1["data"])["cn"]["st"]["rt"]
            a = ''
            for i in result_2:
                for x in i["ws"]:
                    w = x['cw'][0]['w']
                    wp = x['cw'][0]['wp']
                    if wp != 's':
                        a += w
            print(a)
            dicTxt += a
            global_var.set_value('dicTxt', dicTxt)


    # print(message)


def on_error(ws, error):
    print(error)


def on_close(ws, close_status_code, close_msg):
    print("### closed ###")


def on_open(ws):
    def run(*args):
        rate = 16000
        format = pyaudio.paInt16
        channels = 1
        chunk = 1024

        p = pyaudio.PyAudio()
        stream = p.open(rate=rate, format=format, channels=channels, input=True)
        print("-----> 开始录音")
        while True:
            data = stream.read(chunk)
            ws.send(data)

    thread.start_new_thread(run, ())

def dictation():
# if __name__ == "__main__":
    websocket.enableTrace(False)
    ws = websocket.WebSocketApp(create_url(),
                                on_message=on_message,
                                on_error=on_error,
                                on_close=on_close)
    ws.on_open = on_open

    ws.run_forever()
