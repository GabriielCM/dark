import React, { useLayoutEffect, useRef } from "react";
import { cancelRender, continueRender, delayRender } from "remotion";

/**
 * Imagem que so libera o quadro depois de decodificada e pintada no proprio
 * elemento.
 *
 * O `<Img>` do Remotion 4.0.230 decodifica uma copia da imagem, troca o `src`
 * do elemento visivel e libera o quadro na mesma hora. Com 6 abas e ~400
 * cenarios de 1920x1088, o quadro saia antes da pintura, na cor de fundo: nos
 * aquedutos (10/10/2026), 277 das 404 trocas de cena piscaram escuro, e no
 * corte seco isso parece um fade longo.
 */
export const DecodedImg: React.FC<React.ImgHTMLAttributes<HTMLImageElement> & { src: string }> = ({
  src,
  ...props
}) => {
  const ref = useRef<HTMLImageElement>(null);

  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) {
      return undefined;
    }
    const handle = delayRender(`Decodificando ${src}`);
    let finished = false;
    const finish = () => {
      if (finished) {
        return;
      }
      finished = true;
      // Dois quadros de animacao: o primeiro agenda a pintura, o segundo
      // garante que ela aconteceu antes da captura.
      requestAnimationFrame(() => requestAnimationFrame(() => continueRender(handle)));
    };
    const fail = () => {
      if (!finished) {
        finished = true;
        cancelRender(new Error(`Nao foi possivel carregar a imagem ${src}`));
      }
    };
    element.src = src;
    element
      .decode()
      .then(finish)
      .catch(() => {
        if (element.complete && element.naturalWidth > 0) {
          finish();
        } else {
          element.addEventListener("load", finish, { once: true });
          element.addEventListener("error", fail, { once: true });
        }
      });
    return () => {
      finished = true;
      continueRender(handle);
    };
  }, [src]);

  return <img ref={ref} {...props} />;
};
