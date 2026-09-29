/**
 * Fontes das camadas graficas, embutidas no bundle (licenca OFL, arquivos em
 * src/fonts/ junto com as licencas).
 *
 * Os videos entregues usavam uma fonte no estilo Comic; aqui ficam tres
 * candidatas livres. O render so comeca depois de todas carregadas: sem isso,
 * os primeiros quadros sairiam com a fonte padrao do navegador.
 */
import { continueRender, delayRender } from "remotion";
import baloo from "./fonts/Baloo2-Variable.ttf";
import comicNeueBold from "./fonts/ComicNeue-Bold.ttf";
import comicNeueRegular from "./fonts/ComicNeue-Regular.ttf";
import comicReliefBold from "./fonts/ComicRelief-Bold.ttf";
import comicReliefRegular from "./fonts/ComicRelief-Regular.ttf";

export const FONT_FAMILIES = ["Comic Neue", "Comic Relief", "Baloo 2"] as const;

const FACES: { family: string; url: string; weight: string }[] = [
  { family: "Comic Neue", url: comicNeueRegular, weight: "400" },
  { family: "Comic Neue", url: comicNeueBold, weight: "700" },
  { family: "Comic Relief", url: comicReliefRegular, weight: "400" },
  { family: "Comic Relief", url: comicReliefBold, weight: "700" },
  { family: "Baloo 2", url: baloo, weight: "400 800" },
];

const waitForFonts = delayRender("carregando as fontes das camadas");

Promise.all(
  FACES.map((face) =>
    new FontFace(face.family, `url(${face.url})`, { weight: face.weight })
      .load()
      .then((loaded) => {
        // A tipagem do lib.dom deste tsconfig nao expoe `add`; o navegador tem.
        (document.fonts as unknown as { add: (face: FontFace) => void }).add(loaded);
      }),
  ),
)
  .then(() => continueRender(waitForFonts))
  .catch((error: unknown) => {
    // Fonte que nao carrega nao pode travar o render: cai na de reserva.
    console.error("falha ao carregar fonte", error);
    continueRender(waitForFonts);
  });

/** Pilha CSS com a fonte escolhida e reservas. */
export const fontStack = (family: string): string =>
  `'${family}', 'Comic Neue', 'Comic Sans MS', sans-serif`;
