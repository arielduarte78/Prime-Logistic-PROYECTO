import main

SHA = "0123456789abcdef0123456789abcdef01234567"
SHA2 = "fedcba9876543210fedcba9876543210fedcba98"


def _repo(tmp_path, head, refs=None, packed=None):
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text(head)
    for ref, sha in (refs or {}).items():
        f = git / ref
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(sha + "\n")
    if packed:
        (git / "packed-refs").write_text("# pack-refs\n" + packed)
    return tmp_path


def test_lee_el_commit_de_una_rama(tmp_path, monkeypatch):
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    raiz = _repo(tmp_path, "ref: refs/heads/main\n", refs={"refs/heads/main": SHA})
    assert main._leer_commit(raiz) == SHA


def test_lee_el_commit_desde_packed_refs(tmp_path, monkeypatch):
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    raiz = _repo(tmp_path, "ref: refs/heads/main\n", packed=f"{SHA2} refs/heads/otra\n{SHA} refs/heads/main\n")
    assert main._leer_commit(raiz) == SHA


def test_head_desacoplado(tmp_path, monkeypatch):
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    assert main._leer_commit(_repo(tmp_path, SHA + "\n")) == SHA


def test_variable_de_entorno_tiene_prioridad(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_COMMIT", SHA2)
    raiz = _repo(tmp_path, "ref: refs/heads/main\n", refs={"refs/heads/main": SHA})
    assert main._leer_commit(raiz) == SHA2


def test_sin_git_devuelve_desconocido(tmp_path, monkeypatch):
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    assert main._leer_commit(tmp_path) == "desconocido"


def test_health_incluye_el_commit(test_client, monkeypatch):
    monkeypatch.setattr(main, "COMMIT", SHA)
    assert test_client.get("/health").json()["commit"] == SHA
