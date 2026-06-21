"""Compile .po files to .mo without requiring system gettext tools."""
import struct
import os
import re


def parse_po(po_path):
    with open(po_path, encoding='utf-8') as f:
        content = f.read()

    entries = {}
    pattern = re.compile(r'msgid\s+"((?:[^"\\]|\\.)*)"\s+msgstr\s+"((?:[^"\\]|\\.)*)"', re.DOTALL)
    for m in pattern.finditer(content):
        msgid = m.group(1).replace('\\n', '\n').replace('\\"', '"')
        msgstr = m.group(2).replace('\\n', '\n').replace('\\"', '"')
        if msgstr:
            entries[msgid] = msgstr
    return entries


def build_mo(entries):
    keys = sorted(entries.keys(), key=lambda s: s.encode('utf-8'))
    values = [entries[k] for k in keys]

    key_bytes = [k.encode('utf-8') for k in keys]
    val_bytes = [v.encode('utf-8') for v in values]

    n = len(keys)
    header_size = 28
    key_table_size = n * 8
    val_table_size = n * 8

    key_start = header_size + key_table_size + val_table_size
    key_offsets = []
    pos = key_start
    for kb in key_bytes:
        key_offsets.append((len(kb), pos))
        pos += len(kb) + 1

    val_start = pos
    val_offsets = []
    for vb in val_bytes:
        val_offsets.append((len(vb), pos))
        pos += len(vb) + 1

    result = struct.pack('<IIIIIII',
        0xde120495,  # magic
        0,           # revision
        n,           # num strings
        header_size, # key table offset
        header_size + key_table_size,  # val table offset
        0,           # hash table size
        0,           # hash table offset
    )

    for length, offset in key_offsets:
        result += struct.pack('<II', length, offset)
    for length, offset in val_offsets:
        result += struct.pack('<II', length, offset)

    for kb in key_bytes:
        result += kb + b'\x00'
    for vb in val_bytes:
        result += vb + b'\x00'

    return result


def compile_all():
    locale_dir = os.path.join(os.path.dirname(__file__), 'locale')
    count = 0
    for lang in os.listdir(locale_dir):
        po_path = os.path.join(locale_dir, lang, 'LC_MESSAGES', 'django.po')
        mo_path = os.path.join(locale_dir, lang, 'LC_MESSAGES', 'django.mo')
        if os.path.exists(po_path):
            entries = parse_po(po_path)
            with open(mo_path, 'wb') as f:
                f.write(build_mo(entries))
            print(f"  {lang}: {len(entries)} traductions compilees -> django.mo")
            count += 1
    print(f"\n{count} fichier(s) .mo généré(s).")


if __name__ == '__main__':
    compile_all()
