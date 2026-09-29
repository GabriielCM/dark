"""Fotos de referencia do Commons (fase B4): adaptador, etapa e img2img."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from PIL import Image, ImageOps

from mundoantigo.artifacts import ArtifactStore
from mundoantigo.errors import ProviderUnavailable
from mundoantigo.pipeline import Runner, Worker
from mundoantigo.providers import fake_registry
from mundoantigo.providers.image import FakeImage
from mundoantigo.providers.llm import FakeLLM
from mundoantigo.providers.references import CommonsReferences, FakeReferences
from mundoantigo.references.prepare import FILL, letterbox
from mundoantigo.references.ranking import TitleRanker
from mundoantigo.style.character import COMMERCIAL_REMBG_MODELS
from tests.fakes import responder

PAGE = {
    "pageid": 385176,
    "title": "File:Roma Appia Antica - mausoleo Cecilia Metella.jpg",
    "index": 1,
    "imageinfo": [
        {
            "url": "https://upload.wikimedia.org/a/ab/Mausoleo.jpg",
            "thumburl": "https://upload.wikimedia.org/thumb/a/ab/Mausoleo.jpg/1920px-Mausoleo.jpg",
            "width": 3000,
            "height": 2000,
            "mime": "image/jpeg",
            "extmetadata": {"LicenseShortName": {"value": "Public domain"}},
        }
    ],
}
SVG_PAGE = {
    "pageid": 2,
    "title": "File:Mapa.svg",
    "index": 2,
    "imageinfo": [{"mime": "image/svg+xml"}],
}


def _commons(recorder, handler) -> CommonsReferences:
    return CommonsReferences(costs=recorder, config={}, transport=httpx.MockTransport(handler))


class TestCommonsAdapter:
    async def test_search_keeps_bitmaps_and_builds_the_credit_url(self, recorder) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"query": {"pages": [SVG_PAGE, PAGE]}})

        found = await _commons(recorder, handler).search("Caecilia Metella", step="referencias")
        assert [c.curid for c in found] == [385176]
        assert found[0].title == "Roma Appia Antica - mausoleo Cecilia Metella.jpg"
        assert found[0].page_url == "https://commons.wikimedia.org/?curid=385176"
        assert "filetype:bitmap" in seen[0].url.params["gsrsearch"]
        assert "MundoAntigoBot" in seen[0].headers["User-Agent"]
        assert recorder.breakdown_by_step() == [("referencias", 0.0, 1)]

    async def test_maxlag_is_transient(self, recorder) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"error": {"code": "maxlag", "info": "lag"}})

        adapter = _commons(recorder, handler)
        adapter.max_retries = 0
        with pytest.raises(ProviderUnavailable, match="maxlag"):
            await adapter.search("x", step="referencias")

    async def test_download_can_ask_for_a_small_thumbnail(self, recorder, tmp_path) -> None:
        urls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            urls.append(str(request.url))
            return httpx.Response(200, content=b"jpeg")

        adapter = _commons(recorder, handler)
        candidate = (await _search_one(adapter))[0]
        #  512 nao e largura padrao: sobe para 960, a proxima aceita.
        await adapter.download(candidate, tmp_path / "t.jpg", width=512)
        assert "/960px-Mausoleo.jpg" in urls[-1]


async def _search_one(adapter: CommonsReferences):
    original = adapter._transport

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"query": {"pages": [PAGE]}})

    adapter._transport = httpx.MockTransport(handler)
    try:
        return await adapter.search("x", step="referencias")
    finally:
        adapter._transport = original


class TestPiecePhoto:
    def test_object_is_whole_and_centered(self) -> None:
        #  Uma anfora em retrato: o recorte ao centro para 16:9 cortava boca e pe.
        amphora = Image.new("RGBA", (100, 400), (180, 80, 40, 255))
        framed = letterbox(amphora, (1920, 1088))
        assert framed.size == (1920, 1088)
        box = ImageOps.invert(framed.convert("L")).getbbox()
        assert box is not None
        height = box[3] - box[1]
        assert abs(height - int(1088 * FILL)) <= 2
        assert abs((box[0] + box[2]) / 2 - 960) <= 2
        assert framed.getpixel((5, 5)) == (255, 255, 255)

    def test_configured_cutout_model_allows_commercial_use(self, settings) -> None:
        model = settings.app["referencias"]["recorte_modelo"]
        assert model in COMMERCIAL_REMBG_MODELS


def test_title_ranker_prefers_the_matching_title() -> None:
    items = [(Path("a.jpg"), "Colosseum at night"), (Path("b.jpg"), "Pantheon dome oculus")]
    scores = TitleRanker().score(items, "coffered dome with the oculus")
    assert scores[1] > scores[0]


class TestReferencesInThePipeline:
    @pytest.fixture
    def runner(self, settings, recorder, sessions, com_remotion) -> Runner:
        llm = FakeLLM(costs=recorder, responses=responder())
        image = FakeImage(costs=recorder)
        references = FakeReferences(costs=recorder)
        runner = Runner.build(
            settings=settings,
            providers=fake_registry(
                settings, recorder, llm=llm, imagem=image, referencias=references
            ),
            session_factory=sessions,
        )
        runner.image = image  # type: ignore[attr-defined]
        return runner

    async def test_licensed_photo_becomes_the_img2img_base(self, runner) -> None:
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await Worker(runner, poll_seconds=0).drain(limit=60)
        store = ArtifactStore(video_id)

        index = store.read_json("referencias", "indice.json")
        assert index["cenas"], "nenhuma cena pediu referencia"
        key, entry = next(iter(index["cenas"].items()))
        chosen = entry["escolhida"]
        #  A primeira candidata do acervo falso e BY-SA: recusada.
        assert chosen["licenca"] != "CC BY-SA 4.0"
        refused = [c for c in entry["candidatas"] if not c["aceita"]]
        assert refused and "SA" in refused[0]["motivo"]

        reference = store.path("referencias", f"cena-{key}.jpg")
        assert reference.exists()
        sidecar = store.read_sidecar(store.path("assets", f"cena-{key}.png"))
        assert sidecar is not None and sidecar.extra["referencia"]["curid"] == chosen["curid"]
        inits = [c for c in runner.image.calls if c.init_image is not None]
        assert inits and inits[0].denoise < 1.0
