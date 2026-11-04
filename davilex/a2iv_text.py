"""Reviewed A2 IV text translations; preserve record metadata and game statistics."""
import re

def dialogue_patch(data, catalog):
    """Replace only the text field after the seventh comma; preserve all other bytes."""
    lookup = {(e['section'].casefold(), e['key']): e for e in catalog['entries']}
    section = ''
    seen = set()
    output = []
    changed = 0
    for raw in data.decode('cp1252').splitlines(keepends=True):
        line = raw.rstrip('\r\n')
        ending = raw[len(line):]
        heading = re.fullmatch(r'\s*\[([^]]+)\]\s*', line)
        if heading:
            section = heading[1].casefold()
        m = re.match(r'(\s*(\d+)\s*=)(.*)', line)
        key = (section, m[2]) if m else None
        if key in lookup:
            entry = lookup[key]
            if key in seen:
                raise ValueError(f'Duplicate communicator entry: {key}')
            seen.add(key)
            fields = m[3].split(',', 7)
            if len(fields) != 8 or fields[0].strip().casefold() != entry['id'].casefold():
                raise ValueError(f'Communicator metadata mismatch: {key}')
            if fields[7].strip() not in (entry['source'], entry['target']):
                raise ValueError(f'Communicator text changed; preserving entry: {key}')
            target = entry['target']
            if any(c in target for c in ',\r\n'):
                raise ValueError(f'Use @ for commas and # for line breaks: {key}')
            whitespace = re.match(r'\s*', fields[7])[0]
            tail = fields[7][len(fields[7].rstrip()):]
            replacement = whitespace + target + tail
            if replacement != fields[7]:
                changed += 1
            fields[7] = replacement
            line = m[1] + ','.join(fields)
        output.append(line + ending)
    if seen != set(lookup):
        raise ValueError(f'Missing communicator entries: {set(lookup) - seen}')
    return ''.join(output).encode('cp1252'), changed

def static_patch(data, catalog):
    """Translate reviewed story/UI values without touching progression or car statistics."""
    lookup = {(e['section'], e['key'], e['occurrence']): e for e in catalog['static_entries']}
    continuations = {e['source']: e['target'] for e in catalog['static_continuations']}
    occurrences = {}
    seen = set()
    seen_continuations = set()
    output = []
    section = ''
    changed = 0
    for raw in data.decode('cp1252').splitlines(keepends=True):
        line = raw.rstrip('\r\n')
        ending = raw[len(line):]
        heading = re.fullmatch(r'\s*\[([^]]+)\]\s*', line)
        if heading:
            section = heading[1].casefold()
        m = re.match(r'(\s*([^;=]+?)\s*=)(.*)', line)
        if m:
            key = m[2].casefold()
            occurrence = occurrences.get((section, key), 0)
            occurrences[section, key] = occurrence + 1
            identity = (section, key, occurrence)
            if identity in lookup:
                entry = lookup[identity]
                if m[3].strip() not in (entry['source'], entry['target']):
                    raise ValueError(f'Story text changed; preserving entry: {identity}')
                if any(c in entry['target'] for c in '\r\n'):
                    raise ValueError(f'Unexpected multiline translation: {identity}')
                leading = re.match(r'\s*', m[3])[0]
                trailing = m[3][len(m[3].rstrip()):]
                new_line = m[1] + leading + entry['target'] + trailing
                changed += line != new_line
                line = new_line
                seen.add(identity)
        for source, target in continuations.items():
            if section == 'track6' and line in (source, target):
                changed += line != target
                line = target
                seen_continuations.add(source)
        output.append(line + ending)
    if seen != set(lookup) or seen_continuations != set(continuations):
        raise ValueError('Missing reviewed A2 IV story text; original preserved.')
    return ''.join(output).encode('cp1252'), changed
