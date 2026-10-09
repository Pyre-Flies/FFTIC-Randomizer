"""Import authored RCC conditional deltas; do not bundle raw game tables."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fftic.rcc_conditionals import decode_table


def main():
    inputs = (
        ('battle',Path('I:/rumble_chaos_crashdown/tables/conditionals.dat'),
         ROOT/'research/rcc-script-assets/fftpack/overlay/event_attack_out.en.bin',0x14938),
        ('world',Path('I:/rumble_chaos_crashdown/tables/world_conditionals.dat'),
         ROOT/'research/rcc-script-assets/fftpack/world_wldcore_bin.en.bin',0x30234))
    bundle = dict(source_commit='ce9aafa1aaf7d05711cd33d8b49a062dc8a8a070',families={})
    for family,modified,original,offset in inputs:
        native_bytes = original.read_bytes()[offset:]
        target_bytes = modified.read_bytes()
        # Source world_conditionals.dat ends after the low byte of its final
        # ushort. Its write leaves the original next/high byte in place.
        if len(target_bytes)%2:
            target_bytes += native_bytes[len(target_bytes):len(target_bytes)+1]
        target = decode_table(target_bytes,family)
        baseline = decode_table(native_bytes,family)
        changed = {key:dict(before=baseline[key],after=target[key]) for key in baseline if baseline[key]!=target[key]}
        bundle['families'][family] = dict(source_sha256=hashlib.sha256(modified.read_bytes()).hexdigest(),
            baseline_asset_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),baseline_table_offset=offset,
            changed_groups=changed)
        print(family,dict(changed_groups=len(changed),before_clauses=sum(len(v['before']) for v in changed.values()),
                          after_clauses=sum(len(v['after']) for v in changed.values()),
                          max_clauses=max(len(v) for v in target.values()),changed_keys=sorted(changed)))
    (ROOT/'fftic/data/rcc-conditionals.json').write_text(json.dumps(bundle,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__': main()
