"""PlantUML and transition tables exported from the exact runtime definition."""
import argparse
import json
import textwrap
from pathlib import Path
from .policy import Policy, DEFAULT_POLICY


def pretty(node):
    if isinstance(node, dict):
        op, args = next(iter(node.items()))
        if op == 'ref': return args.replace('facts.', '').replace('parameters.', '')
        if op == 'not': return '!(' + pretty(args) + ')'
        sign = {'and': ' && ', 'or': ' || ', 'eq': ' == ', 'ne': ' != ', 'lt': ' < ', 'ge': ' >= '}[op]
        return '(' + sign.join(pretty(x) for x in args) + ')'
    return json.dumps(node)


def style(title):
    return ['@startuml', 'skinparam monochrome true', 'skinparam backgroundColor white',
            'skinparam defaultFontName Arial', 'skinparam defaultFontSize 18',
            'skinparam ArrowFontSize 16', 'skinparam shadowing false', 'hide empty description',
            'skinparam stateBackgroundColor white', 'skinparam stateBorderColor black', 'skinparam stateBorderThickness 1',
            'skinparam roundcorner 0', 'skinparam linetype polyline', 'title ' + title]


def export_policy(policy, output):
    out = Path(output); out.mkdir(parents=True, exist_ok=True)
    definition = policy.definition
    (out / 'policy.json').write_text(json.dumps(definition, indent=2) + '\n', encoding='utf-8')
    table = ['# A: runtime automata definition', '', f'Policy: `{policy.version}`; SHA256: `{policy.sha256}`', '',
             'Generated from JSON. Proposal transitions do not change state. Observed transitions follow actual effects.', '',
             '| Machine | Edge | Phase | From | To | Guard | Outcome |', '|---|---|---|---|---|---|---|']
    for m in definition['machines']:
        lines = style(m['id'] + ': observed state changes') + ['state "Actual observations" as Scope {']
        for state in m['states']: lines.append(f'state "{state}" as {state}')
        lines += [f'[*] --> {m["initial"]} : default reset']
        for e in m['transitions']:
            guard = pretty(e['when'])
            table.append(f'| {m["id"]} | {e["id"]} | {e["phase"]} | {e["from"]} | {e["to"]} | `{guard.replace("|", "&#124;")}` | {e["outcome"]} |')
            if e['phase'] != 'observed' or e['from'] == e['to']: continue
            if m['id'] == 'R1':
                # The second AND argument is an OR of fully specified events, directly from JSON.
                events = e['when']['and'][1]['or']
                labels = []
                for event in events:
                    fields = {term['eq'][0]['ref']: term['eq'][1] for term in event['and']}
                    labels.append(str(fields['event.device']) + '.' + str(fields['event.mode']))
                label = 'observe ' + ' / '.join(labels)
                guard_label = pretty(m['states'][e['to']])
            else:
                label = 'observe'
                guard_label = pretty(e['when'])
            lines.append(f'{e["from"]} --> {e["to"]} : {label}\\n[{guard_label}]')
        lines += ['}', 'legend bottom', 'Only observed state changes are drawn.',
                  'Self-transitions and proposal decisions: see transition-table.md.',
                  'A scenario reset selects its actual observed state.',
                  'endlegend', '@enduml', '']
        if m['id'] == 'R2':
            clock = definition['clocks']['rest']
            position = lines.index('endlegend')
            lines[position:position] = [f'Reset elapsed := 0 when {pretty(clock["reset_when"])}.',
                                        f'Then advance by simulation dt; rest_s = {definition["parameters"]["rest_s"]} seconds.']
        (out / (m['id'] + '-states.puml')).write_text('\n'.join(lines), encoding='utf-8')
        # Decision diagram: one state at a time so source guards remain legible.
        for state in m['states']:
            decisions = style(m['id'] + ' proposals in ' + state) + ['state "Proposal check (state unchanged)" as Scope {', f'state "{state}" as S', '[*] --> S']
            direction = iter(('left', 'right', 'down'))
            for e in m['transitions']:
                if e['phase'] == 'proposal' and e['from'] == state:
                    outcome = e['outcome'] + (': ' + e['reason'] if e['reason'] else '')
                    guard = '\\n'.join(textwrap.wrap(pretty(e['when']), width=52, break_long_words=False, break_on_hyphens=False))
                    decisions.append(f'S -{next(direction)}-> S : [{guard}]\\n/ {outcome}')
            decisions += ['}', '@enduml', '']
            (out / f'{m["id"]}-{state}-decisions.puml').write_text('\n'.join(decisions), encoding='utf-8')
    clocks = ['','## Clock reset rules','']
    for name, clock in definition['clocks'].items():
        clocks.append(f'- `{name}` uses `{clock["fact"]}`; reset to zero when `{pretty(clock["reset_when"])}`, then add elapsed simulation time.')
    (out / 'transition-table.md').write_text('\n'.join(table + clocks) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--policy', default=str(DEFAULT_POLICY))
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    export_policy(Policy.load(args.policy), args.output)


if __name__ == '__main__': main()
