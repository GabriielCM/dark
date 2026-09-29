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


def parse_json_loose(text: str) -> Any:
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*\n(.*)\n```\s*$", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    for candidate in (cleaned, strip_trailing_commas(cleaned)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    #  Ultimo recurso: o maior bloco entre chaves ou colchetes.
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = cleaned.find(opener), cleaned.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(strip_trailing_commas(cleaned[start : end + 1]))
            except json.JSONDecodeError:
                continue
    raise ProviderError("llm", f"resposta nao e JSON valido: {cleaned[:300]!r}")


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
