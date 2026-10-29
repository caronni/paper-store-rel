#!/usr/bin/env python3
"""tables_fr.py -- markdown tables from the format round's measurement files
(never typed).  python tables_fr.py sets | seeds GROUP | edge | onebull | walls
"""
import json
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fr_common as C   # noqa: E402

CF = C.CONFIGS
HEAD = '| case | ' + ' | '.join(CF) + ' |\n|---|' + '---|' * len(CF)


def load_sets():
    return {c: json.load(open(os.path.join(C.OUT, 'runs-sets', c, f'sets-{c}.json'))) for c in CF}


def sets_table():
    S = load_sets()
    print('### verdicts\n\n| | ' + ' | '.join(CF) + ' |\n|---|' + '---|' * len(CF))
    for k in list('ABCDEFGHI') + ['I note', 'all', 'margin', 'F alone', 'blocks', 'secs']:
        row = []
        for c in CF:
            v = S[c]['verdict'][k]
            row.append({True: 'pass', False: '**FAIL**'}.get(v, str(v)) if not isinstance(v, int) or isinstance(v, bool)
                       else f'{v:,}')
        print(f'| {k} | ' + ' | '.join(row) + ' |')
    print('| slots missed | ' + ' | '.join(str(len(S[c]['slots']['missed'])) + ': ' +
                                       ' '.join(f'({a},{b})' for a, b in S[c]['slots']['missed'][:4]) +
                                       (' …' if len(S[c]['slots']['missed']) > 4 else '') for c in CF) + ' |')
    print('\n### every case: done (D) or chunks held / need; blocks per frame\n\n' + HEAD)
    for case in S[CF[0]]['cases']:
        row = []
        for c in CF:
            r = S[c]['cases'][case]
            h = 'D' if r['done'] else f"{r['held']}/{r['need']}"
            row.append(f"{h} [{' '.join(str(b) for b in r['blocks'])}]")
        same = len(set(row)) == 1
        print(f'| {case}{"" if not same else " (=)"} | ' + ' | '.join(row) + ' |')


def seeds_table(group):
    D = {c: json.load(open(os.path.join(C.OUT, 'seeds', f'{group}-{c}.json'))) for c in CF
         if os.path.exists(os.path.join(C.OUT, 'seeds', f'{group}-{c}.json'))}
    cf = [c for c in CF if c in D]
    keys = [('captures', lambda r: 1), ('candidates', lambda r: r['seeds']), ('false seeds', lambda r: r['false_seeds']),
            ('captures with a false seed', lambda r: int(r['false_seeds'] > 0)),
            ('false seeds that started a walk', lambda r: r['false_started_walk']),
            ('reads by false walks', lambda r: r['false_walk_reads']),
            ('  of them accepted', lambda r: r['false_walk_accepted']),
            ('  of them white', lambda r: r['false_walk_white']),
            ('true bullseyes in frame', lambda r: r['bullseyes_in_frame']),
            ('true bullseyes found', lambda r: r['true_found_in_frame']),
            ('header read alone', lambda r: int(r['header_alone'])),
            ('header read alone, true seeds only', lambda r: int(r['cf_header_alone'])),
            ('blocks accepted (walk, header known)', lambda r: r['blocks']),
            ('blocks accepted, true seeds only', lambda r: r['cf_blocks']),
            ('chunks held (walk, header known)', lambda r: r['chunks']),
            ('chunks held, true seeds only', lambda r: r['cf_chunks']),
            ('chunks lost to false seeds (Σ cost)', lambda r: r['cost_chunks']),
            ('captures where false seeds cost chunks', lambda r: int(r['cost_chunks'] > 0)),
            ('captures where false seeds gained chunks', lambda r: int(r['cost_chunks'] < 0))]
    print(f'### seeds, {group} (sums over captures)\n\n| | ' + ' | '.join(cf) + ' |\n|---|' + '---|' * len(cf))
    for name, fn in keys:
        print(f'| {name} | ' + ' | '.join(f'{sum(fn(r) for r in D[c]):,}' for c in cf) + ' |')
    mx = {c: max(D[c], key=lambda r: r['false_seeds']) for c in cf}
    print('| most false seeds in one capture | ' + ' | '.join(f"{mx[c]['false_seeds']} ({mx[c]['case']})" for c in cf) + ' |')
    print('\nper capture: false seeds / true found of in frame / cost\n\n' + HEAD)
    for i, r0 in enumerate(D[cf[0]]):
        row = []
        for c in cf:
            r = D[c][i]
            assert r['case'] == r0['case']
            row.append(f"{r['false_seeds']} / {r['true_found_in_frame']}/{r['bullseyes_in_frame']}"
                       f"{'' if r['header_alone'] else ' nh'} / {r['cost_chunks']:+d}")
        print(f"| {r0['case']} | " + ' | '.join(row) + ' |')


def edge_table():
    P = json.load(open(os.path.join(C.OUT, 'edge', 'pools.json')))
    pool = {(r['pool'], r['cfg']): r for r in P['runs']}
    pools = []
    for r in P['runs']:
        if (r['group'], r['pool']) not in pools:
            pools.append((r['group'], r['pool']))
    print('### pools: chunks held at the end (CLOSED = done, == bundle)\n\n| pool | ' + ' | '.join(CF) + ' |\n|---|' + '---|' * len(CF))
    for g in ('edge', 'q045', 'ring'):
        sums = {c: 0 for c in CF}
        for gg, p in pools:
            if gg != g:
                continue
            row = []
            for c in CF:
                r = pool[(p, c)]
                h = r['rows'][-1]['held'] or 0
                sums[c] += h
                row.append(f"{h}{' CLOSED' if r['closed'] else ''}{'' if r['output_equals_bundle'] in (None, True) else ' !='}"
                           f"{'' if r['rc'] == 0 else ' rc ' + str(r['rc'])}")
            print(f'| {p} | ' + ' | '.join(row) + ' |')
        if g != 'ring':
            print(f'| **{g} Σ** | ' + ' | '.join(f'**{sums[c]:,}**' for c in CF) + ' |')
    ap = os.path.join(C.OUT, 'edge', 'alone.json')
    if os.path.exists(ap):
        A = json.load(open(ap))
        al = {(r['pool'], r['cfg']): r['rows'][0] for r in A['runs']}
        names = []
        for r in A['runs']:
            if r['pool'] not in names:
                names.append(r['pool'])
        print('\n### frames alone: Σ printed bullseye count / Σ blocks / Σ chunks held\n\n| group | ' + ' | '.join(CF) +
              ' |\n|---|' + '---|' * len(CF))
        for g, pre in (('edge (12)', 'edge'), ('q045 (24)', 'q045'), ('ring', 'ring'), ('clean', 'clean')):
            fs = [n for n in names if n.startswith(pre)]
            print(f'| {g} | ' + ' | '.join(
                f"{sum(al[f, c]['bullseyes'] or 0 for f in fs)} / {sum(al[f, c]['blocks'] or 0 for f in fs):,} / "
                f"{sum(al[f, c]['held'] or 0 for f in fs):,}" for c in CF) + ' |')


def onebull_table():
    A = json.load(open(os.path.join(C.OUT, 'onebull', 'alone.json')))
    al = {(r['pool'], r['cfg']): r for r in A['runs']}
    S = {c: {r['case']: r for r in json.load(open(os.path.join(C.OUT, 'seeds', f'onebull-{c}.json')))}
         for c in CF if os.path.exists(os.path.join(C.OUT, 'seeds', f'onebull-{c}.json'))}
    names = []
    for r in A['runs']:
        if r['pool'] not in names:
            names.append(r['pool'])
    print('### one bullseye: survivor found (y/n) / header read alone (y/n) / blocks accepted / chunks held of 609'
          ' (CLOSED); + false seeds\n\n' + HEAD)
    for n in names:
        row = []
        for c in CF:
            r = al[n, c]
            x = r['rows'][0]
            s = S.get(c, {}).get(n)
            fnd = '?' if s is None else ('y' if s['true_found_in_frame'] else 'n')
            if s is not None and n.endswith('clean'):
                fnd = f"{s['true_found_in_frame']}/{s['bullseyes_in_frame']}"
            hdr = 'y' if x['need'] not in (None, '?') else 'n'
            fs = '' if s is None else f" +{s['false_seeds']}f"
            row.append(f"{fnd} / {hdr} / {x['blocks']} / {x['held']}{' CLOSED' if r['closed'] else ''}{fs}")
        print(f'| {n} | ' + ' | '.join(row) + ' |')


def walls_table():
    W = json.load(open(os.path.join(C.OUT, 'walls.json')))
    print('### paired walls, min (median) s over 3 rounds\n\n| frame | ' + ' | '.join(CF) + ' |\n|---|' + '---|' * len(CF))
    for f in sorted({w['frame'] for w in W}):
        xs = {c: [w['secs'] for w in W if w['frame'] == f and w['cfg'] == c] for c in CF}
        print(f'| {f} | ' + ' | '.join(f'{min(xs[c]):.2f} ({st.median(xs[c]):.2f})' for c in CF) + ' |')
    print(f"load1 {min(w['load1'] for w in W)}–{max(w['load1'] for w in W)}")


if __name__ == '__main__':
    a = sys.argv[1:]
    {'sets': sets_table, 'edge': edge_table, 'onebull': onebull_table, 'walls': walls_table}.get(
        a[0], lambda: seeds_table(a[1]))()
