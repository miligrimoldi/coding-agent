"""
PolicyEngine._matches_path debía anclar patrones sin comodines
explícitos (".env", "secrets/**", "package-lock.json") solo a la raíz
del workspace -- un ".env" en una subcarpeta, o un "secrets/" anidado,
no quedaban bloqueados. Se corrigió para que se comporten como en un
.gitignore: bloquean en cualquier profundidad del árbol.
"""

from policy_engine import PolicyEngine


def _engine():
    # No hace falta un YAML real -- _matches_path no lee self.config.
    return PolicyEngine(config={})


def test_bare_filename_pattern_matches_at_any_depth():
    engine = _engine()

    assert engine._matches_path(".env", ".env")
    assert engine._matches_path("src/.env", ".env")
    assert engine._matches_path("config/nested/.env", ".env")


def test_bare_filename_pattern_does_not_false_positive():
    engine = _engine()

    assert not engine._matches_path("src/environment.ts", ".env")
    assert not engine._matches_path("src/dotenv.ts", ".env")


def test_directory_glob_pattern_matches_at_any_depth():
    engine = _engine()

    assert engine._matches_path("secrets/api-key.txt", "secrets/**")
    assert engine._matches_path("src/secrets/api-key.txt", "secrets/**")
    assert engine._matches_path("config/secrets/db.txt", "secrets/**")

    assert engine._matches_path(
        ".github/workflows/ci.yml", ".github/**"
    )
    assert engine._matches_path(
        "apps/api/.github/workflows/ci.yml", ".github/**"
    )


def test_directory_glob_pattern_does_not_false_positive():
    engine = _engine()

    # "mysecrets" no es el directorio "secrets".
    assert not engine._matches_path("mysecrets/file.txt", "secrets/**")


def test_double_star_prefix_pattern_still_works():
    engine = _engine()

    assert engine._matches_path("cert.pem", "**/*.pem")
    assert engine._matches_path("src/cert.pem", "**/*.pem")
    assert engine._matches_path("certs/nested/cert.pem", "**/*.pem")


def test_lockfile_patterns_match_at_any_depth():
    engine = _engine()

    assert engine._matches_path(
        "package-lock.json", "package-lock.json"
    )
    assert engine._matches_path(
        "apps/api/package-lock.json", "package-lock.json"
    )


def test_explicit_nested_pattern_stays_anchored_to_root():
    engine = _engine()

    assert engine._matches_path("config/prod.yaml", "config/prod.yaml")
    assert not engine._matches_path(
        "other/config/prod.yaml", "config/prod.yaml"
    )
