"""Verified native equivalent of RCC's initial Ramza Mime job constants.

Enhanced unifies the original job assignments in its compact actor spawn
initializer. Change only the Ramza branch's job store; keep graphic1, male
flags, stat/equipment profiles, name identity and every other use of r13=1.
"""
import hashlib
from pathlib import Path

from .game import ENHANCED_SHA256
from .rcc_qol import raw_from_rva,_patch


RAMZA_JOB_STORE = 0x275392
ORIGINAL_STORE = bytes.fromhex('44 88 69 02')
MIME_STORE = bytes.fromhex('C6 41 02 5D')
GUARDS = (
    ('native spawn type branches and original Ramza store',0x275310,0x27539E,
     '8fd0ff368bf905309de423d770721ef62ac690d04872f267a742829177f85187'),
    ('compact actor allocator calls spawn initializer',0x27528C,0x2752DD,
     '69281eda1db9267999bc02298a222c7dc5cd1c9b8702fd321ef749f303f88fda'),
    ('newgame reset allocates type2 Ramza only in mode0',0x284500,0x28454A,
     '37b0522f1d9b1778d9a06856cef5eb59a55105b4dfea21540edcd22d612fdb9c'),
    ('current job propagates from compact actor',0x284AE4,0x284B1E,
     '851be7622d91eb7ead345d0f9e08db51e7e93156916ff606c5e41cec7851688b'),
    ('modern newgame selects mode0',0x37E033,0x37E03A,
     'af0b63647ea2ded5a924a163091c0752fbba0b2cb859679c37d29bca2df8fc6e'),
)


def fiesta_native_patches(data):
    if hashlib.sha256(data).hexdigest()!=ENHANCED_SHA256:
        raise ValueError('Fiesta native initialization requires the verified Enhanced executable')
    for label,start,end,expected in GUARDS:
        raw = raw_from_rva(data,start,end-start)
        if hashlib.sha256(data[raw:raw+end-start]).hexdigest()!=expected:
            raise ValueError('Fiesta native caller/layout guard failed: '+label)
    return [_patch(data,'RCC Fiesta initial Ramza job Mime93',RAMZA_JOB_STORE,ORIGINAL_STORE,MIME_STORE)]


def apply_fiesta_native(before,result):
    directory = before.get('_RCCGameDirectory')
    if not directory: raise ValueError('Fiesta requires a verified game-directory input')
    data = (Path(directory)/'FFT_enhanced.exe').read_bytes()
    plans = fiesta_native_patches(data)
    existing = result.setdefault('_RCCNativeTablePatches',[])
    if any(plan['rva']==RAMZA_JOB_STORE for plan in existing):
        raise ValueError('Fiesta native initialization was already planned')
    existing.extend(plans)
    return dict(source='RCC4659-4662 initial Ramza job93',native_patch_count=1,
                initial_job=93,old_initial_job=1,job_store_rva='0x275392',
                source_assignment_adaptation='Enhanced compact job byte propagates into decoded actor job and expanded current job',
                native_call_chain=['0x37E033 mode0','0x37FF14','0x284500 mode0',
                                   '0x27528C type2','0x275310 Ramza branch'],
                guard='exact Enhanced executable SHA256, original instruction and five caller/layout byte ranges',
                preserved=['Ramza graphic1','male flags','generic/monster spawn branches',
                           'stats and equipment profiles','name identity','unrelated r13=1 uses'])
