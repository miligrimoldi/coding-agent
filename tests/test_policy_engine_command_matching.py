"""
PolicyEngine._contains_any (usado para commands.deny y
commands.require_approval) comparaba el string crudo del comando contra
los patrones configurados. Un comando con espacios/tabs de más (ej.
"git  push" con doble espacio) evadía por completo una regla "git
push", pese a ejecutarse exactamente igual una vez que shlex/el shell
colapsan los espacios. Se corrigió normalizando espacios en blanco
antes de comparar.
"""

import pytest

from policy_engine import PolicyEngine, PolicyViolation


def _engine():
    return PolicyEngine(config={
        "commands": {
            "deny": ["rm -rf", "git push"],
            "require_approval": ["npm install"],
        },
    })


@pytest.mark.parametrize(
    "command",
    [
        "git push",
        "git  push",
        "git   push",
        "git\tpush",
        "rm -rf .",
        "rm  -rf .",
        "rm -rf   /tmp/x",
    ],
)
def test_denied_command_blocked_despite_extra_whitespace(command):
    engine = _engine()

    with pytest.raises(PolicyViolation):
        engine._validate_command(command)


@pytest.mark.parametrize(
    "command",
    ["npm run build", "npm run test", "git status"],
)
def test_unrelated_commands_not_blocked(command):
    engine = _engine()

    # No debe levantar excepción.
    engine._validate_command(command)


def test_require_approval_also_matches_despite_extra_whitespace():
    engine = _engine()

    assert engine._contains_any(
        "npm  install", ["npm install"]
    )
    assert engine._contains_any(
        "npm install", ["npm install"]
    )
    assert not engine._contains_any(
        "npm run build", ["npm install"]
    )
