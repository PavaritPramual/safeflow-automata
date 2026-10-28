"""A local demo viewer composed around the real verified Application.

Run: python -m tools.live_console --config examples/smart-home/lab.yaml
No production engine changes and no fabricated proposer responses.
"""
import argparse
import copy
import hmac
import json
import math
import os
import secrets
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone, timedelta
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

import yaml
from safeflow.application import Application

ASSETS = Path(__file__).with_name('console_assets')


class ForwardingSink:
    """Only display records after the real durable sink has accepted them."""
    def __init__(self, sink, callback):
        self.sink, self.callback = sink, callback

    def write(self, row):
        self.sink.write(row)
        self.callback(row)


class Console:
    def __init__(self, application, interval=3):
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError('positive_interval_required')
        self.app, self.interval = application, interval
        self.condition = threading.Condition(threading.RLock())
        self.events, self.queue = deque(maxlen=1000), deque()
        self.submissions = {}
        self.sequence = self.round = 0
        self.running = self.busy = self.closing = False
        self.error = None
        self.token = secrets.token_urlsafe(32)
        self.state = application.lab_state()
        self.ready = self.state.get('readiness') == 'ready'
        self.commands = {}
        names = {'air_conditioner': 'AC', 'heater': 'Heater',
                 'ventilation_fan': 'Fan', 'light': 'Light'}
        for action, spec in application.definition.data['actions'].items():
            if len(spec['set']) != 1:
                continue
            fact, mode = next(iter(spec['set'].items()))
            device = application.config['bindings'][fact]
            self.commands[action] = {
                'label': ('Turn off ' if mode == 'off' else 'Turn on ') + names.get(device, device),
                'request': {'device': device, 'mode': mode},
            }
        receipt_id = str(uuid.uuid4())
        application.logs.mkdir(parents=True, exist_ok=True)
        self.receipts = application.logs / ('demo-requests-' + receipt_id + '.jsonl')
        self.worker = threading.Thread(target=self._work, name='console-rounds', daemon=True)
        if self.ready:
            self.session = application.loop.session
            self.session.sink = ForwardingSink(self.session.sink, self._record)
            self.emit('session', {'session_id': self.session.id,
                                 'definition_sha256': application.definition.sha256})
        self.worker.start()

    def emit(self, kind, data, **extra):
        with self.condition:
            self.sequence += 1
            self.events.append({'id': self.sequence, 'kind': kind, 'round': self.round,
                                'time': datetime.now(timezone(timedelta(hours=7))).strftime('%H:%M:%S'),
                                'data': copy.deepcopy(data), **extra})
            self.condition.notify_all()

    def _record(self, row):
        name = row['event']
        if name == 'received' and row['source'] == 'ai':
            envelope = row['raw'] if isinstance(row['raw'], dict) else {}
            native = envelope.get('raw')
            request = envelope.get('request') or {}
            self.emit('ai_request', request or envelope.get('prompt'), event_id=row['event_id'])
            content = None
            if isinstance(native, dict):
                message = native.get('message')
                if isinstance(message, dict):
                    content = message.get('content')
                elif native.get('choices'):
                    content = native['choices'][0].get('message', {}).get('content')
            self.emit('ai_output', envelope, content=content, native=native, event_id=row['event_id'])
        elif name == 'received':
            self.emit('human_command', row['raw'], event_id=row['event_id'])
        elif name == 'decision':
            self.emit('decision', {'normalized': row['normalized'], 'result': row['result']},
                      event_id=row['event_id'])
        elif name == 'observation':
            self.emit('observation', row['observation'], event_id=row['event_id'])
        elif name in ('fault', 'session_halt', 'session_end'):
            self.emit(name, row)

    def start(self):
        with self.condition:
            if not self.ready or self.closing or self.error or self.state.get('halted'):
                raise RuntimeError('session_not_ready_restart_service')
            if not self.running:
                self.running = True
                self.emit('info', 'Auto loop started')
                self.condition.notify_all()

    def pause(self):
        with self.condition:
            self.running = False
            self.emit('info', 'Stopping after current round' if self.busy
                      else 'Paused')
            self.condition.notify_all()

    def _receipt(self, event, **fields):
        record = {'event': event, 'time_ns': time.time_ns(), **fields}
        with self.receipts.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())

    def submit(self, action, request_id):
        with self.condition:
            if type(action) is not str or action not in self.commands or type(request_id) is not str or not 1 <= len(request_id) <= 128:
                raise ValueError('invalid_human_request')
            if self.closing or not self.ready or self.error or self.state.get('halted'):
                raise RuntimeError('session_not_ready')
            if request_id in self.submissions:
                if self.submissions[request_id] != action:
                    raise ValueError('request_id_content_mismatch')
                return {'request_id': request_id, 'replayed': True}
            if len(self.queue) >= 32:
                raise ValueError('human_queue_full')
            # The demo receipt is separate from the core trace. The core receives
            # it only between rounds, so HTTP stays responsive during a model call.
            self._receipt('accepted', request_id=request_id, action=action)
            self.queue.append((request_id, action))
            self.submissions[request_id] = action
            self.emit('human_queued', {'request_id': request_id, 'action': action,
                                      'label': self.commands[action]['label'],
                                      'status': 'queued for next round'})
            self.condition.notify_all()
            return {'request_id': request_id, 'replayed': False}

    def snapshot(self, after=0):
        with self.condition:
            return {'running': self.running, 'busy': self.busy, 'error': self.error,
                    'ready': self.ready, 'pending': len(self.queue), 'round': self.round,
                    'state': copy.deepcopy(self.state), 'interval': self.interval,
                    'events': [copy.deepcopy(e) for e in self.events if e['id'] > after],
                    'cursor': self.sequence,
                    'dropped': bool(self.events and after < self.events[0]['id'] - 1)}

    def rules(self):
        data = self.app.definition.data
        image = json.loads((ASSETS / 'overview.json').read_text(encoding='utf-8'))
        return {'definition': data, 'sha256': self.app.definition.sha256,
                'yaml': yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                'verification': copy.deepcopy(self.app._verification),
                'overview_matches': image['definition_sha256'] == self.app.definition.sha256,
                'overview_caption': image['caption'],
                'commands': [{'id': k, 'label': v['label']} for k, v in self.commands.items()]}

    def _work(self):
        next_round = 0
        while True:
            with self.condition:
                while not self.closing and (not self.running or time.monotonic() < next_round):
                    self.condition.wait(None if not self.running else max(0, next_round-time.monotonic()))
                if self.closing:
                    return
                self.busy = True
                self.round += 1
                human = self.queue.popleft() if self.queue else None
                before = copy.deepcopy(self.state)
            try:
                if human:
                    ident, action = human
                    core_id = self.app.lab_enqueue(self.commands[action]['request'])
                    self._receipt('delivered', request_id=ident, core_request_id=core_id)
                    self.emit('human_delivered', {'request_id': ident, 'core_request_id': core_id,
                                                 'action': action})
                self.emit('round_start', {'source': 'human' if human else 'ai',
                                         'facts': before.get('facts'),
                                         'time_s': before.get('simulation_time_s')})
                result = self.app.lab_step()
                with self.condition:
                    self.state = result
                    self.state['readiness'] = 'ready'
                if result.get('halted'):
                    raise RuntimeError('automata_session_halted')
                self.emit('round_end', {'simulation_time_s': result['simulation_time_s'],
                                        'last_result': result['last_result']})
            except Exception as exc:
                with self.condition:
                    self.running = False
                    self.error = str(exc)
                self.emit('error', {'error': str(exc), 'type': type(exc).__name__})
            finally:
                with self.condition:
                    self.busy = False
                    next_round = time.monotonic() + self.interval
                    self.condition.notify_all()

    def close(self):
        with self.condition:
            self.closing, self.running = True, False
            self.condition.notify_all()
        self.worker.join(timeout=130)
        if self.worker.is_alive():
            raise RuntimeError('round_still_running_session_not_closed')
        with self.condition:
            for ident, action in self.queue:
                self._receipt('cancelled_on_service_shutdown', request_id=ident, action=action)
            self.queue.clear()
        self.app.close()


def make_server(console, port=8766):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, data, mime='application/json; charset=utf-8', cookie=False):
            body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; frame-ancestors 'none'; object-src 'none'")
            if cookie:
                self.send_header('Set-Cookie', 'console_session='+console.token+'; HttpOnly; SameSite=Strict; Path=/')
            self.end_headers()
            self.wfile.write(body)

        def local_host(self):
            number = self.server.server_port
            return self.headers.get('Host') in (f'localhost:{number}', f'127.0.0.1:{number}')

        def do_GET(self):
            if not self.local_host():
                self.reply(403, {'error': 'local_host_only'}); return
            url = urlsplit(self.path)
            if url.path == '/':
                self.reply(200, (ASSETS/'index.html').read_bytes(), 'text/html; charset=utf-8', cookie=True)
            elif url.path in ('/console.js', '/style.css', '/overview.svg'):
                name = url.path[1:]
                mime = {'console.js':'text/javascript; charset=utf-8', 'style.css':'text/css; charset=utf-8',
                        'overview.svg':'image/svg+xml'}[name]
                self.reply(200, (ASSETS/name).read_bytes(), mime)
            elif url.path == '/api/rules':
                self.reply(200, console.rules())
            elif url.path == '/api/events':
                try:
                    values = parse_qs(url.query).get('after', ['0'])
                    if len(values) != 1: raise ValueError()
                    after = int(values[0])
                    if after < 0: raise ValueError()
                    self.reply(200, console.snapshot(after))
                except ValueError:
                    self.reply(400, {'error': 'invalid_cursor'})
            else:
                self.reply(404, {'error': 'not_found'})

        def do_POST(self):
            cookie = SimpleCookie()
            try: cookie.load(self.headers.get('Cookie', ''))
            except Exception: pass
            received = cookie.get('console_session')
            if (not self.local_host() or self.headers.get('Origin') != 'http://'+self.headers.get('Host', '')
                    or not received or not hmac.compare_digest(received.value.encode(), console.token.encode())):
                self.reply(403, {'error': 'local_session_required'}); return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 4096 or self.headers.get_content_type() != 'application/json':
                    raise ValueError('invalid_request')
                def pairs(items):
                    result = {}
                    for key, value in items:
                        if key in result: raise ValueError('duplicate_json_key')
                        result[key] = value
                    return result
                data = json.loads(self.rfile.read(size), object_pairs_hook=pairs)
                if type(data) is not dict: raise ValueError('object_required')
                if self.path == '/api/start' and data == {}:
                    console.start(); self.reply(200, {'status':'running'})
                elif self.path == '/api/stop' and data == {}:
                    console.pause(); self.reply(200, {'status':'stopping_after_current_round'})
                elif self.path == '/api/human' and set(data) == {'action','request_id'}:
                    self.reply(202, console.submit(**data))
                else:
                    raise ValueError('unknown_action_or_fields')
            except (ValueError, TypeError, KeyError) as exc:
                self.reply(400, {'error':str(exc)})
            except RuntimeError as exc:
                self.reply(409, {'error':str(exc)})
            except OSError:
                self.reply(503, {'error':'request_receipt_not_saved'})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='examples/smart-home/lab.yaml')
    parser.add_argument('--logs', default='logs/live-console')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--interval', type=float, default=3)
    parser.add_argument('--paused', action='store_true', help='Wait for the web Start button')
    args = parser.parse_args()
    app = Application(args.config, logs=args.logs)
    console = Console(app, args.interval)
    try:
        server = make_server(console, args.port)
    except OSError:
        console.close()
        raise
    if not args.paused and console.ready:
        console.start()
    print(json.dumps({'url':f'http://localhost:{server.server_port}', 'ready':console.ready,
                      'definition_sha256':app.definition.sha256, 'logs':str(app.logs)}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        console.close()


if __name__ == '__main__':
    main()
