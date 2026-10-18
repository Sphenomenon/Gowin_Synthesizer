#!/usr/bin/env python3
"""Compile geometry and MIDI controls only. Never ingest or emit sampled audio."""
import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import numpy as np

RATE = 48000
MAX_HZ = 2000
HARMONICS = 8
BUDGET = 16384
FORBIDDEN = {'.wav', '.wave', '.aif', '.aiff', '.au', '.pcm', '.raw', '.mp3', '.flac', '.ogg', '.m4a'}
FUNCTIONS = {k: getattr(np, k) for k in ('sin', 'cos', 'tan', 'sqrt', 'abs', 'exp')}


def equation(text, t):
    tree = ast.parse(text, mode='eval')
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call,
                                 ast.Name, ast.Load, ast.Constant, ast.Add, ast.Sub,
                                 ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd)):
            raise ValueError('unsupported equation syntax')
        if isinstance(node, ast.Name) and node.id not in {*FUNCTIONS, 't', 'pi'}:
            raise ValueError('unknown equation identifier: ' + node.id)
        if isinstance(node, ast.Call) and (not isinstance(node.func, ast.Name)
                                           or node.func.id not in FUNCTIONS or node.keywords):
            raise ValueError('unsupported equation call')
    result = eval(compile(tree, '<geometry>', 'eval'), {'__builtins__': {}},
                  dict(FUNCTIONS, t=t, pi=np.pi))
    return np.broadcast_to(result, t.shape).astype(float)


def svg_vertices(path):
    if path.suffix.lower() != '.svg':
        raise ValueError('only SVG geometry input is accepted')
    root = ET.parse(path).getroot()
    result = None
    for element in root.iter():
        kind = element.tag.rsplit('}', 1)[-1]
        if 'transform' in element.attrib:
            raise ValueError('SVG transforms require explicit flattening before compilation')
        if kind in ('svg', 'g', 'title', 'desc', 'metadata'):
            continue
        if result is not None:
            raise ValueError('exactly one closed SVG contour is supported')
        if kind in ('circle', 'ellipse'):
            cx, cy = float(element.get('cx', 0)), float(element.get('cy', 0))
            rx = float(element.get('r', element.get('rx', 0)))
            ry = float(element.get('r', element.get('ry', 0)))
            t = np.arange(2048) * (2*np.pi/2048)
            result = np.column_stack((cx + rx*np.cos(t), cy + ry*np.sin(t)))
        elif kind == 'polygon':
            values = [float(x) for x in re.findall(r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?', element.get('points', ''))]
            if len(values) < 6 or len(values) % 2:
                raise ValueError('invalid polygon')
            result = np.array(values).reshape(-1, 2)
        elif kind == 'path':
            data = element.get('d', '')
            tokens = re.findall(r'[A-Za-z]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?', data)
            if re.sub(r'[\s,]', '', data) != ''.join(tokens):
                raise ValueError('invalid SVG path tokens')
            vertices, cursor, origin, i, command, closed = [], np.zeros(2), None, 0, None, False
            counts = {'M': 2, 'L': 2, 'H': 1, 'V': 1, 'C': 6, 'Q': 4}
            while i < len(tokens):
                if tokens[i].isalpha():
                    command = tokens[i]; i += 1
                if command is None or command.upper() not in {*counts, 'Z'}:
                    raise ValueError('supported SVG commands: M L H V C Q Z (absolute/relative)')
                op = command.upper()
                if op == 'Z':
                    closed = True
                    if i != len(tokens):
                        raise ValueError('multiple SVG subpaths are unsupported')
                    break
                if closed or (op == 'M' and origin is not None):
                    raise ValueError('multiple SVG subpaths are unsupported')
                count = counts[op]
                args = np.array([float(x) for x in tokens[i:i+count]])
                if len(args) != count:
                    raise ValueError('incomplete SVG command')
                i += count
                start = cursor.copy()
                if op in ('M', 'L'):
                    cursor = args + (start if command.islower() else 0)
                    vertices.append(cursor.copy())
                    if op == 'M':
                        origin = cursor.copy(); command = 'l' if command.islower() else 'L'
                elif op in ('H', 'V'):
                    axis = 0 if op == 'H' else 1
                    cursor[axis] = args[0] + (start[axis] if command.islower() else 0)
                    vertices.append(cursor.copy())
                else:
                    controls = args.reshape(-1, 2) + (start if command.islower() else 0)
                    for u in np.linspace(0, 1, 65)[1:]:
                        if op == 'C':
                            p = (1-u)**3*start + 3*(1-u)**2*u*controls[0] + 3*(1-u)*u*u*controls[1] + u**3*controls[2]
                        else:
                            p = (1-u)**2*start + 2*(1-u)*u*controls[0] + u*u*controls[1]
                        vertices.append(p)
                    cursor = controls[-1].copy()
            if not closed:
                raise ValueError('SVG path must explicitly close with Z')
            result = np.array(vertices)
        else:
            raise ValueError('unsupported SVG element: ' + kind)
    if result is None:
        raise ValueError('no SVG geometry')
    return result


def resample(vertices, points):
    vertices = np.asarray(vertices, dtype=float)
    if vertices.ndim != 2 or vertices.shape[1] != 2 or len(vertices) < 3 or not np.isfinite(vertices).all():
        raise ValueError('finite X/Y contour with at least three vertices required')
    if np.array_equal(vertices[0], vertices[-1]):
        vertices = vertices[:-1]
    closed = np.vstack((vertices, vertices[0]))
    length = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    keep = np.r_[True, length > 1e-12]
    closed = closed[keep]
    distance = np.r_[0, np.cumsum(np.linalg.norm(np.diff(closed, axis=0), axis=1))]
    if distance[-1] <= 0:
        raise ValueError('zero-length contour')
    positions = np.arange(points) * distance[-1]/points
    return np.column_stack([np.interp(positions, distance, closed[:, j]) for j in (0, 1)])


def compile_geometry(document, directory, points=512):
    shapes = document.get('shapes', [])
    if points not in (128, 256, 512) or not 1 <= len(shapes) <= 8:
        raise ValueError('require 1..8 shapes, each 128/256/512 points')
    if len(shapes)*points*4 > BUDGET:
        raise ValueError('path ROM exceeds 16384-byte budget')
    arrays = []
    for shape in shapes:
        if set(shape) - {'name', 'svg', 'x', 'y', 'vertices'}:
            raise ValueError('unknown shape fields')
        sources = int('svg' in shape)+int('vertices' in shape)+int('x' in shape or 'y' in shape)
        if sources != 1:
            raise ValueError('choose exactly one geometry source')
        if 'svg' in shape:
            raw = resample(svg_vertices(directory/shape['svg']), points)
        elif 'vertices' in shape:
            raw = resample(shape['vertices'], points)
        else:
            t = np.arange(points)*2*np.pi/points
            raw = np.column_stack((equation(shape['x'], t), equation(shape['y'], t)))
        if not np.isfinite(raw).all():
            raise ValueError('non-finite path coordinates')
        raw -= raw.mean(axis=0)
        spectrum = np.fft.rfft(raw, axis=0)
        spectrum[HARMONICS+1:] = 0
        smooth = np.fft.irfft(spectrum, n=points, axis=0)
        extent = np.max(np.abs(smooth))
        if extent < 1e-12:
            raise ValueError('degenerate geometry after smoothing')
        arrays.append(np.rint(smooth * (30000/extent)).astype(np.int16))
    return np.array(arrays)


def compile_scene(scene, shape_count):
    if set(scene) - {'schema', 'duration_samples', 'events', 'description'}:
        raise ValueError('unknown scene fields')
    if scene.get('schema') != 'scope-control-v1' or not 30*RATE <= scene.get('duration_samples', 0) <= 60*RATE:
        raise ValueError('scene needs scope-control-v1 schema and 30..60 seconds duration')
    words = []
    previous = -1
    for event in scene['events']:
        if set(event) - {'sample', 'op', 'note', 'velocity', 'shape', 'cc', 'value'}:
            raise ValueError('unknown event fields; audio payloads are forbidden')
        sample = event['sample']
        if not isinstance(sample, int) or not previous <= sample <= scene['duration_samples']:
            raise ValueError('event timestamps must be ordered absolute 48 kHz samples')
        previous = sample
        op = event['op']
        allowed={'note_on': {'sample','op','note','velocity','shape'},
                 'note_off': {'sample','op','note'}, 'cc': {'sample','op','cc','value'},
                 'bend': {'sample','op','value'}}
        if op not in allowed or set(event)-allowed[op]:
            raise ValueError('unsupported fields for event '+str(op))
        if op in ('note_on', 'note_off'):
            note, velocity = event['note'], event.get('velocity', 0)
            if not isinstance(note, int) or not 0 <= note <= 95 or not isinstance(velocity, int) or not 0 <= velocity <= 127:
                raise ValueError('note/velocity out of supported range')
            if op == 'note_on' and velocity == 0:
                raise ValueError('note_on requires nonzero velocity')
            if op == 'note_on' and 'shape' in event:
                if not isinstance(event['shape'], int) or not 0 <= event['shape'] < shape_count:
                    raise ValueError('shape out of range')
                words.append((sample << 32) | (2 << 14) | (97 << 7) | event['shape'])
            data = ((1 if op == 'note_on' else 0) << 14) | (note << 7) | velocity
        elif op == 'cc':
            cc, value = event['cc'], event['value']
            if not all(isinstance(v, int) and 0 <= v <= 127 for v in (cc, value)):
                raise ValueError('CC/value out of range')
            if cc not in {1, 5, 7, 11, 64, 81, 90, 91, 92, 93, 94, 95, 97, 98, 99, 100, 101, 103, 120, 123}:
                raise ValueError('unsupported scene CC')
            if cc == 81 and value > 7:
                raise ValueError('effect mask must be 0..7')
            if cc == 103 and value == 0:
                raise ValueError('scene speed zero is unsupported')
            if cc in {91, 97} and value != 127 and value >= shape_count:
                raise ValueError('shape CC out of range')
            if cc == 91 and value == 127:
                raise ValueError('morph destination must be a shape id')
            if cc in {90, 95} and value not in {0, 64, 127}:
                raise ValueError('enable/mute CC must be 0, 64(toggle) or 127')
            data = (2 << 14) | (cc << 7) | value
        elif op == 'bend':
            value = event['value']
            if not isinstance(value, int) or not 0 <= value <= 16383:
                raise ValueError('bend requires unsigned 14-bit value')
            data = (4 << 14) | ((value & 127) << 7) | (value >> 7)
        else:
            raise ValueError('unsupported event op: '+str(op))
        words.append((sample << 32) | data)
    if len(words) > 256:
        raise ValueError('scene exceeds 256x64 control cue budget')
    return words


def audit_tree(root):
    for path in root.rglob('*'):
        if path.is_file():
            if path.suffix.lower() in FORBIDDEN:
                raise ValueError('audio file forbidden: '+str(path))
            head = path.read_bytes()[:16]
            if head.startswith((b'RIFF', b'FORM', b'fLaC', b'OggS', b'ID3', b'.snd')):
                raise ValueError('audio container signature forbidden: '+str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('geometry', type=Path)
    parser.add_argument('--scene', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--points', type=int, default=512)
    args = parser.parse_args()
    try:
        if args.geometry.suffix != '.json' or args.scene.suffix != '.json':
            raise ValueError('JSON geometry/scene sources required')
        audit_tree(args.geometry.parent)
        document = json.loads(args.geometry.read_text())
        if set(document) != {'schema', 'shapes'} or document['schema'] != 'scope-geometry-v1':
            raise ValueError('invalid geometry schema')
        geometry = compile_geometry(document, args.geometry.parent, args.points)
        scene = json.loads(args.scene.read_text())
        cues = compile_scene(scene, len(geometry))
        args.out.mkdir(parents=True, exist_ok=True)
        mem = ''.join(f'{(int(x)&65535)<<16 | (int(y)&65535):08x}\n' for shape in geometry for x, y in shape)
        (args.out/'paths.mem').write_text(mem)
        (args.out/'scene.json').write_text(json.dumps(scene, indent=2)+'\n')
        (args.out/'scene_controls.mem').write_text(''.join(f'{v:016x}\n' for v in cues)+('0000000000000000\n'*(256-len(cues))))
        (args.out/'rotation.mem').write_text(''.join(f'{(round(32767*math.cos(2*math.pi*n/512))&65535)<<16 | (round(32767*math.sin(2*math.pi*n/512))&65535):08x}\n' for n in range(512)))
        (args.out/'note_steps.mem').write_text(''.join(f'{round(440*2**((n-69)/12)*2**32/RATE):08x}\n' for n in range(128)))
        manifest = dict(schema='scope-geometry-rom-v1', coordinate_format='signed16 X then signed16 Y; normalized closed phase contour',
                        shape_count=len(geometry), points_per_shape=args.points, path_bytes=geometry.size*2,
                        harmonics=HARMONICS, maximum_scan_hz=MAX_HZ, guard_hz=20000,
                        cue_count=len(cues), cue_format='absolute sample timestamp[63:32], zero[31:18], MIDI control[17:0]',
                        inputs={str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.geometry, args.scene, Path(__file__),*[args.geometry.parent/shape['svg'] for shape in document['shapes'] if 'svg' in shape]]},
                        contains_pcm_audio=False, audio_payloads=0)
        manifest['artifacts'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in args.out.iterdir() if p.is_file() and p.name != 'manifest.json'}
        (args.out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
        audit_tree(args.out)
        print(json.dumps(dict(output=str(args.out), path_bytes=manifest['path_bytes'], cues=len(cues), pcm_audio=False)))
    except (ValueError, KeyError, SyntaxError, TypeError) as error:
        parser.error(str(error))

if __name__ == '__main__':
    main()
