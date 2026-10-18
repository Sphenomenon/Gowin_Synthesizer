#!/usr/bin/env python3
"""Summarize saved telemetry without changing touch events or hardware state."""
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import statistics


def summarize(path):
    frames = []
    rejected = 0
    for line in Path(path).read_text().splitlines():
        try:
            frame = json.loads(line)
            if all(key in frame for key in ('timestamp', 'key_device', 'slider_device')):
                frames.append(frame)
        except ValueError:
            rejected += 1
    if not frames:
        raise ValueError(f'No telemetry frames: {path}')
    duration = (datetime.fromisoformat(frames[-1]['timestamp']) -
                datetime.fromisoformat(frames[0]['timestamp'])).total_seconds()
    result = dict(source=str(Path(path).resolve()), frames=len(frames),
                  first_timestamp=frames[0]['timestamp'], last_timestamp=frames[-1]['timestamp'],
                  duration_seconds=duration, frame_rate=(len(frames)-1)/duration if duration else None,
                  rejected_lines=rejected, crc_errors_end=frames[-1].get('crc_errors'),
                  dropped_end=frames[-1].get('dropped'), hardware_touch_verified=False)
    for name in ('key_device', 'slider_device'):
        devices = [frame[name] for frame in frames]
        ready = [device for device in devices if device['online'] and device['configured']]
        errors = Counter(device['error'] for device in devices)
        error_episodes = sum(device['error'] != 0 and (i == 0 or device['error'] != devices[i-1]['error'])
                             for i, device in enumerate(devices))
        channels = []
        for channel in range(16):
            values = {}
            for field in ('signals', 'references', 'deltas'):
                # Count only the channel carried in this UART frame, avoiding
                # repeated cache values. Older TB1 frames carry every channel.
                samples = [device[field][channel] for device in ready
                           if device.get('raw_valid') and device[field][channel] is not None
                           and device.get('diagnostic_channel') in (None, channel)]
                values[field] = dict(samples=len(samples), minimum=min(samples),
                                     median=statistics.median(samples), maximum=max(samples)) if samples else None
            channels.append(values)
        result[name] = dict(ready_frames=len(ready), total_frames=len(devices),
                            error_frames=dict(errors), error_episodes=error_episodes,
                            any_key_frames=sum(bool(device['keys']) for device in ready),
                            any_key_fraction=(sum(bool(device['keys']) for device in ready)/len(ready)) if ready else None,
                            all_keys_frames=sum(device['keys'] == 0xffff for device in ready),
                            slider_detect_frames=sum(device['slider_detect'] for device in ready),
                            key_masks_most_common=Counter(device['keys'] for device in ready).most_common(8),
                            channels=channels, last={key:devices[-1].get(key) for key in
                            ('online', 'configured', 'error', 'i2c_address', 'chip_id', 'version', 'general', 'keys')})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = summarize(args.capture)
    text = json.dumps(result, ensure_ascii=False, indent=2)+'\n'
    if args.output:
        args.output.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
