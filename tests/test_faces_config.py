import sys
import types

from flickr_find_me.faces import FaceEngine


def test_model_root_from_env(monkeypatch):
    seen = {}

    class FakeFA:
        def __init__(self, name, root="~/.insightface", **kw):
            seen["root"] = root

        def prepare(self, **kw):
            pass

    mod = types.ModuleType("insightface.app")
    mod.FaceAnalysis = FakeFA
    monkeypatch.setitem(sys.modules, "insightface.app", mod)
    monkeypatch.setenv("FLICKR_FIND_ME_MODELS", "/models")
    FaceEngine()
    assert seen["root"] == "/models"
