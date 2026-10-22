"""The live suite's cleanup must only touch rows of its own throwaway users."""

from tests.live.conftest import cleanup


class Recorder:
    """Records every query chain sent through the admin client."""

    def __init__(self):
        self.calls = []
        self.deleted_users = []
        self.auth = type("A", (), {"admin": self})()

    def delete_user(self, user_id):
        self.deleted_users.append(user_id)

    def table(self, name):
        chain = [("table", name)]
        self.calls.append(chain)

        class Q:
            def __getattr__(_, method):
                def step(*args):
                    chain.append((method, args))
                    return Q()

                return step

        return Q()


def test_cleanup_borra_solo_lo_de_sus_usuarios():
    """Revisión PR #5: una obra ajena llamada «[E2E] …» se conserva."""

    admin = Recorder()
    cleanup(admin, ["u-a", "u-b"])

    deletes = [c for c in admin.calls if ("delete", ()) in c]
    assert deletes, "la limpieza no borró nada"
    for chain in deletes:
        filtros = [args for method, args in chain if method == "eq"]
        assert filtros, f"borrado sin filtro: {chain}"
        assert all(
            col in ("creado_por", "user_id") and val in ("u-a", "u-b") for col, val in filtros
        )
        assert not any(method in ("like", "ilike") for method, _ in chain), chain
    assert admin.deleted_users == ["u-a", "u-b"]


def test_cleanup_sin_usuarios_no_borra_nada():
    admin = Recorder()
    cleanup(admin, [])
    assert admin.calls == [] and admin.deleted_users == []
