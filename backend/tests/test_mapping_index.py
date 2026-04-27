import pytest

from app.models.card import LocalCardFile, TTSCardImage
from app.services import mapping_index


class FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return FakeScalars(self._items)


class FakeDb:
    def __init__(self):
        self.calls = 0

    async def execute(self, _query):
        self.calls += 1
        if self.calls == 1:
            return FakeResult([LocalCardFile(arkhamdb_id="01001", face="a", relative_path="01001_a.card")])
        return FakeResult([
            TTSCardImage(
                id=15405,
                arkhamdb_id="99999",
                source="英文",
                relative_json_path="Wrong/Card.json",
                card_id=999,
                face_url="wrong",
            ),
            TTSCardImage(
                id=22001,
                arkhamdb_id="01001",
                source="英文",
                relative_json_path="Core/RolandBanks.json",
                card_id=1001,
                face_url="right",
            ),
        ])


@pytest.mark.asyncio
async def test_resolve_mapping_prefers_stable_lookup_id_when_tts_id_drifted(monkeypatch):
    """映射索引不能依赖数据库自增 tts_id，否则迁移服务器后会指向错误卡图。"""
    monkeypatch.setattr(mapping_index, "load_mapping_index", lambda: {
        "version": 1,
        "cards": {
            "01001": {
                "faces": {
                    "a": {
                        "英文": {
                            "tts_id": 15405,
                            "tts_side": "front",
                            "tts_lookup_id": "01001",
                        }
                    }
                }
            }
        },
    })

    resolved = await mapping_index.resolve_card_image_mappings(FakeDb(), "01001")

    english = next(item for item in resolved if item["source"] == "英文")
    assert english["tts_id"] == 22001
    assert english["relative_json_path"] == "Core/RolandBanks.json"
    assert english["status"] == "已绑定"
