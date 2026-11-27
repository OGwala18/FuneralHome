import qrcode from "qrcode-generator";

/**
 * A QR code for the feedback questionnaire's link, drawn on a canvas.
 *
 * Error correction "Q" (a quarter of the code can be damaged and it still
 * scans), because these get printed, folded and taped to counters.
 */
export const qrCanvas = (text: string, size = 1024): HTMLCanvasElement => {
  const code = qrcode(0, "Q");
  code.addData(text);
  code.make();

  const modules = code.getModuleCount();
  const quiet = 4; // the blank border scanners need, in modules
  const cell = Math.floor(size / (modules + quiet * 2));
  const side = cell * (modules + quiet * 2);

  const canvas = document.createElement("canvas");
  canvas.width = side;
  canvas.height = side;
  const context = canvas.getContext("2d")!;
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, side, side);
  context.fillStyle = "#000000";
  for (let row = 0; row < modules; row += 1) {
    for (let col = 0; col < modules; col += 1) {
      if (code.isDark(row, col)) {
        context.fillRect((col + quiet) * cell, (row + quiet) * cell, cell, cell);
      }
    }
  }
  return canvas;
};
