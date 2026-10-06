/**
 * Tela em pe: os cortes do TikTok (ADR 0010).
 *
 * Os mesmos componentes desenham o video 16:9 e o corte 9:16. O modo vertical
 * vem so da proporcao do quadro, sem campo novo no contrato com o Python.
 *
 * No vertical, o texto fica dentro da zona segura do app:
 * - no alto ficam as abas ("Seguindo", "Para voce");
 * - na direita, da metade para baixo, ficam os botoes (curtir, comentar,
 *   compartilhar);
 * - no pe ficam o nome da conta e a legenda do post.
 *
 * As faixas abaixo dividem a altura entre as camadas para que nada se cubra:
 * gancho, tarja e cartao do fim no alto; texto-chave logo abaixo; a legenda
 * no meio; o MC e o balao embaixo.
 */

export const isVertical = (width: number, height: number): boolean => height > width;

/** Zona segura do TikTok, em fracao do quadro. */
export const SAFE = { top: 0.12, bottom: 0.2, right: 0.15, left: 0.05 } as const;

/** Onde cada camada fica na tela em pe, em fracao da altura. */
export const VERTICAL = {
  /** Gancho, tarja e cartao do fim: logo abaixo das abas do app. */
  topBand: 0.13,
  /** Texto-chave: abaixo do gancho, que ja saiu quando ele aparece. */
  keyText: 0.27,
  /** Centro da legenda queimada. */
  subtitles: 0.52,
  /** Altura do MC recortado, com os pes no pe do quadro. */
  host: 0.28,
  /** Balao de cena atuada (sem MC recortado): entre o texto-chave e a legenda. */
  actedAnchor: { x: 0.55, y: 0.45 },
  /** Faixa das pecas do cartao explicativo: entre o gancho e a legenda. */
  card: { top: 0.15, height: 0.3 },
} as const;
