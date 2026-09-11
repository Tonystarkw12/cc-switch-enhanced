"""`ccse completion` — emit static shell completion scripts.

stdlib-only by project principle (no argcomplete): a hand-written zsh script
using _arguments, and a bash -W wordlist. Regenerate per release only when the
subcommand set changes.
"""
from __future__ import annotations

import sys

_SUBCMDS = ("list show profiles apply diff genprofile undo history snapshots "
            "verify rewrite rules penv current completion")

_ZSH = f"""#compdef ccse
# ccse zsh completion — regenerate: ccse completion zsh
_ccse() {{
  local -a cmds
  cmds=({_SUBCMDS})
  _arguments -C \\
    '--model[switch every agent primary model slot]:name:' \\
    '--base-url[switch every base_url]:url:' \\
    '--api-key[switch every api_key]:key:' \\
    '--only[adapters to include]:ids:' \\
    '--exclude[adapters to exclude]:ids:' \\
    '--dry[preview only, write nothing]' \\
    '--no-backup[skip pre-write snapshot]' \\
    '--no-keep-prefix[set model name verbatim]' \\
    '--version[print version]' \\
    '(-v --verbose)'{{-v,--verbose}}'[show what apply touched]' \\
    '(-q --quiet)'{{-q,--quiet}}'[suppress hints and notes]' \\
    '1:cmd:($cmds)' \\
    '*::arg:->args'
  case $words[1] in
    (apply|diff)
      _arguments '--model[name]:name:' '--base-url[url]:url:' \\
        '--api-key[key]:key:' '--no-backup' '--no-keep-prefix' \\
        '--only[ids]:ids:' '--exclude[ids]:ids:' '1:profile:( )' ;;
    (penv)
      _arguments '--base-url[url]:url:' '--api-key[key]:key:' \\
        '--model[name]:name:' '--prefix[prefix]:prefix:' '--file[env file]:file:' \\
        '--rm[remove provider]' '--dry' '1:dir/name:_path_files -/' '2:name:( )' ;;
    (rules)
      _arguments '--apply[inject snippet]' '--rm[remove block]' \\
        '--snippet[file]:file:_files' '--only[ids]:ids:' '--exclude[ids]:ids:' '--dry' ;;
    (verify) _arguments '--only[ids]:ids:' '--exclude[ids]:ids:' '--timeout[seconds]:seconds:' ;;
    (undo) '1:stamp:( )' ;;
  esac
}}
_ccse "$@"
"""

_BASH = f"""# ccse bash completion — regenerate: ccse completion bash
_ccse_completion() {{
  local cur="${{COMP_WORDS[COMP_CWORD]}}" prev="${{COMP_WORDS[COMP_CWORD-1]}}"
  local cmds="{_SUBCMDS}"
  local flags="--model --base-url --api-key --only --exclude --dry --no-backup --no-keep-prefix --version --verbose --quiet"
  if [[ $COMP_CWORD -eq 1 ]]; then
    COMPREPLY=($(compgen -W "$cmds $flags" -- "$cur"))
    return 0
  fi
  case "${{COMP_WORDS[1]}}" in
    apply|diff) COMPREPLY=($(compgen -W "--model --base-url --api-key --no-backup --no-keep-prefix --only --exclude" -- "$cur")) ;;
    penv) COMPREPLY=($(compgen -W "--base-url --api-key --model --prefix --file --rm --dry" -- "$cur")) ;;
    rules) COMPREPLY=($(compgen -W "--apply --rm --snippet --only --exclude --dry" -- "$cur")) ;;
    verify|show|list) COMPREPLY=($(compgen -W "--only --exclude --json" -- "$cur")) ;;
    *) COMPREPLY=($(compgen -W "--json --only --exclude" -- "$cur")) ;;
  esac
  return 0
}}
complete -F _ccse_completion ccse
"""


def run(shell: str | None) -> int:
    shell = (shell or "zsh").lower()
    if shell == "zsh":
        print(_ZSH, end="")
        print("# install: ccse completion zsh > ~/.zfunc/_ccse  (+ fpath ~/.zfunc before compinit)",
              file=sys.stderr)
    elif shell == "bash":
        print(_BASH, end="")
        print("# install: ccse completion bash > ~/.local/share/bash-completion/completions/ccse",
              file=sys.stderr)
    else:
        from . import config
        config.die(f"unknown shell {shell!r} (zsh | bash)")
    return 0
