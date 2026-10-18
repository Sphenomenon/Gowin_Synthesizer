#!/usr/bin/env python3
"""External TF playback assets only; never write audio into the FPGA checkout."""
from pathlib import Path
import argparse
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import wave

REPO = Path(__file__).resolve().parents[6]
UPSTREAM = 'https://github.com/djmango/oscilloscope-music.git'
COMMIT = 'f1315f22b01a9baa9147c173ff00d3279212eff8'
DEFAULT = Path.home() / 'Documents/oscilloscope_tf_assets_20261002'


def outside_repo(path):
    path = path.expanduser().resolve()
    if path == REPO or REPO in path.parents:
        raise ValueError('PCM assets must stay outside the FPGA checkout: ' + str(path))
    return path


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda: f.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def wav_info(path):
    import numpy as np
    with wave.open(str(path), 'rb') as w:
        if w.getnchannels() != 2 or w.getsampwidth() != 2 or w.getcomptype() != 'NONE':
            raise ValueError('requires uncompressed stereo PCM16 WAV')
        info = dict(rate_hz=w.getframerate(),channels=2,bits=16,frames=w.getnframes())
        pcm = np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').reshape(-1,2)
    if len(pcm) != info['frames'] or not len(pcm):
        raise ValueError('truncated or empty WAV')
    info.update(duration_s=info['frames']/info['rate_hz'],bytes=path.stat().st_size,
                peak_lsb=np.abs(pcm.astype(np.int32)).max(axis=0).tolist(),
                dc_lsb=pcm.mean(axis=0).tolist(),sha256=sha(path))
    return info,pcm


def prepare(assets):
    import numpy as np
    from scipy.signal import resample_poly
    assets.mkdir(parents=True,exist_ok=True)
    upstream = assets/'upstream'
    if not upstream.exists():
        subprocess.run(['git','clone',UPSTREAM,str(upstream)],check=True)
        subprocess.run(['git','-C',str(upstream),'checkout','--detach',COMMIT],check=True)
    head = subprocess.check_output(['git','-C',str(upstream),'rev-parse','HEAD'],text=True).strip()
    if head != COMMIT or subprocess.check_output(['git','-C',str(upstream),'status','--porcelain'],text=True):
        raise ValueError('upstream must be the clean, reviewed pinned commit '+COMMIT)
    env = dict(os.environ,PYTHONPATH=str(upstream/'src'))
    original = assets/'original'
    with (assets/'generation.log').open('w') as log:
        subprocess.run([sys.executable,'-m','oscilloscope_music.cli','--out',str(original),'--no-render'],
                       cwd=upstream,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    original_info,_ = wav_info(original/'oscilloscope_song.wav')
    centered = assets/'centered_44100.wav'
    with (assets/'centered_generation.log').open('w') as log:
        subprocess.run([sys.executable,str(Path(__file__).with_name('centered_song.py')),str(centered)],
                       cwd=upstream,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    centered_info,pcm = wav_info(centered)
    if original_info['rate_hz'] != 44100:
        raise ValueError('pinned source rate changed')
    # Identical linear-phase 160/147 polyphase filter for both axes. No mono
    # downmix, phase widening, reverb, pitch/time changes, or per-axis scaling.
    resampled = resample_poly(pcm.astype(np.float64),160,147,axis=0)
    expected = (len(pcm)*160+146)//147
    if len(resampled) != expected or not np.all(np.isfinite(resampled)):
        raise ValueError('resampling length/finite check')
    # Polyphase interpolation can overshoot individual source samples. A
    # single common attenuation preserves the stereo geometry without clipping.
    common_gain = min(1.0,0.98*32767/float(np.abs(resampled).max()))
    resampled *= common_gain
    if np.abs(resampled).max() > 32767:
        raise ValueError('resampling exceeds PCM16 headroom; refuse clipping')
    pcm48 = np.rint(resampled).astype('<i2')
    dest = assets/'OSCIMUS.WAV'
    with wave.open(str(dest),'wb') as w:
        w.setnchannels(2);w.setsampwidth(2);w.setframerate(48000);w.writeframes(pcm48.tobytes())
    info,_ = wav_info(dest)
    if info['rate_hz'] != 48000 or abs(info['duration_s']-original_info['duration_s']) > 1/48000:
        raise ValueError('output duration/rate mismatch')
    shutil.copyfile(upstream/'LICENSE',assets/'OSCILIC.TXT')
    manifest = dict(source=UPSTREAM,commit=COMMIT,license='MIT',
                    copyright='2026 Sulaiman Khan Ghori',original=original_info,centered=centered_info,tf_file=info,
                    adaptation='omit upstream per-note dx/dy placement before tanh; keep composition/timing/ratios/envelopes',
                    adapter_sha256=sha(Path(__file__).with_name('centered_song.py')),
                    conversion='stereo common-filter scipy resample_poly 160/147; common attenuation; round to PCM16',
                    common_gain=common_gain,
                    axes='Left=X, Right=Y',mode='external prerecorded TF playback',
                    live_contest_engine=False,hardware_tested=False,
                    note='Upstream video colors individual voices; hardware shows the summed stereo signal.')
    (assets/'OSCISRC.TXT').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(assets=str(assets),tf_file=info),indent=2))


def removable_mounts():
    tree = json.loads(subprocess.check_output(['lsblk','--json','--paths','-o','NAME,TYPE,RM,TRAN,FSTYPE,MOUNTPOINTS'],text=True))
    found = []
    def walk(node,removable=False):
        removable = removable or bool(node.get('rm'))
        if removable and node.get('fstype') == 'vfat':
            for mount in node.get('mountpoints') or []:
                if mount:
                    found.append((Path(mount).resolve(),node['name']))
        for child in node.get('children') or []:
            walk(child,removable)
    for node in tree['blockdevices']:
        walk(node)
    return found


def install(assets,mount,dry_run):
    candidates = removable_mounts()
    if mount:
        mount = outside_repo(mount)
        candidates = [(m,d) for m,d in candidates if m == mount]
    if len(candidates) != 1:
        raise ValueError('need exactly one mounted removable FAT16/FAT32 TF card; detected '+str(candidates))
    mount,device = candidates[0]
    # Root must be a mounted removable FAT filesystem, never /boot/efi or an
    # ordinary directory. No format, partition, raw-block, or board operations.
    actual = json.loads(subprocess.check_output(['findmnt','--json','--target',str(mount)],text=True))['filesystems'][0]
    if Path(actual['target']).resolve() != mount or actual['fstype'] != 'vfat':
        raise ValueError('target is not the exact FAT mount root')
    if 'ro' in actual['options'].split(','):
        raise ValueError('TF mount is read-only')
    info,_ = wav_info(assets/'OSCIMUS.WAV')
    manifest = json.loads((assets/'OSCISRC.TXT').read_text())
    if info != manifest['tf_file'] or manifest['commit'] != COMMIT:
        raise ValueError('prepared media differs from manifest')
    files = ['OSCIMUS.WAV','OSCILIC.TXT','OSCISRC.TXT']
    wavs = [p.name for p in mount.iterdir() if p.is_file() and p.suffix.upper()=='.WAV']
    if len(wavs) >= 16 and not (mount/'OSCIMUS.WAV').exists():
        raise ValueError('TF root already has 16 WAVs; HDL playlist budget exceeded')
    for name in files:
        dest = mount/name
        if dest.is_symlink() or (dest.exists() and (not dest.is_file() or sha(dest)!=sha(assets/name))):
            raise ValueError('refuse overwriting existing different file '+str(dest))
    if shutil.disk_usage(mount).free < sum((assets/name).stat().st_size for name in files if not (mount/name).exists()):
        raise ValueError('insufficient TF space')
    receipt = dict(mount=str(mount),device=device,dry_run=dry_run,files={},hardware_tested=False)
    for name in files:
        source,dest = assets/name,mount/name
        if not dry_run and not dest.exists():
            temp = mount/(Path(name).stem+'.TMP')
            with temp.open('xb') as target,source.open('rb') as origin:
                shutil.copyfileobj(origin,target);target.flush();os.fsync(target.fileno())
            # Keep every existing file, even if it appeared after preflight.
            if dest.exists():
                temp.unlink();raise ValueError('destination appeared during copy '+str(dest))
            # Linux renameat2(RENAME_NOREPLACE) prevents a concurrent writer
            # from making the preflight overwrite check stale. FAT supports it.
            libc=ctypes.CDLL(None,use_errno=True)
            rename=libc.renameat2
            rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
            rename.restype=ctypes.c_int
            if rename(-100,os.fsencode(temp),-100,os.fsencode(dest),1)!=0:
                error=ctypes.get_errno()
                temp.unlink()
                raise OSError(error,os.strerror(error),str(dest))
        if not dry_run and sha(dest)!=sha(source):
            raise ValueError('TF readback hash mismatch '+str(dest))
        receipt['files'][name]=sha(source)
    if not dry_run:
        fd = os.open(mount,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
        receipt['root_wav_directory_order']=[p.name for p in mount.iterdir() if p.is_file() and p.suffix.upper()=='.WAV']
        (assets/'install_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','install','inspect'))
    parser.add_argument('--assets',type=Path,default=DEFAULT)
    parser.add_argument('--mount',type=Path)
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    try:
        assets=outside_repo(args.assets)
        if args.action=='prepare': prepare(assets)
        elif args.action=='install': install(assets,args.mount,args.dry_run)
        else: print(json.dumps([(str(m),d) for m,d in removable_mounts()],indent=2))
    except (ValueError,OSError,subprocess.CalledProcessError) as error:
        print('ERROR: '+str(error),file=sys.stderr);return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
