"""Desktop/CLI entry point for source and bundled executable launches."""
import argparse
import json
from pathlib import Path
import sys

from fftic.game import read_game
from fftic.package import create_seed, write_json
from fftic.randomize import DEFAULT_FLAGS, FLAGS
from fftic.runtime import workspace_root,default_game_dir,default_output_dir
from fftic import VERSION

ROOT = workspace_root()


def _emit(message, error=False):
    stream = sys.stderr if error else sys.stdout
    if stream is not None:
        print(message, file=stream)


def main(argv=None):
    parser = argparse.ArgumentParser(description="FFTIC Enhanced seeded table randomizer")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="Read-only executable layout and hash report")
    inspect.add_argument("--game-dir", type=Path, default=default_game_dir(ROOT))
    inspect.add_argument("--report", type=Path)
    inspect.add_argument("--result-file", type=Path, help=argparse.SUPPRESS)
    build = sub.add_parser("generate", help="Generate a Reloaded-II mod outside the game data folders",
                           epilog="Job skillsets use s for ordinary and unique jobs. Encounter units use u; formation changes use f.")
    build.add_argument("--game-dir", type=Path, default=default_game_dir(ROOT))
    build.add_argument("--output", type=Path, default=default_output_dir(ROOT))
    build.add_argument("--seed", required=True)
    build.add_argument("--flags", default=DEFAULT_FLAGS, help='; '.join(f'{f}: {name}' for f,name in FLAGS.items()))
    build.add_argument("--ability-mode", type=lambda value: 'shuffle' if value=='rcc' else value,
                       choices=("shuffle","full"), default="shuffle",
                       help="shuffle: exchange existing lists; full: rebuild complete lists")
    build.add_argument("--skill-degree", type=float, default=1.0,
                       help="0 to 1; scales shuffle probabilities or selects the fraction of jobs to rebuild")
    build.add_argument("--min-actions", type=int, default=6,
                       help="Full mode only: minimum human actions, 1 to 16, default 6")
    build.add_argument("--max-actions", type=int, default=12,
                       help="Full mode only: maximum human actions, 1 to 16, default 12")
    build.add_argument("--passives-per-type", type=int, choices=(1,2), default=1,
                       help="Full mode only: reactions, supports and movements per human job")
    build.add_argument("--spread", type=float, default=0.25, help="0 to 1; stat randomness, default 0.25")
    build.add_argument("--chaos",type=float,default=1.0,help="Difficulty multiplier, 0 to 10, default 1")
    build.add_argument('--fiesta',action='store_true',help='Optional Job Fiesta mode')
    build.add_argument('--easymodo',action='store_true',help='Optional level-one enemy mode')
    build.add_argument('--result-file',type=Path,help=argparse.SUPPRESS)
    sub.add_parser("gui", help="Open the desktop generator")
    args = parser.parse_args((sys.argv[1:] if argv is None else argv) or ['gui'])
    result = dict(version=VERSION)
    try:
        if args.command == "gui":
            from fftic.gui import run
            run(ROOT)
        elif args.command == "inspect":
            _, report = read_game(args.game_dir, require_supported=False)
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                write_json(args.report, report)
            result.update(result='passed',build=report)
            _emit(json.dumps(report, indent=2))
        else:
            destination, manifest = create_seed(
                game_dir=args.game_dir, output_root=args.output, seed=args.seed,
                flags=args.flags, spread=args.spread, project_root=ROOT,
                skill_degree=args.skill_degree, chaos=args.chaos,
                ability_mode='rcc' if args.ability_mode=='shuffle' else 'full', min_actions=args.min_actions,
                max_actions=args.max_actions, passives_per_type=args.passives_per_type,
                fiesta=args.fiesta,easymodo=args.easymodo)
            result.update(result='passed',seed=args.seed,output=str(destination),
                          manifest=str(destination/'manifest.json'),property_changes=manifest['property_changes'])
            _emit(f"Generated {manifest['property_changes']} property changes.")
            _emit(f"Mod: {destination / 'randomizer-mod.zip'}")
            _emit(f"Report: {destination / 'spoiler.txt'}")
            _emit("Offline checks passed. In-game validation is still required.")
        if getattr(args,'result_file',None):
            args.result_file.parent.mkdir(parents=True,exist_ok=True)
            write_json(args.result_file,result)
        return 0
    except (OSError, ValueError) as error:
        _emit(f"Error: {error}", error=True)
        if getattr(args,'result_file',None):
            args.result_file.parent.mkdir(parents=True,exist_ok=True)
            write_json(args.result_file,dict(result='failed',version=VERSION,error=str(error)))
        return 1


if __name__ == "__main__":
    sys.exit(main())
