# Choose your settings

Start with the defaults for the established shuffle rules. Choose **Full
redistribution** if you want jobs to receive completely rebuilt ability lists.
Hover over any setting in the app, or focus it with Tab, for a short explanation.

## Ability mode

| | Shuffle | Full redistribution |
| --- | --- | --- |
| Job abilities | Exchanges abilities between existing lists. Some familiar abilities remain. | Deals new lists from the available pools. |
| Special command menus | Items, Aim, Geomancy, Jump, Iaido, Throw, and Math keep their command structures. | Compatible command-menu profiles can move between humanoid jobs. |
| Reaction, support, and movement | Counts vary; some jobs can lack a type. | One of each per humanoid job by default; two of each is optional. |
| Monster abilities | Uses the established monster mutation and Beastmaster rules. | Gives monsters four compatible actions, including their hidden fourth slot. |
| Reuse | Shared skills and special exceptions follow the original rules. | Separate humanoid and monster pools are consumed before refilling. Naturally shared skills can belong to both. |

Both modes include ordinary and unique humanoid jobs under **Job skillsets
(ordinary and unique)**. A job's changes apply wherever that job appears,
including the opening battle. Jobs sharing a command list share its new abilities.
Skills still follow equipment, inventory, terrain, and learned-spell requirements.
Redistribution does not automatically unlock all jobs or skills.

## How much changes?

| Setting | Meaning |
| --- | --- |
| **Stat randomness** | How far randomized numbers can move from their original values. Default **25%**; higher values allow larger changes. Applies to enabled numerical settings. |
| **Ability degree** | Default **100%**. In Shuffle, lowers or raises the chance of skillset changes. In Full redistribution, selects what fraction of eligible enabled skillsets is rebuilt. |
| **Chaos multiplier** | Scales progression and difficulty boosts in enabled settings. Default **1.0**. Higher values can make later enemies much harder; **0** removes these boosts while retaining randomization. |
| **Minimum / Maximum actions** | Full redistribution only. Default **6–12** actions per humanoid job, subject to compatible command menus. The minimum cannot exceed the maximum. Monsters keep four skills, and a special surprise can add an extra action. |
| **Each passive type** | Full redistribution only. Choose **1** or **2** reaction abilities, support abilities, and movement abilities per humanoid job. Monsters do not receive these slots. |

## Randomize checkboxes

The first fourteen options below are enabled by default. The two testing
conveniences are off by default.

| Option | What changes |
| --- | --- |
| **Job requirements and job-level JP** | Job unlock requirements and JP thresholds for job levels. |
| **Job innate abilities, statuses, elements and equipment permissions** | Built-in job traits, elemental properties, statuses, and allowed equipment. |
| **Job skillsets (ordinary and unique)** | Actions, reactions, supports, and movement skills in humanoid job lists, including unique character and enemy jobs. |
| **Ability CT, MP, power, range and area** | How abilities behave: charge time, MP cost, power, range, and effect area. |
| **Ability and weapon status effects** | Statuses inflicted or granted by abilities and weapons. |
| **Human job stats and skill JP costs** | Humanoid job stats and growth, learning costs, and eligible learning chances. |
| **Monster skills and stats** | Monster and boss skillsets, stats, and built-in traits. |
| **Enemy and ally encounter units** | Battle units' jobs or species, loadouts, equipment, levels, and related traits. |
| **Special surprises** | Special units, names, weather, and later encounter surprises. Can change maps when formations are also enabled. |
| **Enemy and ally formations** | Starting positions and player deployment areas, with terrain checks, plus random-encounter group changes. |
| **Trophies, poaches and move-find items** | Battle rewards, poaching results, and Treasure Hunter finds, including rare alternatives. |
| **Prices, shop timing and rarity** | Item prices and when equipment becomes available. |
| **Equipment, consumables and equip bonuses** | Weapon, armor, shield, accessory, consumable, and equipment-bonus properties. |
| **Battle music** | Eligible battle music, with tracks needed by particular scenes preserved. |
| **Automatically advance event dialogue** | Advances event dialogue automatically, useful when replaying scenes. |
| **Optional six free actions for testing** | Makes six selected actions free to learn, free to cast, and instant wherever they are assigned. Does not unlock every skill or job. |

Shared job, ability, and item changes also affect enemies that use those same
definitions. Turning off a checkbox skips that category of randomization;
built-in progression and convenience changes are part of the generated mod.

## Optional play styles

**Job Fiesta** starts Ramza and the initial party as Mimes, clears their secondary
and passive loadouts, and gives early enemies Stone Guns. It is intended as a
new-game challenge and is off by default.

**Easy Mode** sets enemies to level 1. Enemies using generic sprites also receive
Tietra's job; special character sprites keep their jobs. It is applied after other
randomization settings and is off by default.

## Credits

The Shuffle rules and built-in changes are adapted from
[Rumble Chaos Crashdown by abyssonym](https://github.com/abyssonym/rumble_chaos_crashdown).
The Windows app bundles [FF16Tools by Nenkai](https://github.com/Nenkai/FF16Tools)
for archive extraction and table conversion. The game loads the generated mod
through [Nenkai's FFTIC Mod Loader](https://github.com/Nenkai/fftivc.utility.modloader)
and [Reloaded-II](https://github.com/Reloaded-Project/Reloaded-II).

For installation and launching, see [Install and play](INSTALL.md).
