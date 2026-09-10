/**
 * Verificacao do contrato de props (ADR 0001).
 *
 * O Python grava os campos que conhece em `contrato.json`; este script compara
 * com os tipos daqui. Divergencia falha o processo, que e o unico jeito de a
 * fronteira entre os dois processos nao apodrecer em silencio.
 */
import { readFileSync } from "node:fs";
import {
  CHARACTER_PROPS_FIELDS,
  SCENE_PROPS_FIELDS,
  SUBTITLE_CUE_FIELDS,
  VIDEO_PROPS_FIELDS,
} from "../src/types.ts";

const snapshotPath = process.argv[2];
if (!snapshotPath) {
  console.error("uso: node contract.ts <caminho do contrato.json>");
  process.exit(2);
}

const snapshot = JSON.parse(readFileSync(snapshotPath, "utf-8")) as Record<string, string[]>;

const sides: Record<string, string[]> = {
  VideoProps: [...VIDEO_PROPS_FIELDS].sort(),
  SceneProps: [...SCENE_PROPS_FIELDS].sort(),
  CharacterProps: [...CHARACTER_PROPS_FIELDS].sort(),
  SubtitleCue: [...SUBTITLE_CUE_FIELDS].sort(),
};

let failed = false;
for (const [name, tsFields] of Object.entries(sides)) {
  const pyFields = (snapshot[name] ?? []).slice().sort();
  const onlyPy = pyFields.filter((f) => !tsFields.includes(f));
  const onlyTs = tsFields.filter((f) => !pyFields.includes(f));
  if (onlyPy.length || onlyTs.length) {
    failed = true;
    console.error(`${name}: so no Python [${onlyPy}] | so no TS [${onlyTs}]`);
  }
}

if (failed) {
  console.error("contrato divergente entre Python e Remotion");
  process.exit(1);
}
console.log("contrato ok");
