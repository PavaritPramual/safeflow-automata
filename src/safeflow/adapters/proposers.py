"""Real providers translate native output to opaque declared action IDs."""
import json
import os
import socket
import time
from urllib.error import URLError
from urllib.request import Request, urlopen


def request_json(url, payload=None, timeout=120, token=None):
    headers = {'Content-Type': 'application/json'}
    if token: headers['Authorization'] = 'Bearer ' + token
    req = Request(url, data=None if payload is None else json.dumps(payload).encode(), headers=headers)
    with urlopen(req, timeout=timeout) as response: return json.load(response)


class JsonActionProposer:
    """Only decoding is shared; it never consults automata guards."""
    def __init__(self, model, url, prompt, actions, timeout=120, options=None):
        self.model, self.url, self.prompt = model, url.rstrip('/'), prompt
        self.actions, self.timeout, self.options = tuple(actions), timeout, dict(options or {})

    def metadata(self):
        return {'provider': self.provider, 'model': self.model, 'url': self.url,
                'options': self.options, 'command_origin': 'model'}

    def messages(self, observation):
        return [{'role': 'system', 'content': self.prompt + '\nAllowed action IDs: ' + ', '.join(self.actions)},
                {'role': 'user', 'content': json.dumps(observation, ensure_ascii=False, sort_keys=True)}]

    def schema(self):
        return {'type': 'object', 'properties': {'action': {'type': 'string', 'enum': list(self.actions)}},
                'required': ['action'], 'additionalProperties': False}

    def _call(self, url, payload, token=None):
        start = time.perf_counter()
        result = {'prompt': payload['messages'], 'request': payload, 'model': self.metadata(), 'latency_ms': None}
        try: result['raw'] = request_json(url, payload, self.timeout, token)
        except (TimeoutError, OSError, URLError, ValueError) as exc:
            reason = getattr(exc, 'reason', exc)
            result.update(raw=None, error_kind='timeout' if isinstance(reason, (TimeoutError, socket.timeout)) else 'adapter_error',
                          error=type(exc).__name__)
        result['latency_ms'] = (time.perf_counter()-start)*1000
        return result

    def normalize(self, response):
        if response.get('error_kind'):
            return {'kind': response['error_kind'], 'action': None}
        try:
            content = self.content(response['raw'])
            def unique(pairs):
                value = {}
                for k, v in pairs:
                    if k in value: raise ValueError('duplicate_key')
                    value[k] = v
                return value
            value = json.loads(content, object_pairs_hook=unique)
            if type(value) is not dict or set(value) != {'action'} or type(value['action']) is not str or value['action'] not in self.actions:
                raise ValueError('unknown_action_or_shape')
            return {'kind': 'proposal', 'action': value['action']}
        except (KeyError, IndexError, TypeError, ValueError):
            return {'kind': 'invalid_output', 'action': None}


class OllamaProposer(JsonActionProposer):
    provider = 'ollama'

    def propose(self, observation, seed=0):
        payload = {'model': self.model, 'messages': self.messages(observation), 'format': self.schema(),
                   'stream': False, 'think': False,
                   'options': {'temperature': 0, 'num_ctx': 2048, 'num_predict': 128, 'num_gpu': 0, **self.options, 'seed': seed}}
        return self._call(self.url + '/api/chat', payload)

    def content(self, raw): return raw['message']['content']


class OpenAICompatibleProposer(JsonActionProposer):
    provider = 'openai_compatible'

    def __init__(self, *args, api_key_env=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_key_env = api_key_env

    def propose(self, observation, seed=0):
        token = os.environ.get(self.api_key_env) if self.api_key_env else None
        if self.api_key_env and not token:
            return {'raw': None, 'error_kind': 'adapter_error', 'error': 'missing_provider_credential',
                    'prompt': self.messages(observation), 'model': self.metadata()}
        payload = {'model': self.model, 'messages': self.messages(observation), 'temperature': 0,
                   'response_format': {'type': 'json_schema', 'json_schema': {'name': 'action', 'strict': True, 'schema': self.schema()}},
                   **self.options}
        return self._call(self.url + '/chat/completions', payload, token)

    def content(self, raw): return raw['choices'][0]['message']['content']
