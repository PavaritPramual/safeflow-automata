"""Administrative commands; people control the lab through Home Assistant."""
import argparse
import json
import os
import sys
import threading
from pathlib import Path
from .core.definition import Definition
from .verification import build_bundle, UppaalVerifier
from .monitoring import check_file


def main(argv=None):
    parser = argparse.ArgumentParser(prog='safeflow')
    sub = parser.add_subparsers(dest='command', required=True)
    verify = sub.add_parser('verify', help='Build a new immutable UPPAAL verification bundle')
    verify.add_argument('--definition', default='examples/smart-home/policy.yaml')
    verify.add_argument('--output', required=True)
    verify.add_argument('--verifyta', default=os.environ.get('SAFEFLOW_VERIFYTA'))
    verify.add_argument('--timeout', type=float, default=30)
    serve = sub.add_parser('serve', help='Run the verified API and Home Assistant lab')
    serve.add_argument('--config', default='examples/smart-home/lab.yaml')
    serve.add_argument('--verification')
    serve.add_argument('--logs', default='logs')
    serve.add_argument('--host', default='0.0.0.0')
    serve.add_argument('--port', type=int, default=8765)
    serve.add_argument('--interval', type=float, default=0)
    serve.add_argument('--model')
    serve.add_argument('--ollama-url')
    check = sub.add_parser('check', help='Check an ordered observed path X against A')
    check.add_argument('trace')
    check.add_argument('--live-prefix', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'verify':
            if not args.verifyta: parser.error('set --verifyta or SAFEFLOW_VERIFYTA to a licensed verifier executable')
            verifier = UppaalVerifier(args.verifyta, args.timeout)
            directory = build_bundle(Definition.load(args.definition), args.output)
            report = verifier.verify(directory)
            print(json.dumps({'status': report['status'], 'results': report['results'], 'bundle': str(directory.resolve())}, indent=2))
            return 0 if report['status'] == 'passed' else 2
        if args.command == 'check':
            result = check_file(args.trace, require_seal=not args.live_prefix)
            print(json.dumps(result, indent=2, ensure_ascii=True))
            return 0 if result['status'] == 'conforms' else 2
        from .application import Application
        from .api import make_server
        from .configuration import load_key
        if args.interval < 0: parser.error('interval cannot be negative')
        app = Application(args.config, logs=args.logs, verification=args.verification)
        if args.model: app.config['proposer']['model'] = args.model
        if args.ollama_url: app.config['proposer']['url'] = args.ollama_url
        server = make_server(app, load_key(), args.host, args.port)
        stop = threading.Event()
        worker = None
        if args.interval:
            def loop():
                while not stop.wait(args.interval):
                    try: app.lab_step()
                    except Exception: break
            worker = threading.Thread(target=loop, daemon=True); worker.start()
        print(json.dumps({'port': args.port, **app.health(), 'reason': app.readiness_error}), flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally:
            stop.set()
            app.request_stop()
            # Do not seal an episode while an in-flight model call can still act.
            if worker: worker.join(timeout=1)
            server.server_close()
            if not worker or not worker.is_alive(): app.close()
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 2


if __name__ == '__main__': raise SystemExit(main())
