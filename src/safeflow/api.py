"""Authenticated versioned service API plus the Home Assistant lab facade."""
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class NotReady(RuntimeError): pass


def fields(data, required=(), optional=()):
    if type(data) is not dict or not set(required) <= set(data) or set(data)-set(required)-set(optional):
        raise ValueError('invalid_request_fields')


def make_server(application, key, host='127.0.0.1', port=8765):
    if type(key) is not str or len(key) < 24: raise ValueError('api_key_too_short')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args): pass

        def reply(self, code, value):
            body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers(); self.wfile.write(body)

        def authenticated(self):
            return hmac.compare_digest(self.headers.get('Authorization', '').encode(), ('Bearer ' + key).encode())

        def do_GET(self):
            if self.path == '/health':
                self.reply(200, application.health()); return
            if not self.authenticated(): self.reply(401, {'error': 'unauthorized'}); return
            try:
                if self.path == '/v1/verification': self.reply(200, application.verification_status())
                elif self.path == '/state': self.reply(200, application.lab_state())
                elif self.path.startswith('/v1/sessions/') and len(self.path.split('/')) == 4:
                    self.reply(200, application.get_session(self.path.split('/')[3]).snapshot())
                else: self.reply(404, {'error': 'not_found'})
            except KeyError: self.reply(404, {'error': 'session_not_found'})
            except Exception as exc: self.reply(503, {'error': str(exc)})

        def do_POST(self):
            if not self.authenticated(): self.reply(401, {'error': 'unauthorized'}); return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 65536: raise ValueError('invalid_request_size')
                def pairs(items):
                    out = {}
                    for k, v in items:
                        if k in out: raise ValueError('duplicate_json_key')
                        out[k] = v
                    return out
                def invalid_constant(value): raise ValueError('nonfinite_json_number')
                data = json.loads(self.rfile.read(size), object_pairs_hook=pairs, parse_constant=invalid_constant)
                if type(data) is not dict: raise ValueError('json_object_required')
                path = self.path.split('/')
                if self.path == '/v1/sessions':
                    fields(data, optional=('facts', 'time_s'))
                    session = application.create_session(**data)
                    self.reply(201, session.snapshot())
                elif len(path) == 5 and path[1:3] == ['v1', 'sessions']:
                    session = application.get_session(path[3])
                    if path[4] == 'events':
                        fields(data, ('event_id', 'source', 'kind'), ('action', 'raw', 'metadata'))
                        replayed = data['event_id'] in session.decisions
                        self.reply(200, {**session.submit(**data), 'replayed': replayed,
                                         'observation_recorded': data['event_id'] in session.observations})
                    elif path[4] == 'observations':
                        fields(data, ('event_id', 'facts', 'time_s', 'applied_at_s'), ('evidence',))
                        self.reply(200, session.observe(**data))
                    elif path[4] == 'close':
                        fields(data); session.finish(); self.reply(200, session.snapshot())
                    else: self.reply(404, {'error': 'not_found'})
                elif self.path == '/step':
                    fields(data, optional=('seed', 'request_id'))
                    if type(data.get('seed', 0)) is not int: raise ValueError('integer_seed_required')
                    if 'request_id' in data and (type(data['request_id']) is not str or not 1 <= len(data['request_id']) <= 128):
                        raise ValueError('invalid_request_id')
                    self.reply(200, application.lab_step(**data))
                elif self.path == '/human':
                    fields(data, ('device', 'mode'))
                    self.reply(202, {'request_id': application.lab_enqueue(data), 'status': 'queued'})
                elif self.path == '/goals':
                    self.reply(200, application.lab_goals(data))
                elif self.path == '/reset':
                    self.reply(200, application.lab_reset(data))
                else: self.reply(404, {'error': 'not_found'})
            except NotReady as exc: self.reply(503, {'error': 'not_ready', 'reason': str(exc)})
            except KeyError: self.reply(404, {'error': 'session_not_found'})
            except (ValueError, TypeError) as exc: self.reply(400, {'error': str(exc)})
            except RuntimeError as exc: self.reply(409, {'error': str(exc)})
            except Exception as exc: self.reply(503, {'error': type(exc).__name__})

    return ThreadingHTTPServer((host, port), Handler)
