# MotherDuck stub — fetch_prod_state imports this module unconditionally but
# only calls it in onelake mode. MotherDuck mode uses artifact mode exclusively.
# The full public surface is declared so that test patch() calls against
# generate_ci_notebook (Fabric bundle) still find their targets when this
# module is resolved first due to sys.path ordering.
_MSG = (
    "Fabric transport is not available in MotherDuck mode. "
    "Set prod_manifest_source.mode to 'artifact' in ci-config.yml."
)


def get_token(audience: str) -> str:
    raise RuntimeError(_MSG)


def request(method: str, path: str, body=None, audience: str = "fabric", retries: int = 3) -> dict:
    raise RuntimeError(_MSG)


def request_long_running(method: str, path: str, body, audience: str = "fabric", timeout_s: int = 120, poll_interval_s: int = 5) -> dict:
    raise RuntimeError(_MSG)


def dfs_request(method: str, url: str, audience: str = "storage", data=None, params=None) -> None:
    raise RuntimeError(_MSG)
