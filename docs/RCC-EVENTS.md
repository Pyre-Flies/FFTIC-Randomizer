# Enhanced event bytecode and RCC story adapters

Original event scripts are read from data/enhanced/0005.pac into a hash-receipted
research cache. The supported archive contains560 Enhanced event*.e files.
Nothing is edited in the original archive. Generated replacements are ordinary
loader assets under FFTIVC/data/enhanced/script/enhanced.

Operand metadata is derived from Gibbed.IvaliceChronicles ScriptFormats commit
8f200e2902dab52dd36b5933df456ebb57173658. Its zlib license is retained in
fftic/data/GIBBED-LICENSE.txt. tools/import_gibbed_opcodes.py produces the
243-entry Classic/Enhanced operand-length JSON. Enhanced deltas include
DisplayMessage10 (+3), ChangeDialog51 (+2) and EB (+4). E6's variable operand
form is deliberately rejected rather than guessed. The decoder rejects unknown
or truncated live instructions. Some original unused terminated stubs contain
opaque older trailing data; those tails are preserved.

The native script loader at RVA2F3BC4..2F3D58 selects the Enhanced path string
at71E640 (Classic71E658), calculates event filenames and calls2F410B. This was
traced on the exact937233f7 executable; the old PS1 sector offsets are not
native file offsets.

## Default overworld scripts

rcc_events.progression_scripts ports the source's explicit variable tails for
events290,303,311,312,313,317,321. It preserves each modern scene through its
decoded final Zero85 or E9 transition boundary, then emits the source's progress
variables and EndDB. Event290 sets variable110 to42 and adds30 to variable49.
The other tails set110 to54,55,55,56,57,58 respectively after clearing85.

The source-authored shortened Murond scene for309 is bundled as885 Classic
bytecode bytes in rcc-murond-script.json. The source retains message1/5 spoken
by unit3. Enhanced original309 has five messages; its first/last IDs301508 and
301512 are anchored before conversion. The two source speeches are translated
to those IDs and Enhanced operand lengths, producing891 decoded bytes through
EndDB. Original game script contents are not part of the generator source ZIP.

Default world conditional changes are owned by rcc_conditionals.py and emitted
together with these scripts. See RCC-CONDITIONALS.md.

## z ending and restored encounters

Native event300's ending flower-scene cut is verified at0x1BC: WaitE5/1,
followed by ChangeDialog51. Delita's UnitId6 animation0x262 at0x1A0 is also
verified. The source reveal replaces the tail, retaining444 prefix bytes plus
71 authored bytes. It reveals Ramza UnitId3 at6,6 facing2, performs the source
animation/condition sequence and decodes through EndDB. Ending units, Encounter
299 and battle conditional144 are changed by their own source phases.

The restored Warjilis encounters dispatch DeepDungeon conditional set37.
That set runs setup script115 and winning script94. The source nine-byte black
background palette instruction at the beginning of event115 is verified as
2E0000000000000000, then replaced with nine F2 padding instructions. Event37
is a conditional-set ID here, not the setup-script filename.

## o dialogue advancement

The source auto_mash mask changes DisplayMessage flags byte2 with &=0x8F,
clearing only0x70. rcc_events.auto_mash applies that mask at decoded message
instructions, preserves every other byte, and is idempotent. It operates on
already-edited progression/ending assets so the phases compose. The audit
records changed message and asset counts plus original/generated hashes.

## Names and poach UI

The source-authored community name list is bundled separately. RCC's length
buckets, vowel trimming, consumed candidate selection and repeated-original
name transitions are retained. Enhanced generic name keys256..1023 (three
256-name pools) are changed in all seven CharaName language tables. IsGeneric
alone is insufficient: named recruits117/118/120/121/127 are preserved.

PoachItem language rows include fixed carcass buy/sell prices and descriptions
naming the original reward. finish_poach_ui runs after t/p/w. The original
96-row baseline is guarded: Cost=item.Price//2 and SellPrice=(Cost+1)//2.
Final prices follow the final reward and item prices. Changed rewards replace
the obsolete item-specific description with authored localized text. Sparse
Nex emission changes only Unknown2C,Cost,SellPrice,Unknown18.

## Evidence

tests/test_rcc_events.py compares the authored ending/progression/Murond source,
Enhanced operand conversion, rejected anchors, exact dialogue-byte preservation
and community-name source consumption. The final startup validation compares
every generated event asset in the actual loader-merged pack with the seed.
Neither decoder tests nor startup asset matching establish campaign completion.
