import openai

class ProxyCaller(object):
    '''
    source = 'internal' 即使用之江内部部署的模型。
    参考 https://qwen.readthedocs.io/zh-cn/latest/deployment/sglang.html
    '''
    def __init__(self, source, url, api_key, model=None):
        self.client = openai.Client(base_url=url, api_key=api_key)

        if source=='external':            
            if model is None:
                model = "gpt-5"
        else:
            models = self.client.models.list()
            model = models.data[0].id
            print('internal:', model)
        self.set_model(model)

    def set_model(self, model: str) -> None:
        self.model = model

    def __call__(self, content_in="ping!", enable_thinking=True):
        kwargs = dict(
            model=self.model,
            messages=[
                {
                "role": "user",
                "content": content_in
                }
            ],
            temperature=0.7,
            presence_penalty=0.0,
            frequency_penalty=0.0,
            top_p=1.0,
            max_completion_tokens=2000,
            stream=False,
            timeout=600,
        )
        try:
            kwargs["extra_body"] = {
                "top_k": 20,
                "chat_template_kwargs": {"enable_thinking": enable_thinking},
            }
            response = self.client.chat.completions.create(**kwargs)
            thinking = getattr(response.choices[0].message, 'reasoning_content', None)
        except Exception:
            kwargs.pop("extra_body", None)
            response = self.client.chat.completions.create(**kwargs)
            thinking = None
        res = {'thinking': thinking, 'content': response.choices[0].message.content}
        return res

def direct_post(url):
    headers = {
        "Content-Type": "application/json",
        "Authorization": ""
    }
    payload = {
        "model": os.getenv("LOCAL_MODEL", "Qwen3-8B"),
        "messages": [{"role": "user", "content": "hello"}],
        "temperature": 0.7,
        "max_tokens": 150
    }

    resp = requests.post(url, headers=headers, json=payload, stream=False)
    print(resp.json()) #["choices"][0]["message"]["content"])

def read_API_list(source):
    return API_L[source]['url'], API_L[source]['key']

if __name__ == "__main__":
    import time,sys
    import json

    with open('./API.json', 'r') as fh:
        API_L = json.load(fh)

    model_name = sys.argv[1]
    bThink = sys.argv[2] == 'True'

    start = time.time()

    url, key = read_API_list(model_name)
    PC = ProxyCaller(model_name, url, key)

    a = PC('解释生物的中心法则', enable_thinking=bThink)
    print('think:', a['thinking'])
    print('content:', a['content'])

    end = time.time()
    print(time.strftime('start %H:%M:%S',time.localtime(start)))
    print(time.strftime('end %H:%M:%S',time.localtime(end)))
    print('dur', end-start )
