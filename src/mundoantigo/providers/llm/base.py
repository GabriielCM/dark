"""Contrato do provedor de texto."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from ...errors import ProviderError


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    raw: dict[str, Any] | None = None

    def json(self) -> Any:
        """Interpreta a resposta como JSON, tolerando cercas de codigo.

        Todo prompt do projeto pede JSON sem cercas, e todo modelo devolve
        cercas de vez em quando.
        """
        return parse_json_loose(self.text)


def strip_trailing_commas(text: str) -> str:
    """Tira a virgula antes de ] ou } fora das strings.

    E o erro de JSON mais comum dos modelos: na amostra de 29/09, o modelo
    rapido deixou `"...machine.",\\n  ],` num terco das respostas, mesmo com o
    modo JSON ligado. A passada respeita strings, entao uma virgula dentro de
    um paragrafo nunca e tocada.
    """
    out: list[str] = []
    in_string = escaped = False
    for i, char in enumerate(text):
        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == ",":
            rest = text[i + 1 :].lstrip()
            if rest[:1] in ("]", "}"):
                continue
        out.append(char)
    return "".join(out)


#  Depois de uma aspa dentro de uma string, o que indica que ela fecha a string:
#  dois-pontos, fim de objeto ou lista, fim do texto, ou uma virgula seguida do
#  comeco de outro valor. `o "furador", que` nao fecha: depois da virgula vem
#  uma palavra.
_CLOSES_STRING = re.compile(r'\s*(?:[:}\]]|$|,\s*(?:["{\[\]}\d-]|true\b|false\b|null\b))')


def escape_inner_quotes(text: str) -> str:
    """Escapa as aspas duplas soltas dentro das strings.

    Modelos que citam alguem no meio da narracao escrevem `"o "furador" abria"`
    sem escapar as aspas de dentro, mesmo com o modo JSON ligado, e o JSON nao
    abre. Uma aspa so fecha a string se o que vem depois tiver cara de JSON.
    """
    out: list[str] = []
    in_string = escaped = False
    for i, char in enumerate(text):
        if not in_string:
            in_string = char == '"'
            out.append(char)
        elif escaped:
            escaped = False
            out.append(char)
        elif char == "\\":
            escaped = True
            out.append(char)
        elif char == '"' and not _CLOSES_STRING.match(text, i + 1):
            out.append('\\"')
        else:
            in_string = char != '"'
            out.append(char)
    return "".join(out)


def _attempts(text: str) -> list[tuple[str, bool]]:
    """Os textos a tentar, do mais fiel ao mais reparado, e se o modo e estrito.

    O modo nao estrito aceita quebra de linha crua dentro das strings.
    """
    commas = strip_trailing_commas(text)
    quotes = strip_trailing_commas(escape_inner_quotes(text))
    return [(text, True), (text, False), (commas, False), (quotes, False)]


def parse_json_loose(text: str) -> Any:
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*\n(.*)\n```\s*$", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    first_error: json.JSONDecodeError | None = None
    for candidate, strict in _attempts(cleaned):
        try:
            return json.loads(candidate, strict=strict)
        except json.JSONDecodeError as exc:
            first_error = first_error or exc
    #  Ultimo recurso: o maior bloco entre chaves ou colchetes.
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = cleaned.find(opener), cleaned.rfind(closer)
        if start != -1 and end > start:
            for candidate, strict in _attempts(cleaned[start : end + 1]):
                try:
                    return json.loads(candidate, strict=strict)
                except json.JSONDecodeError:
                    continue
    where = ""
    if first_error is not None:
        #  O comeco da resposta quase nunca e onde ela quebra.
        around = cleaned[max(0, first_error.pos - 120) : first_error.pos + 120]
        where = f" ({first_error.msg}, posicao {first_error.pos}: {around!r})"
    raise ProviderError("llm", f"resposta nao e JSON valido{where}: {cleaned[:200]!r}")


class LLMProvider(Protocol):
    name: str
    model: str
    is_local: bool

    async def complete(
        self,
        prompt: str,
        *,
        step: str,
        video_id: str | None = None,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 8000,
        step_run_id: int | None = None,
    ) -> LLMResponse: ...
