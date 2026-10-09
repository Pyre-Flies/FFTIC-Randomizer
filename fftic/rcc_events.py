"""RCC event changes on Enhanced bytecode, using verified instruction lengths.

Operand metadata is adapted from Rick/Gibbed's ScriptFormats, zlib licensed;
see data/GIBBED-LICENSE.txt. Original game scripts are extracted locally and
kept outside the source distribution. No disc-relative addresses are used.
"""
import hashlib
import json
from pathlib import Path
import struct


LENGTHS = {int(k):v for k,v in json.loads((Path(__file__).with_name('data')/'gibbed-opcode-lengths.json').read_text(encoding='utf-8')).items()}


def instructions(data,mode='enhanced'):
    """Decode executable instructions, preserving opaque padding after ends.

    Some original unused scripts retain a terminated stub followed by older
    data. Reject undecodable live code; preserve that unreachable tail.
    """
    offset,ended = 0,False
    while offset<len(data):
        opcode = data[offset]
        size = LENGTHS.get(opcode,{}).get(mode,-1)
        if size<0 or offset+size+1>len(data):
            if ended:
                return
            raise ValueError(f'Undecodable {mode} event instruction at0x{offset:X}:0x{opcode:02X}')
        yield offset,opcode,data[offset:offset+size+1]
        ended |= opcode in (0xDB,0xE3)
        offset += size+1


def prepare_event_inputs(game_dir,project_root):
    from .preview import locate_cli,run_cli
    source = Path(game_dir)/'data/enhanced/0005.pac'
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    cache = Path(project_root)/'research/rcc-events'/digest[:16]
    receipt = cache/'inputs.json'
    cache.mkdir(parents=True,exist_ok=True)
    if receipt.exists():
        record = json.loads(receipt.read_text(encoding='utf-8'))
        for name,expected in record['files_sha256'].items():
            if hashlib.sha256((cache/name).read_bytes()).hexdigest()!=expected:
                raise ValueError('Event input cache changed; re-extract the affected cache')
    else:
        run_cli(locate_cli(project_root),['unpack-all','-i',source,'-o',cache,'-g','fft'],cache/'extract.log')
        files = sorted((cache/'script/enhanced').glob('*.e'))
        if len(files)!=560 or not (cache/'script/enhanced/event300.e').exists():
            raise ValueError('Verified Enhanced event-script inventory changed')
        record = dict(archive_sha256={source.name:digest},
                      files_sha256={p.relative_to(cache).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                      opcode_source='gibbed/Gibbed.IvaliceChronicles@8f200e2902dab52dd36b5933df456ebb57173658')
        receipt.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    assets = {name:(cache/name).read_bytes() for name in record['files_sha256']}
    return assets,record


def ending_script(original,delita_id):
    """Splice RCC's fight reveal after Delita's flower-scene speech.

    Enhanced retains the same sequence but expands message operands. The
    cut point is the wait immediately before its change-dialog instruction.
    Both sides of that boundary are decoded, and the scene's animations and
    unit IDs are verified instead of assuming the PS1 byte offset survives.
    """
    decoded = list(instructions(original))
    boundaries = {offset:(op,raw) for offset,op,raw in decoded}
    cut = 0x1BC
    if boundaries.get(cut)!=(0xE5,b'\xe5\x01\x00') or boundaries.get(cut+3,(None,))[0]!=0x51:
        raise ValueError('Enhanced ending flower-scene boundary changed')
    if boundaries.get(0x1A0)!=(0x11,bytes((0x11,delita_id,0,0x62,2,0))):
        raise ValueError('Enhanced ending Delita animation anchor changed')
    ramza = 3
    reveal = bytes((
        0xE5,1,0, 0x5F,ramza,0,6,6,0,2, 0x45,ramza,0,0,
        0x48, 0x21,0x6A,0, 0x98,ramza,0,
        0x11,ramza,0,0x2C,0,0, 0x44,ramza,0, 0xF1,30,0,
        0x11,delita_id,0,1,0,0, 0xF1,30,0,
        0x53,ramza,0,4,1,0,0,0,
        0x76,0,1,12,64,0,4, 0xE5,0x36,0, 0x78,15,90,
        0xE5,0x38,0, 0x77, 0xE5,0x36,0, 0xDB))
    result = original[:cut]+reveal
    if list(instructions(result))[-1][1]!=0xDB:
        raise ValueError('RCC ending reveal did not decode through its end')
    return result


def auto_mash(data):
    changed = bytearray(data)
    messages = 0
    for offset,opcode,raw in instructions(data):
        if opcode==0x10 and raw[2]&0x70:
            changed[offset+2] &= 0x8F
            messages += 1
    return bytes(changed),messages


def progression_scripts(assets):
    """Port RCC's eight explicit story-variable changes and Murond script.

    Enhanced replaces several old function6 tails with its E9 transition
    instruction. Keep each native scene through that boundary, then execute
    RCC's own progress variables. Murond uses the source's shortened scene,
    with its two retained speeches mapped to verified Enhanced message IDs.
    """
    results,audit = {},[]
    stages = {290:42,303:54,311:55,312:55,313:56,317:57,321:58}
    for event,stage in stages.items():
        name = f'script/enhanced/event{event:03}.e'
        original = assets[name]
        decoded = list(instructions(original))
        end = next(offset for offset,op,raw in decoded if op in (0xDB,0xE3))
        live = [(offset,op,raw) for offset,op,raw in decoded if offset<end]
        candidates = [offset for offset,op,raw in live if op==0xBE and raw==b'\xbe\x55\x00']
        if candidates:
            cut = candidates[-1]
        else:
            transitions = [offset for offset,op,raw in live if op==0xE9]
            # The modern 312 scene only sets its shared flag125 at its end.
            cut = transitions[-1] if transitions else end
        script = (b'\xbe\x6e\x00\xb0\x6e\x00\x2a\x00\xb0\x31\x00\x1e\x00' if event==290 else
                  b'\xbe\x55\x00\xbe\x6e\x00\xb0\x6e\x00'+struct.pack('<H',stage))+b'\xdb'
        results[name] = original[:cut]+script
        list(instructions(results[name]))
        audit.append(dict(event=event,boundary=f'0x{cut:X}',story_progress=stage))
    name = 'script/enhanced/event309.e'
    original = assets[name]
    spoken = [raw for _,op,raw in instructions(original) if op==0x10]
    if len(spoken)!=5 or int.from_bytes(spoken[0][3:7],'little')!=301508 or int.from_bytes(spoken[-1][3:7],'little')!=301512:
        raise ValueError('Enhanced Murond dialogue identity anchors changed')
    source = bytes.fromhex(json.loads((Path(__file__).with_name('data')/'rcc-murond-script.json').read_text(encoding='utf-8'))['classic_bytecode_hex'])
    chunks = []
    for _,op,raw in instructions(source,'classic'):
        if op==0x10:
            message = int.from_bytes(raw[3:5],'little')
            if message not in (1,5) or raw[5]!=3:
                raise ValueError('RCC Murond speech ownership changed')
            raw = raw[:3]+struct.pack('<I',{1:301508,5:301512}[message])+raw[5:]+b'\x00'
        chunks.append(raw)
    results[name] = b''.join(chunks)
    if list(instructions(results[name]))[-1][1]!=0xDB:
        raise ValueError('Adapted RCC Murond script did not reach its end')
    audit.append(dict(event=309,source='RCC custom Murond scene',story_progress=55,
                      enhanced_message_ids=[301508,301512]))
    return results,audit


def apply_event_assets(before,result,game_dir,project_root,flags):
    assets,inputs = prepare_event_inputs(game_dir,project_root)
    audit = dict(inputs=inputs,ending_reveal=False,automatic_dialogue_messages=0,changed_assets={})
    edited,progress = progression_scripts(assets)
    audit['overworld_scripts'] = progress
    if 'z' in flags:
        name = 'script/enhanced/event300.e'
        unit = result['_RCCUnitContext'][(307,0)]
        edited[name] = ending_script(assets[name],unit['UnitId'])
        audit['ending_reveal'] = True
        # Conditional set37 runs setup script115, not script37. Source
        # restore_warjilis replaces precisely its nine-byte black background.
        name = 'script/enhanced/event115.e'
        original = assets[name]
        if list(instructions(original))[0]!=(0,0x2E,bytes.fromhex('2E0000000000000000')):
            raise ValueError('END background palette instruction changed')
        edited[name] = b'\xF2'*9+original[9:]
        audit['warjilis_background_script'] = 115
    if 'o' in flags:
        for name,original in assets.items():
            changed,count = auto_mash(edited.get(name,original))
            audit['automatic_dialogue_messages'] += count
            if changed!=original:
                edited[name] = changed
    for name,data in edited.items():
        result.setdefault('_RCCEventAssets',{})[name] = data
        audit['changed_assets'][name] = dict(original_sha256=hashlib.sha256(assets[name]).hexdigest(),
                                          generated_sha256=hashlib.sha256(data).hexdigest())
    result['_RCCEventAudit'] = audit
    return audit
